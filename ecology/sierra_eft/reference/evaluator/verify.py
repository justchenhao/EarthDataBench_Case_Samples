#!/usr/bin/env python3
"""Private output-first evaluator for Sierra Nevada EFT v0.9."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image


YEARS = list(range(2001, 2019))
ANNUAL_SHAPE = (18, 164, 410)
PERIOD_SHAPE = (164, 410)
REQUIRED_FILES = {
    "sierra_nevada_eft.npz",
    "thresholds.json",
    "representative.png",
    "methodology.md",
    "build_product.py",
}
FIELDS = {
    "evi_mean_scaled": (ANNUAL_SHAPE, np.dtype("int16"), 0.0, 10000.0),
    "evi_ssd_scaled": (ANNUAL_SHAPE, np.dtype("int16"), 0.0, 10000.0),
    "evi_dmax_month": (ANNUAL_SHAPE, np.dtype("uint8"), 1.0, 12.0),
    "eft_code": (ANNUAL_SHAPE, np.dtype("uint8"), 1.0, 64.0),
    "eft_richness": (ANNUAL_SHAPE, np.dtype("uint8"), 0.0, 16.0),
    "eft_rarity": (ANNUAL_SHAPE, np.dtype("float32"), 0.0, 1.0),
    "evi_mean_interannual_mean": (PERIOD_SHAPE, np.dtype("float32"), 0.0, 10000.0),
    "evi_ssd_interannual_mean": (PERIOD_SHAPE, np.dtype("float32"), 0.0, 10000.0),
    "evi_dmax_interannual_mean": (PERIOD_SHAPE, np.dtype("float32"), 1.0, 12.0),
    "eft_mode": (PERIOD_SHAPE, np.dtype("uint8"), 1.0, 64.0),
    "eft_interannual_variability": (PERIOD_SHAPE, np.dtype("uint8"), 1.0, 18.0),
    "eft_richness_interannual_mean": (PERIOD_SHAPE, np.dtype("float32"), 0.0, 16.0),
    "eft_rarity_interannual_mean": (PERIOD_SHAPE, np.dtype("float32"), 0.0, 1.0),
    "eft_interannual_dissimilarity": (PERIOD_SHAPE, np.dtype("float32"), 0.0, 1.0),
}


def internal(detail: str) -> dict:
    return {
        "schema_version": "1.0",
        "status": "evaluator_internal_error",
        "score": None,
        "level": None,
        "detail": detail,
        "metrics": {},
    }


def scored_zero(detail: str) -> dict:
    return {
        "schema_version": "1.0",
        "status": "scored",
        "score": 0.0,
        "level": "S0",
        "detail": detail,
        "metrics": {},
    }


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {name: archive[name] for name in archive.files}


def validate_output(output_dir: Path) -> dict[str, np.ndarray]:
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ValueError("OUTPUT_DIRECTORY_INVALID")
    entries = list(output_dir.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise ValueError("OUTPUT_ENTRY_NOT_REGULAR_FILE")
    if {entry.name for entry in entries} != REQUIRED_FILES:
        raise ValueError("OUTPUT_FILE_SET_INVALID")
    if any(entry.stat().st_size <= 0 for entry in entries):
        raise ValueError("OUTPUT_FILE_EMPTY")
    if (output_dir / "build_product.py").stat().st_size > 2 * 1024 * 1024:
        raise ValueError("BUILD_SCRIPT_TOO_LARGE")
    compile((output_dir / "build_product.py").read_text(encoding="utf-8"), "build_product.py", "exec")
    (output_dir / "methodology.md").read_text(encoding="utf-8")
    thresholds = json.loads((output_dir / "thresholds.json").read_text(encoding="utf-8"))
    if thresholds.get("years") != YEARS:
        raise ValueError("THRESHOLD_YEARS_INVALID")
    for name in ("evi_mean_scaled", "evi_ssd_scaled"):
        values = thresholds.get(name)
        if not isinstance(values, list) or len(values) != 3 or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
            raise ValueError("THRESHOLD_VALUES_INVALID")
        if not values[0] < values[1] < values[2]:
            raise ValueError("THRESHOLD_ORDER_INVALID")
    with Image.open(output_dir / "representative.png") as image:
        image.verify()
    with Image.open(output_dir / "representative.png") as image:
        if image.format != "PNG":
            raise ValueError("FIGURE_CONTRACT_INVALID")
        colors = image.convert("RGB").resize((300, 180)).getcolors(maxcolors=300 * 180)
        if colors is None:
            unique_colors = 300 * 180
        else:
            unique_colors = len(colors)
        if unique_colors < 32:
            raise ValueError("FIGURE_DEGENERATE")

    submission = load_npz(output_dir / "sierra_nevada_eft.npz")
    if set(submission) != set(FIELDS):
        raise ValueError("PRODUCT_FIELDS_INVALID")
    for name, (shape, dtype, lower, upper) in FIELDS.items():
        value = submission[name]
        if value.shape != shape or value.dtype != dtype:
            raise ValueError(f"PRODUCT_SCHEMA_INVALID:{name}")
        if not np.isfinite(value).all():
            raise ValueError(f"PRODUCT_NONFINITE:{name}")
        if float(value.min()) < lower or float(value.max()) > upper:
            raise ValueError(f"PRODUCT_RANGE_INVALID:{name}")
        if np.unique(value).size < 2:
            raise ValueError(f"PRODUCT_DEGENERATE:{name}")
    return submission


def mae(candidate: np.ndarray, expert: np.ndarray) -> float:
    return float(np.mean(np.abs(candidate.astype(np.float64) - expert.astype(np.float64))))


def exact(candidate: np.ndarray, expert: np.ndarray) -> float:
    return float(np.mean(candidate == expert))


def similarity_metrics(candidate: dict[str, np.ndarray], expert: dict[str, np.ndarray]) -> dict:
    metrics = {
        "evi_mean_scaled_mae": mae(candidate["evi_mean_scaled"], expert["evi_mean_scaled"]),
        "evi_ssd_scaled_mae": mae(candidate["evi_ssd_scaled"], expert["evi_ssd_scaled"]),
        "evi_dmax_month_exact_fraction": exact(candidate["evi_dmax_month"], expert["evi_dmax_month"]),
        "eft_code_exact_fraction": exact(candidate["eft_code"], expert["eft_code"]),
        "eft_richness_exact_fraction": exact(candidate["eft_richness"], expert["eft_richness"]),
        "eft_rarity_mae": mae(candidate["eft_rarity"], expert["eft_rarity"]),
        "eft_mode_exact_fraction": exact(candidate["eft_mode"], expert["eft_mode"]),
        "eft_interannual_variability_exact_fraction": exact(candidate["eft_interannual_variability"], expert["eft_interannual_variability"]),
        "eft_interannual_dissimilarity_mae": mae(candidate["eft_interannual_dissimilarity"], expert["eft_interannual_dissimilarity"]),
    }
    components = {
        "evi_mean": max(0.0, 1.0 - metrics["evi_mean_scaled_mae"] / 500.0),
        "evi_ssd": max(0.0, 1.0 - metrics["evi_ssd_scaled_mae"] / 300.0),
        "evi_dmax": metrics["evi_dmax_month_exact_fraction"],
        "eft_code": metrics["eft_code_exact_fraction"],
        "eft_richness": metrics["eft_richness_exact_fraction"],
        "eft_rarity": max(0.0, 1.0 - metrics["eft_rarity_mae"]),
        "eft_mode": metrics["eft_mode_exact_fraction"],
        "eft_variability": metrics["eft_interannual_variability_exact_fraction"],
        "eft_dissimilarity": max(0.0, 1.0 - metrics["eft_interannual_dissimilarity_mae"]),
    }
    metrics["components"] = components
    metrics["aggregate_similarity"] = float(np.mean(list(components.values())))
    return metrics


def c_tier(similarity: float) -> float:
    if similarity >= 0.92:
        return 0.6
    if similarity >= 0.72:
        return 0.4
    return 0.2


def support_points(rows: list[dict], partition_key: str | None = None, partition_value: str | None = None) -> dict[tuple[int, int, int], int]:
    grouped: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for row in rows:
        if partition_key is not None and row.get(partition_key) != partition_value:
            continue
        key = (int(row["year"]) - 2001, int(row["row"]), int(row["col"]))
        grouped[key].append(int(row["month"]))
    return {key: int(round(float(np.median(values)))) for key, values in grouped.items()}


def b_metrics(product: dict[str, np.ndarray], points: dict[tuple[int, int, int], int]) -> dict:
    errors = []
    for (year, row, col), observed in points.items():
        predicted = int(product["evi_dmax_month"][year, row, col])
        errors.append(float(min(abs(predicted - observed), 12 - abs(predicted - observed))))
    array = np.asarray(errors, dtype=np.float64)
    return {
        "n": int(array.size),
        "coverage": 1.0 if array.size else 0.0,
        "mean_circular_month_error": float(array.mean()) if array.size else None,
        "within_one_month_fraction": float(np.mean(array <= 1.0)) if array.size else None,
    }


def b_comparison(candidate: dict[str, np.ndarray], expert: dict[str, np.ndarray], rows: list[dict]) -> dict:
    partitions = {
        "s4": support_points(rows, "s4_partition", "site_disjoint_s4"),
        "s5": support_points(rows, "s5_partition", "site_year_disjoint_s5"),
        "combined": support_points(rows),
    }
    result = {}
    for name, points in partitions.items():
        agent = b_metrics(candidate, points)
        baseline = b_metrics(expert, points)
        improvement = baseline["mean_circular_month_error"] - agent["mean_circular_month_error"]
        result[name] = {
            "agent": agent,
            "expert": baseline,
            "improvement_months": float(improvement),
            "agent_gap_to_expert_months": float(agent["mean_circular_month_error"] - baseline["mean_circular_month_error"]),
        }
    expert_error = result["combined"]["expert"]["mean_circular_month_error"]
    agent_error = result["combined"]["agent"]["mean_circular_month_error"]
    result["relative_fidelity"] = float(min(1.0, (expert_error + 1e-12) / (agent_error + 1e-12)))
    return result


def b_tier(relative_fidelity: float) -> float:
    if relative_fidelity >= 0.95:
        return 0.6
    if relative_fidelity >= 0.75:
        return 0.4
    return 0.2


def evaluate(output_dir: Path, reference_dir: Path) -> dict:
    try:
        expert = load_npz(reference_dir / "expert_product.npz")
        support_document = json.loads((reference_dir / "fixed_support.json").read_text(encoding="utf-8"))
        rows = support_document["rows"]
        if set(expert) != set(FIELDS) or len(rows) != 49:
            return internal("PRIVATE_REFERENCE_INVALID")
        for name, (shape, dtype, _, _) in FIELDS.items():
            if expert[name].shape != shape or expert[name].dtype != dtype:
                return internal("PRIVATE_REFERENCE_INVALID")
    except Exception:
        return internal("PRIVATE_REFERENCE_INVALID")

    try:
        candidate = validate_output(output_dir)
    except Exception as exc:
        return scored_zero(f"OUTPUT_CONTRACT_FAILED:{type(exc).__name__}:{exc}")

    c_metrics = similarity_metrics(candidate, expert)
    comparison = b_comparison(candidate, expert, rows)
    c_score = c_tier(c_metrics["aggregate_similarity"])
    b_score = b_tier(comparison["relative_fidelity"])
    combined_improvement = comparison["combined"]["improvement_months"]
    s4_improvement = comparison["s4"]["improvement_months"]
    s5_improvement = comparison["s5"]["improvement_months"]

    score = min(c_score, b_score)
    level = {0.2: "S1", 0.4: "S2", 0.6: "S3"}[score]
    detail = "LOW_BRANCH_MIN_C_SIMILARITY_AND_B_FIDELITY"
    if combined_improvement >= 0.25 and score < 0.6:
        detail += ";BOUNDARY_B_IMPROVED_BUT_EXPERT_LEVEL_GATES_FAILED"
    if score >= 0.6 and combined_improvement >= 0.25:
        score, level, detail = 0.8, "S4", "CUMULATIVE_S3_AND_STRICT_B_SUPERIORITY_COMBINED"
        if s4_improvement >= 0.25 and s5_improvement >= 0.25:
            score, level, detail = 1.0, "S5", "CUMULATIVE_S4_AND_STRICT_B_SUPERIORITY_BOTH_PARTITIONS"

    return {
        "schema_version": "1.0",
        "status": "scored",
        "score": score,
        "level": level,
        "detail": detail,
        "metrics": {
            "agent_vs_expert_product": c_metrics,
            "independent_validation": comparison,
            "tiers": {"c_similarity": c_score, "b_fidelity": b_score},
            "decision_order": ["output_contract", "cumulative_S1_S3_min_C_and_B", "S4_requires_S3_and_B_improvement", "S5_requires_S4_and_second_axis"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.output_dir, args.reference_dir), ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
