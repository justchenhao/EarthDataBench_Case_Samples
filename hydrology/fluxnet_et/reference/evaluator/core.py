#!/usr/bin/env python3
"""Private validation helpers for the canonical FLUXNET2015 ET evaluator."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import stat
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image


TASK_ID = "hydrology/fluxnet2015_et_benchmark_v05"
SITES = ["US-MMS", "US-Ne1", "US-NR1"]
PREDICTORS = ["ta_c", "ws_m_s", "rh_percent", "sw_in_w_m2", "lw_in_w_m2", "pa_kpa", "ndvi"]
OUTPUTS = {"daily_le_prolonged.csv.gz", "method.json", "representative_daily_le.png", "solution.py"}
METHOD_REQUIRED_KEYS = {"task_id", "validation_fidelity", "public_input_sha256", "predictors", "sites"}
SITE_REQUIRED_KEYS = {"training_rows"}


class EvaluatorIntegrityError(RuntimeError):
    pass


class AgentOutputError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key_hash(keys: list[str]) -> str:
    return hashlib.sha256(("\n".join(keys) + "\n").encode()).hexdigest()


def correlation(left: np.ndarray, right: np.ndarray) -> float:
    if left.size < 2 or np.std(left) == 0 or np.std(right) == 0:
        return float("nan")
    return float(np.corrcoef(left, right)[0, 1])


def season(month: int) -> str:
    if month in (12, 1, 2):
        return "DJF"
    if month in (3, 4, 5):
        return "MAM"
    if month in (6, 7, 8):
        return "JJA"
    return "SON"


def moving_block_lowers(author_error: np.ndarray, candidate_error: np.ndarray, dates: np.ndarray, block_length: int, resamples: int, seed: int, quantile: float) -> tuple[float, float]:
    count = author_error.size
    if count < block_length or candidate_error.size != count or dates.size != count:
        raise EvaluatorIntegrityError("PRIVATE_BLOCK_TOO_SHORT")
    rng = np.random.default_rng(seed)
    day = dates.astype("datetime64[D]").astype(np.int64)
    starts = np.array([start for start in range(count - block_length + 1) if day[start + block_length - 1] - day[start] == block_length - 1])
    if starts.size == 0:
        raise EvaluatorIntegrityError("PRIVATE_CONTIGUOUS_BLOCK_MISSING")
    rmse_sampled = np.empty(resamples, dtype=float)
    mae_sampled = np.empty(resamples, dtype=float)
    blocks_needed = math.ceil(count / block_length)
    offsets = np.arange(block_length)
    for index in range(resamples):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        positions = (chosen[:, None] + offsets[None, :]).ravel()[:count]
        ae = author_error[positions]
        ce = candidate_error[positions]
        rmse_sampled[index] = float(np.sqrt(np.mean(ae**2)) - np.sqrt(np.mean(ce**2)))
        mae_sampled[index] = float(np.mean(np.abs(ae)) - np.mean(np.abs(ce)))
    return float(np.quantile(rmse_sampled, quantile)), float(np.quantile(mae_sampled, quantile))


def load_json(path: Path, private: bool) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        error = EvaluatorIntegrityError if private else AgentOutputError
        raise error("INVALID_JSON") from exc
    if not isinstance(value, dict):
        error = EvaluatorIntegrityError if private else AgentOutputError
        raise error("INVALID_JSON_OBJECT")
    return value


def check_regular_exact(output_dir: Path) -> None:
    if not output_dir.is_dir():
        raise AgentOutputError("OUTPUT_DIRECTORY_MISSING")
    names = {path.name for path in output_dir.iterdir()}
    if names != OUTPUTS:
        raise AgentOutputError("OUTPUT_FILE_SET_INVALID")
    for name in OUTPUTS:
        path = output_dir / name
        mode = os.lstat(path).st_mode
        if not stat.S_ISREG(mode) or path.is_symlink():
            raise AgentOutputError("OUTPUT_NOT_ORDINARY_FILE")


def validate_method(path: Path, thresholds: dict) -> None:
    method = load_json(path, private=False)
    if not METHOD_REQUIRED_KEYS.issubset(method):
        raise AgentOutputError("METHOD_TOP_LEVEL_KEYS_INVALID")
    if method["task_id"] != TASK_ID or method["validation_fidelity"] != "reconstructed":
        raise AgentOutputError("METHOD_FIXED_VALUE_INVALID")
    if method["public_input_sha256"] != thresholds["public_a_sha256"] or method["predictors"] != PREDICTORS:
        raise AgentOutputError("METHOD_INPUT_IDENTITY_INVALID")
    if not isinstance(method["sites"], dict) or set(method["sites"]) != set(SITES):
        raise AgentOutputError("METHOD_SITE_CONTAINER_INVALID")
    for site in SITES:
        report = method["sites"][site]
        if not isinstance(report, dict) or not SITE_REQUIRED_KEYS.issubset(report):
            raise AgentOutputError("METHOD_SITE_KEYS_INVALID")
        if report["training_rows"] != thresholds["training_rows"][site]:
            raise AgentOutputError("METHOD_TRAINING_COUNT_INVALID")
        if isinstance(report["training_rows"], bool) or not isinstance(report["training_rows"], int):
            raise AgentOutputError("METHOD_TRAINING_COUNT_INVALID")


def load_candidate(output_dir: Path, thresholds: dict) -> pd.DataFrame:
    path = output_dir / "daily_le_prolonged.csv.gz"
    if path.read_bytes()[:2] != b"\x1f\x8b":
        raise AgentOutputError("CSV_NOT_GZIP")
    try:
        with gzip.open(path, "rt") as handle:
            frame = pd.read_csv(handle)
    except Exception as exc:
        raise AgentOutputError("CSV_UNREADABLE") from exc
    if list(frame.columns) != ["site_id", "date", "le_w_m2"] or len(frame) != 8766:
        raise AgentOutputError("CSV_SCHEMA_OR_COUNT_INVALID")
    if frame.duplicated(["site_id", "date"]).any():
        raise AgentOutputError("CSV_DUPLICATE_KEYS")
    values = pd.to_numeric(frame["le_w_m2"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all() or np.any(values < -100.0) or np.any(values > 350.0):
        raise AgentOutputError("CSV_VALUE_INVALID")
    expected_keys = thresholds["candidate_keys"]
    actual_keys = (frame["site_id"].astype(str) + "|" + frame["date"].astype(str)).tolist()
    if actual_keys != expected_keys:
        raise AgentOutputError("CSV_KEY_ORDER_OR_SUPPORT_INVALID")
    frame["le_w_m2"] = values
    for site in SITES:
        if float(frame.loc[frame.site_id.eq(site), "le_w_m2"].std()) < thresholds["s1_min_site_std"]:
            raise AgentOutputError("CSV_SITE_DEGENERATE")
    return frame


def validate_figure_and_source(output_dir: Path) -> None:
    try:
        with Image.open(output_dir / "representative_daily_le.png") as image:
            image.verify()
        with Image.open(output_dir / "representative_daily_le.png") as image:
            image.verify()
    except AgentOutputError:
        raise
    except Exception as exc:
        raise AgentOutputError("FIGURE_UNREADABLE") from exc
    try:
        source = (output_dir / "solution.py").read_text()
        compile(source, str(output_dir / "solution.py"), "exec")
    except Exception as exc:
        raise AgentOutputError("SOLUTION_INVALID") from exc
    if len(source.strip()) < 200:
        raise AgentOutputError("SOLUTION_INCOMPLETE")


def load_private(reference_dir: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    thresholds = load_json(reference_dir / "thresholds.json", private=True)
    support = load_json(reference_dir / "fixed_support.json", private=True)
    required = [
        reference_dir / "independent_fluxnet_daily_le.csv.gz",
        reference_dir / "author_daily_le.csv.gz",
        reference_dir / "evaluator_contract.json",
        reference_dir / "reference_validation_overview.png",
        reference_dir / "evaluator/verify.py",
    ]
    if not all(path.is_file() for path in required):
        raise EvaluatorIntegrityError("PRIVATE_REFERENCE_MISSING")
    b_path, c_path = required[0], required[1]
    if sha256(b_path) != thresholds["private_b_sha256"] or sha256(c_path) != thresholds["private_c_sha256"]:
        raise EvaluatorIntegrityError("PRIVATE_REFERENCE_HASH_DRIFT")
    try:
        b = pd.read_csv(b_path)
        c = pd.read_csv(c_path)
    except Exception as exc:
        raise EvaluatorIntegrityError("PRIVATE_REFERENCE_UNREADABLE") from exc
    if list(b.columns) != ["site_id", "date", "le_obs_w_m2", "le_obs_qc"] or list(c.columns) != ["site_id", "date", "le_w_m2"]:
        raise EvaluatorIntegrityError("PRIVATE_REFERENCE_SCHEMA_INVALID")
    if b.duplicated(["site_id", "date"]).any() or c.duplicated(["site_id", "date"]).any():
        raise EvaluatorIntegrityError("PRIVATE_REFERENCE_DUPLICATE_KEYS")
    b_keys = (b.site_id.astype(str) + "|" + b.date.astype(str)).tolist()
    c_keys = (c.site_id.astype(str) + "|" + c.date.astype(str)).tolist()
    if len(b_keys) != support["independent"]["count"] or key_hash(b_keys) != support["independent"]["sha256"]:
        raise EvaluatorIntegrityError("PRIVATE_SUPPORT_MISMATCH")
    if len(c_keys) != support["author"]["count"] or key_hash(c_keys) != support["author"]["sha256"]:
        raise EvaluatorIntegrityError("PRIVATE_AUTHOR_SUPPORT_MISMATCH")
    if len(c_keys) != len(thresholds["candidate_keys"]) or set(c_keys) != set(thresholds["candidate_keys"]):
        raise EvaluatorIntegrityError("PRIVATE_CANDIDATE_SUPPORT_MISMATCH")
    public_path = reference_dir.parent / "input/daily_predictors_and_training.csv.gz"
    if not public_path.is_file() or sha256(public_path) != thresholds["public_a_sha256"]:
        raise EvaluatorIntegrityError("PUBLIC_RUNTIME_INPUT_MISSING_OR_DRIFTED")
    try:
        public = pd.read_csv(public_path)
    except Exception as exc:
        raise EvaluatorIntegrityError("PUBLIC_RUNTIME_INPUT_UNREADABLE") from exc
    return thresholds, b, c, public
