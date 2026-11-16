#!/usr/bin/env python3
"""Private cumulative evaluator for TP glacier SAT v0.10."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from PIL import Image


TASK_ID = "cryosphere/tp_glacier_sat_station_correction_v13"
CASE_VERSION = "v0.13"
OUTPUT_FILES = {"sat_201901.tif", "sat_201907.tif", "representative_sat.png", "method_report.md"}
REPORT_TOKENS = ("RMSE", "MBE", "R2", "MOD11A1", "MYD11A1", "MOD13A3", "MCD43A3", "SRTM", "ERA5", "CMA", "NCEI", "TPDC", "self-check", "spatiotemporal")


class AgentOutputError(RuntimeError):
    pass


def _error(reason: str) -> dict:
    return {"schema_version": "1.0", "status": "agent_output_error", "score": 0.0, "score_level": "S0", "reason": reason, "stages": []}


def _internal(reason: str) -> dict:
    return {"schema_version": "1.0", "status": "evaluator_internal_error", "score": None, "score_level": None, "detail": reason}


def _raster(path: Path) -> np.ndarray:
    try:
        with rasterio.open(path) as ds:
            if ds.count != 1 or ds.width != 80 or ds.height != 70 or ds.crs.to_string() != "EPSG:4326":
                raise AgentOutputError("RASTER_GRID_INVALID")
            if ds.dtypes[0] != "float32":
                raise AgentOutputError("RASTER_DTYPE_INVALID")
            if abs(ds.transform.a - 0.01) > 1e-9 or abs(ds.transform.e + 0.01) > 1e-9 or abs(ds.transform.c - 96.5) > 1e-9 or abs(ds.transform.f - 29.7) > 1e-9:
                raise AgentOutputError("RASTER_TRANSFORM_INVALID")
            array = ds.read(1).astype(np.float64)
    except AgentOutputError:
        raise
    except Exception as exc:
        raise AgentOutputError("RASTER_UNREADABLE") from exc
    if not np.isfinite(array).all() or float(array.min()) < -80.0 or float(array.max()) > 50.0:
        raise AgentOutputError("RASTER_FINITE_OR_RANGE_INVALID")
    if float(np.std(array)) < 0.1:
        raise AgentOutputError("RASTER_DEGENERATE")
    return array


def validate_delivery(output: Path) -> dict[str, np.ndarray]:
    if output.is_symlink() or not output.is_dir():
        raise AgentOutputError("OUTPUT_DIRECTORY_MISSING_OR_UNSAFE")
    entries = list(output.iterdir())
    if {item.name for item in entries} != OUTPUT_FILES or any(item.is_symlink() or not item.is_file() or item.stat().st_size == 0 for item in entries):
        raise AgentOutputError("DELIVERABLE_SET_INVALID")
    rasters = {"201901": _raster(output / "sat_201901.tif"), "201907": _raster(output / "sat_201907.tif")}
    try:
        with Image.open(output / "representative_sat.png") as image:
            image.verify()
        with Image.open(output / "representative_sat.png") as image:
            image.verify()
    except AgentOutputError:
        raise
    except Exception as exc:
        raise AgentOutputError("FIGURE_UNREADABLE") from exc
    report = (output / "method_report.md").read_text(encoding="utf-8")
    if len(report.encode("utf-8")) < 800 or any(token not in report for token in REPORT_TOKENS):
        raise AgentOutputError("METHOD_REPORT_INVALID")
    return rasters


def _metrics(pred: np.ndarray, truth: np.ndarray) -> dict:
    error = pred - truth
    sst = float(np.sum((truth - np.mean(truth)) ** 2))
    return {"n": int(truth.size), "rmse": float(np.sqrt(np.mean(error ** 2))), "mae": float(np.mean(np.abs(error))), "mbe": float(np.mean(error)), "abs_mbe": float(abs(np.mean(error))), "r2": None if sst == 0 else float(1 - np.sum(error ** 2) / sst)}


def _load_table(path: Path) -> pd.DataFrame:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return pd.read_csv(stream)


def _sample(array: np.ndarray, lat: float, lon: float) -> float:
    row = int(np.rint((29.7 - lat) / 0.01 - 0.5))
    col = int(np.rint((lon - 96.5) / 0.01 - 0.5))
    if row < 0 or row >= array.shape[0] or col < 0 or col >= array.shape[1]:
        return float("nan")
    return float(array[row, col])


def _score_b(rasters: dict[str, np.ndarray], reference: Path) -> tuple[dict, dict]:
    truth = _load_table(reference / "heldout_truth.csv.gz")
    baseline = _load_table(reference / "author_method_reconstruction.csv.gz")
    coords = pd.read_csv(reference / "support_coords.csv")
    groups = pd.read_csv(reference / "fixed_support.csv")
    truth = truth.merge(coords, on="station_id", how="inner").merge(groups, on=["station_id", "year_month"], how="inner")
    baseline = baseline.merge(truth[["station_id", "year_month"]], on=["station_id", "year_month"], how="inner")
    candidate_values = []
    for row in truth.itertuples():
        candidate_values.append(_sample(rasters[str(row.year_month).replace("-", "")], row.latitude, row.longitude))
    truth["candidate"] = candidate_values
    truth["baseline"] = baseline["sat_c"].to_numpy()
    if not np.isfinite(truth["candidate"]).all():
        raise AgentOutputError("B_SAMPLE_OUTSIDE_OR_INVALID")
    all_candidate = _metrics(truth["candidate"].to_numpy(float), truth["sat_c"].to_numpy(float))
    all_baseline = _metrics(truth["baseline"].to_numpy(float), truth["sat_c"].to_numpy(float))
    by_group = {}
    for name, frame in truth.groupby("score_split", sort=True):
        by_group[name] = {"candidate": _metrics(frame["candidate"].to_numpy(float), frame["sat_c"].to_numpy(float)), "baseline": _metrics(frame["baseline"].to_numpy(float), frame["sat_c"].to_numpy(float))}
    metrics = {"candidate": all_candidate, "baseline": all_baseline, "groups": by_group, "support_rows": int(len(truth))}
    stage06 = all_candidate["rmse"] <= all_baseline["rmse"] + 0.5 and all_candidate["abs_mbe"] <= all_baseline["abs_mbe"] + 0.5 and (all_candidate["r2"] or -999) >= (all_baseline["r2"] or -999) - 0.05
    # 0.8 (approved 2026-11-10): substantial improvement = every partition's RMSE
    # and |MBE| at most 50% of the author baseline, plus overall RMSE at or below
    # the paper's glacier-station accuracy (1.61 degC, Qin et al. 2023 Fig. 4c).
    stage08 = (
        all_candidate["rmse"] <= 0.5 * all_baseline["rmse"]
        and all_candidate["abs_mbe"] <= 0.5 * all_baseline["abs_mbe"]
        and all_candidate["rmse"] <= 1.61
        and (all_candidate["r2"] or -999) >= (all_baseline["r2"] or -999) - 1e-9
        and all(
            by["candidate"]["rmse"] <= 0.5 * by["baseline"]["rmse"]
            and by["candidate"]["abs_mbe"] <= 0.5 * by["baseline"]["abs_mbe"]
            for by in by_group.values()
        )
    )
    # 1.0: additionally overall RMSE at or below the paper's TP regular-station
    # accuracy (1.35 degC, Qin et al. 2023 Fig. 4b).
    stage10 = stage08 and all_candidate["rmse"] <= 1.35
    return metrics, {"score_0_6": stage06, "score_0_8": stage08, "score_1_0": stage10}


def _score_c(rasters: dict[str, np.ndarray], reference: Path) -> dict:
    errors = []
    coverages = []
    for month in ("201901", "201907"):
        with rasterio.open(reference / f"author_grid_{month}.tif") as ds:
            author = ds.read(1).astype(float)
        mask = np.isfinite(author)
        coverages.append(float(mask.mean()))
        if mask.any():
            errors.extend((rasters[month][mask] - author[mask]).tolist())
    error = np.asarray(errors, dtype=float)
    return {"finite_coverage_mean": float(np.mean(coverages)), "n": int(error.size), "mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error ** 2)))}


def evaluate(output_dir: Path, reference_dir: Path) -> dict:
    output, reference = Path(output_dir), Path(reference_dir)
    try:
        rasters = validate_delivery(output)
    except AgentOutputError as exc:
        return _error(str(exc))
    try:
        c = _score_c(rasters, reference)
        b, b_flags = _score_b(rasters, reference)
    except AgentOutputError as exc:
        return _error(str(exc))
    except Exception as exc:
        return _internal(f"PRIVATE_EVALUATOR_FAILED:{type(exc).__name__}")
    stage02 = True
    stage04 = c["n"] >= 20 and c["finite_coverage_mean"] >= 0.005 and c["mae"] <= 15.0
    stage06 = stage04 and b_flags["score_0_6"] and c["mae"] <= 10.0
    stage08 = stage06 and b_flags["score_0_8"]
    stage10 = stage08 and b_flags["score_1_0"]
    stages = [
        {"stage": "score_0_2", "passed": stage02, "metrics": {"output_files": len(OUTPUT_FILES)}},
        {"stage": "score_0_4", "passed": stage04, "metrics": {"C": c}},
        {"stage": "score_0_6", "passed": stage06, "metrics": {"B": b, "C": c}},
        {"stage": "score_0_8", "passed": stage08, "metrics": {"B": b}},
        {"stage": "score_1_0", "passed": stage10, "metrics": {"B": b, "C": c}},
    ]
    score, level = 0.0, "S0"
    for value, stage in ((0.2, stage02), (0.4, stage04), (0.6, stage06), (0.8, stage08), (1.0, stage10)):
        if stage:
            score, level = value, f"S{int(value * 5)}"
        else:
            break
    return {"schema_version": "1.0", "status": "scored", "score": score, "score_level": level, "stages": stages, "metrics": {"B": b, "C": c}}
