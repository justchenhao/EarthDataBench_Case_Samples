"""Strict bottom-up cumulative evaluator for Atlantic d13C-DIC v0.3."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from netCDF4 import Dataset

from io_guard import (
    AgentOutputError,
    load_climatology,
    load_points,
    load_qc,
    validate_directory,
    validate_methodology,
    validate_png,
    validate_source,
)


def verdict(status: str, score: float | None, detail: str, **fields: object) -> dict:
    return {
        "schema_version": "1.0",
        "status": status,
        "score": score,
        "score_level": None if score is None else {0.0: "S0", 0.2: "S1", 0.4: "S2", 0.6: "S3", 0.8: "S4", 1.0: "S5"}[score],
        "detail": detail,
        **fields,
    }


def _sha256_lines(values: np.ndarray) -> str:
    return hashlib.sha256("".join(f"{value}\n" for value in values).encode("utf-8")).hexdigest()


def _metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float | int]:
    reference = np.asarray(reference, dtype="f8")
    candidate = np.asarray(candidate, dtype="f8")
    error = candidate - reference
    denominator = float(np.sum((reference - reference.mean()) ** 2))
    correlation = 0.0 if len(reference) < 2 or np.std(reference) == 0 or np.std(candidate) == 0 else float(np.corrcoef(reference, candidate)[0, 1])
    return {
        "n": int(len(reference)),
        "rmse": float(np.sqrt(np.mean(error * error))),
        "mae": float(np.mean(np.abs(error))),
        "bias": float(np.mean(error)),
        "r2": 0.0 if denominator == 0 else 1.0 - float(np.sum(error * error)) / denominator,
        "correlation": correlation,
        "candidate_standard_deviation": float(np.std(candidate)),
    }


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise RuntimeError(f"PRIVATE_CSV_UNREADABLE:{path.name}:{type(exc).__name__}") from exc
    if list(frame.columns) != columns:
        raise RuntimeError(f"PRIVATE_CSV_SCHEMA:{path.name}")
    return frame


def _load_private(evaluation_dir: Path, contract: dict) -> dict[str, object]:
    try:
        with np.load(evaluation_dir / "public_support.npz", allow_pickle=False) as source:
            support = {name: source[name] for name in source.files}
    except Exception as exc:
        raise RuntimeError(f"PRIVATE_SUPPORT_UNREADABLE:{type(exc).__name__}") from exc
    expected_arrays = {
        "qc_ids", "qc_expocodes", "point_ids", "depth", "lat", "lon", "valid_mask"
    }
    if set(support) != expected_arrays:
        raise RuntimeError("PRIVATE_SUPPORT_ARRAY_SET")
    if (
        support["qc_ids"].shape != (96_079,)
        or support["qc_expocodes"].shape != (96_079,)
        or support["point_ids"].shape != (152_127,)
        or support["depth"].shape != (33,)
        or support["lat"].shape != (180,)
        or support["lon"].shape != (360,)
        or support["valid_mask"].shape != (33, 180, 360)
    ):
        raise RuntimeError("PRIVATE_SUPPORT_SHAPE")
    if (
        _sha256_lines(support["qc_ids"]) != contract["support"]["qc_id_sha256"]
        or _sha256_lines(support["point_ids"]) != contract["support"]["point_id_sha256"]
        or _sha256_lines(support["qc_expocodes"]) != contract["support"]["qc_expocode_sha256"]
        or int(np.sum(support["valid_mask"])) != contract["support"]["grid_valid_cells"]
    ):
        raise RuntimeError("PRIVATE_SUPPORT_HASH_OR_COUNT")
    if (
        len(np.unique(support["qc_ids"])) != len(support["qc_ids"])
        or len(np.unique(support["point_ids"])) != len(support["point_ids"])
        or np.any(np.diff(support["qc_ids"]) <= 0)
        or np.any(np.diff(support["point_ids"]) <= 0)
    ):
        raise RuntimeError("PRIVATE_SUPPORT_KEYS")
    support["valid_mask"] = support["valid_mask"].astype(bool)

    expert_qc = _read_csv(
        evaluation_dir / "data/expert_qc_observations.csv.gz",
        ["observation_id", "expocode", "adjusted_d13c_dic_per_mille", "quality_flag"],
    )
    expert_point = _read_csv(
        evaluation_dir / "data/expert_point_product.csv.gz",
        ["sample_id", "author_d13c_dic_per_mille", "author_quality_flag"],
    )
    independent = _read_csv(
        evaluation_dir / "data/independent_holdout_reference.csv.gz",
        [
            "sample_id", "expocode", "region", "block_id", "station",
            "longitude_deg_e", "latitude_deg_n", "depth_m",
            "truth_d13c_dic_per_mille", "author_d13c_dic_per_mille",
        ],
    )
    if (
        len(expert_qc) != 96_079
        or len(expert_point) != 152_127
        or len(independent) != 881
        or expert_qc.observation_id.duplicated().any()
        or expert_point.sample_id.duplicated().any()
        or independent.sample_id.duplicated().any()
        or not np.array_equal(expert_qc.observation_id.to_numpy(np.int64), support["qc_ids"])
        or not np.array_equal(expert_qc.expocode.astype(str).to_numpy(), support["qc_expocodes"].astype(str))
        or not np.array_equal(expert_point.sample_id.to_numpy(np.int64), support["point_ids"])
    ):
        raise RuntimeError("PRIVATE_REFERENCE_SUPPORT")
    counts = independent.groupby("region").size().to_dict()
    blocks = independent.groupby("region").block_id.nunique().to_dict()
    if counts != {"north_atlantic": 430, "south_atlantic": 451} or blocks != {"north_atlantic": 50, "south_atlantic": 22}:
        raise RuntimeError("PRIVATE_B_GROUPS")
    positions = np.searchsorted(support["point_ids"], independent.sample_id.to_numpy(np.int64))
    if not np.array_equal(support["point_ids"][positions], independent.sample_id.to_numpy(np.int64)):
        raise RuntimeError("PRIVATE_B_POINT_MAPPING")
    if not np.allclose(
        expert_point.author_d13c_dic_per_mille.to_numpy()[positions],
        independent.author_d13c_dic_per_mille.to_numpy(),
        rtol=0,
        atol=1e-12,
    ):
        raise RuntimeError("PRIVATE_B_AUTHOR_MAPPING")

    try:
        with Dataset(evaluation_dir / "data/expert_climatology.nc", "r") as dataset:
            if not {"Depth", "lat", "lon", "c13_recon"}.issubset(dataset.variables):
                raise RuntimeError("PRIVATE_GRID_VARIABLES")
            if (
                not np.array_equal(dataset["Depth"][:], support["depth"])
                or not np.array_equal(dataset["lat"][:], support["lat"])
                or not np.array_equal(dataset["lon"][:], support["lon"])
            ):
                raise RuntimeError("PRIVATE_GRID_COORDINATES")
            expert_grid = np.asarray(np.ma.filled(dataset["c13_recon"][:], np.nan), dtype="f8")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"PRIVATE_GRID_UNREADABLE:{type(exc).__name__}") from exc
    grid_comparison = np.isfinite(expert_grid) & support["valid_mask"]
    if int(grid_comparison.sum()) != 280_744 or np.any(np.isfinite(expert_grid) & ~support["valid_mask"]):
        raise RuntimeError("PRIVATE_GRID_SUPPORT")
    return {
        "support": support,
        "expert_qc": expert_qc,
        "expert_point": expert_point,
        "independent": independent,
        "b_positions": positions,
        "expert_grid": expert_grid,
        "grid_comparison": grid_comparison,
    }


def _block_bootstrap_lower(
    frame: pd.DataFrame,
    candidate: np.ndarray,
    contract: dict,
    region: str,
) -> tuple[float, float]:
    blocks = sorted(frame.block_id.unique())
    block_values = frame.block_id.to_numpy()
    positions = {block: np.flatnonzero(block_values == block) for block in blocks}
    truth = frame.truth_d13c_dic_per_mille.to_numpy(float)
    author = frame.author_d13c_dic_per_mille.to_numpy(float)
    bootstrap = contract["independent_b"]["bootstrap"]
    rng = np.random.Generator(np.random.PCG64(bootstrap["seeds"][region]))
    gains_rmse = np.empty(bootstrap["replicates"], dtype="f8")
    gains_mae = np.empty(bootstrap["replicates"], dtype="f8")
    for index in range(bootstrap["replicates"]):
        selected = rng.choice(blocks, size=len(blocks), replace=True)
        rows = np.concatenate([positions[block] for block in selected])
        author_error = author[rows] - truth[rows]
        candidate_error = candidate[rows] - truth[rows]
        gains_rmse[index] = np.sqrt(np.mean(author_error * author_error)) - np.sqrt(np.mean(candidate_error * candidate_error))
        gains_mae[index] = np.mean(np.abs(author_error)) - np.mean(np.abs(candidate_error))
    quantile = bootstrap["quantile"]
    return (
        float(np.quantile(gains_rmse, quantile, method="inverted_cdf")),
        float(np.quantile(gains_mae, quantile, method="inverted_cdf")),
    )


def _regional_b(frame: pd.DataFrame, candidate: np.ndarray, contract: dict, region: str) -> dict:
    truth = frame.truth_d13c_dic_per_mille.to_numpy(float)
    author = frame.author_d13c_dic_per_mille.to_numpy(float)
    author_metrics = _metrics(truth, author)
    candidate_metrics = _metrics(truth, candidate)
    rmse_gain = float(author_metrics["rmse"] - candidate_metrics["rmse"])
    mae_gain = float(author_metrics["mae"] - candidate_metrics["mae"])
    rmse_lower, mae_lower = _block_bootstrap_lower(frame, candidate, contract, region)
    block_improvements = []
    for block_id, block in frame.assign(candidate=candidate).groupby("block_id", sort=True):
        block_truth = block.truth_d13c_dic_per_mille.to_numpy(float)
        author_rmse = float(np.sqrt(np.mean((block.author_d13c_dic_per_mille.to_numpy(float) - block_truth) ** 2)))
        candidate_rmse = float(np.sqrt(np.mean((block.candidate.to_numpy(float) - block_truth) ** 2)))
        block_improvements.append(candidate_rmse < author_rmse)
    return {
        "region": region,
        "blocks": int(frame.block_id.nunique()),
        "author": author_metrics,
        "candidate": candidate_metrics,
        "rmse_ratio_to_author": float(candidate_metrics["rmse"] / author_metrics["rmse"]),
        "mae_ratio_to_author": float(candidate_metrics["mae"] / author_metrics["mae"]),
        "rmse_gain": rmse_gain,
        "mae_gain": mae_gain,
        "relative_rmse_gain": float(rmse_gain / author_metrics["rmse"]),
        "relative_mae_gain": float(mae_gain / author_metrics["mae"]),
        "block_bootstrap_rmse_gain_lcb_05": rmse_lower,
        "block_bootstrap_mae_gain_lcb_05": mae_lower,
        "improved_block_fraction": float(np.mean(block_improvements)),
    }


def _strict_region(metrics: dict, thresholds: dict) -> bool:
    return bool(
        metrics["rmse_gain"] >= thresholds["absolute_gain_min"]
        and metrics["mae_gain"] >= thresholds["absolute_gain_min"]
        and metrics["relative_rmse_gain"] >= thresholds["relative_gain_min"]
        and metrics["relative_mae_gain"] >= thresholds["relative_gain_min"]
        and metrics["block_bootstrap_rmse_gain_lcb_05"] > thresholds["bootstrap_gain_lcb_min_exclusive"]
        and metrics["block_bootstrap_mae_gain_lcb_05"] > thresholds["bootstrap_gain_lcb_min_exclusive"]
        and metrics["improved_block_fraction"] >= thresholds["improved_block_fraction_min"]
        and abs(metrics["candidate"]["bias"]) <= thresholds["absolute_bias_max"]
    )


def _b_cap(regions: dict[str, dict], contract: dict) -> float:
    for score in ("0.6", "0.4"):
        threshold = contract["independent_b"]["degradation_caps"][score]
        if all(
            value["rmse_ratio_to_author"] <= threshold["rmse_ratio_max"]
            and value["mae_ratio_to_author"] <= threshold["mae_ratio_max"]
            and abs(value["candidate"]["bias"]) <= threshold["absolute_bias_max"]
            for value in regions.values()
        ):
            return float(score)
    return 0.2


def _passes(metrics: dict, thresholds: dict) -> bool:
    for name, limit in thresholds.items():
        metric_name = name.removesuffix("_min").removesuffix("_max")
        value = metrics[metric_name]
        if metric_name == "bias":
            value = abs(value)
        if name.endswith("_min"):
            if value < limit:
                return False
        elif name.endswith("_max"):
            if value > limit:
                return False
        else:
            raise RuntimeError(f"PRIVATE_THRESHOLD_NAME:{name}")
    return True


def _c_metrics(candidate: dict, private: dict) -> dict:
    expert_qc = private["expert_qc"]
    expert_point = private["expert_point"]
    qc_reference = expert_qc.adjusted_d13c_dic_per_mille.to_numpy(float)
    qc_valid = qc_reference != -9999.0
    qc = _metrics(qc_reference[qc_valid], candidate["qc"]["values"][qc_valid])
    qc["flag_agreement"] = float(np.mean(expert_qc.quality_flag.to_numpy(np.int64) == candidate["qc"]["flags"]))
    point = _metrics(expert_point.author_d13c_dic_per_mille.to_numpy(float), candidate["points"]["values"])
    point["flag_agreement"] = float(np.mean(expert_point.author_quality_flag.to_numpy(np.int64) == candidate["points"]["flags"]))
    mask = private["grid_comparison"]
    grid = _metrics(private["expert_grid"][mask], candidate["grid"]["d13c_dic"][mask])
    uncertainty = np.concatenate(
        [
            candidate["points"]["uncertainty"],
            candidate["grid"]["uncertainty"][private["support"]["valid_mask"]].astype(float),
        ]
    )
    uncertainty_metrics = {
        "median": float(np.median(uncertainty)),
        "p95": float(np.quantile(uncertainty, 0.95)),
        "minimum": float(np.min(uncertainty)),
        "maximum": float(np.max(uncertainty)),
    }
    return {"qc": qc, "point": point, "grid": grid, "uncertainty": uncertainty_metrics}


def _c_tier(metrics: dict, contract: dict) -> float:
    for score in ("0.6", "0.4"):
        thresholds = contract["author_c"]["agreement_tiers"][score]
        passed = all(_passes(metrics[branch], thresholds[branch]) for branch in ("qc", "point", "grid"))
        uncertainty = metrics["uncertainty"]
        uncertainty_pass = (
            thresholds["uncertainty"]["median_min"] <= uncertainty["median"] <= thresholds["uncertainty"]["median_max"]
            and uncertainty["p95"] <= thresholds["uncertainty"]["p95_max"]
        )
        if passed and uncertainty_pass:
            return float(score)
    return 0.2


def evaluate(output_dir: Path, evaluation_dir: Path) -> dict:
    contract = json.loads((evaluation_dir / "contract.json").read_text(encoding="utf-8"))
    private = _load_private(evaluation_dir, contract)
    support = private["support"]
    try:
        validate_directory(output_dir)
        candidate = {
            "qc": load_qc(output_dir / "qc_observations.csv.gz", support["qc_ids"], support["qc_expocodes"]),
            "points": load_points(output_dir / "reconstructed_points.csv.gz", support["point_ids"]),
            "grid": load_climatology(
                output_dir / "climatology.nc",
                support["depth"], support["lat"], support["lon"], support["valid_mask"],
            ),
        }
        output_gate = {
            "passed": True,
            "figure": validate_png(output_dir / "representative.png"),
            "methodology": validate_methodology(output_dir / "methodology.md"),
            "source": validate_source(output_dir / "build_product.py"),
            "qc_valid_rows": int(np.sum(candidate["qc"]["values"] != -9999.0)),
            "point_rows": int(len(candidate["points"]["ids"])),
            "grid_valid_cells": int(np.sum(support["valid_mask"])),
        }
    except AgentOutputError as exc:
        return verdict("agent_output_error", 0.0, str(exc), passed_levels=[], output_gate={"passed": False})

    independent = private["independent"].copy()
    independent["candidate"] = candidate["points"]["values"][private["b_positions"]]
    regions = {
        region: _regional_b(
            independent[independent.region.eq(region)].reset_index(drop=True),
            independent.loc[independent.region.eq(region), "candidate"].to_numpy(float),
            contract,
            region,
        )
        for region in ("north_atlantic", "south_atlantic")
    }
    c_metrics = _c_metrics(candidate, private)
    c_tier = _c_tier(c_metrics, contract)
    b_cap = _b_cap(regions, contract)
    north_pass = _strict_region(regions["north_atlantic"], contract["independent_b"]["strict_0_8_north"])
    south_pass = _strict_region(regions["south_atlantic"], contract["independent_b"]["strict_1_0_south"])

    score = min(c_tier, b_cap)
    if score >= 0.6 and north_pass and south_pass:
        return verdict(
            "scored", 1.0, "CUMULATIVE_NORTH_AND_SOUTH_STRICT_SUPERIORITY",
            passed_levels=[0.2, 0.4, 0.6, 0.8, 1.0], output_gate=output_gate,
            independent_b=regions, b_degradation_cap=b_cap, strict_b_superiority={"north": True, "south": True},
            author_c=c_metrics, author_c_tier=c_tier,
        )
    if score >= 0.6 and north_pass and b_cap >= 0.6:
        return verdict(
            "scored", 0.8, "NORTH_STRICT_SUPERIORITY_WITH_SOUTH_NONDEGRADATION",
            passed_levels=[0.2, 0.4, 0.6, 0.8], output_gate=output_gate,
            independent_b=regions, b_degradation_cap=b_cap, strict_b_superiority={"north": True, "south": south_pass},
            author_c=c_metrics, author_c_tier=c_tier,
        )

    return verdict(
        "scored", score, f"NO_STRICT_B_SUPERIORITY:C_{c_tier:.1f}:B_CAP_{b_cap:.1f}",
        passed_levels=[value for value in (0.2, 0.4, 0.6) if value <= score], output_gate=output_gate,
        independent_b=regions, b_degradation_cap=b_cap,
        strict_b_superiority={"north": north_pass, "south": south_pass},
        author_c=c_metrics, author_c_tier=c_tier,
    )
