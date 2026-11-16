#!/usr/bin/env python3
"""Target-first evaluator for the FLUXNET daily-LE prolongation successor.

The public output contract is checked first.  Expert agreement and the
independent-validation degradation cap then establish the cumulative 0.6
prerequisite.  Only products reaching that level can earn robust superiority
scores on independent tower observations.  Private support and numerical
thresholds are frozen outside Public D.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


TASK_ID = "hydrology/fluxnet2015_et_benchmark_v05"
SITES = ["US-MMS", "US-Ne1", "US-NR1"]
PERIODS = {"2015_2018": (2015, 2018), "2019_2022": (2019, 2022)}
REQUIRED_METHOD_KEYS = {
    "task_id",
    "validation_fidelity",
    "public_input_sha256",
    "predictors",
    "sites",
}


def _core(reference_dir: Path):
    path = reference_dir / "evaluator" / "core.py"
    spec = importlib.util.spec_from_file_location("fluxnet_contract_core", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("EVALUATOR_CORE_MISSING")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TASK_ID = TASK_ID
    return module


def _method_gate(path: Path, thresholds: dict, core) -> None:
    method = core.load_json(path, private=False)
    if not REQUIRED_METHOD_KEYS.issubset(method):
        raise core.AgentOutputError("METHOD_REQUIRED_KEYS_MISSING")
    if method["task_id"] != TASK_ID or method["validation_fidelity"] != "reconstructed":
        raise core.AgentOutputError("METHOD_FIXED_VALUE_INVALID")
    if method["public_input_sha256"] != thresholds["public_a_sha256"]:
        raise core.AgentOutputError("METHOD_INPUT_IDENTITY_INVALID")
    if method["predictors"] != core.PREDICTORS:
        raise core.AgentOutputError("METHOD_PREDICTORS_INVALID")
    if not isinstance(method["sites"], dict) or set(method["sites"]) != set(SITES):
        raise core.AgentOutputError("METHOD_SITE_CONTAINER_INVALID")
    for site in SITES:
        report = method["sites"][site]
        if not isinstance(report, dict):
            raise core.AgentOutputError("METHOD_SITE_REPORT_INVALID")
        if report.get("training_rows") != thresholds["training_rows"][site]:
            raise core.AgentOutputError("METHOD_TRAINING_COUNT_INVALID")


def _errors(group: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    obs = group["le_obs_w_m2"].to_numpy(float)
    author = group["le_w_m2_author"].to_numpy(float) - obs
    candidate = group["le_w_m2_candidate"].to_numpy(float) - obs
    return author, candidate


def _gain(group: pd.DataFrame) -> dict[str, float]:
    author, candidate = _errors(group)
    author_rmse = float(np.sqrt(np.mean(author**2)))
    author_mae = float(np.mean(np.abs(author)))
    candidate_rmse = float(np.sqrt(np.mean(candidate**2)))
    candidate_mae = float(np.mean(np.abs(candidate)))
    rmse_gain = author_rmse - candidate_rmse
    mae_gain = author_mae - candidate_mae
    return {
        "count": int(len(group)),
        "author_rmse_w_m2": author_rmse,
        "candidate_rmse_w_m2": candidate_rmse,
        "rmse_gain_w_m2": rmse_gain,
        "rmse_relative_gain": rmse_gain / author_rmse if author_rmse else 0.0,
        "author_mae_w_m2": author_mae,
        "candidate_mae_w_m2": candidate_mae,
        "mae_gain_w_m2": mae_gain,
        "mae_relative_gain": mae_gain / author_mae if author_mae else 0.0,
        "rmse_relative_degradation": (candidate_rmse - author_rmse) / author_rmse if author_rmse else 0.0,
        "mae_relative_degradation": (candidate_mae - author_mae) / author_mae if author_mae else 0.0,
    }


def _strict_gain(metric: dict, score: dict) -> bool:
    return bool(
        metric["rmse_gain_w_m2"] >= score["high_min_absolute_gain_w_m2"]
        and metric["mae_gain_w_m2"] >= score["high_min_absolute_gain_w_m2"]
        and metric["rmse_relative_gain"] >= score["high_min_relative_gain"]
        and metric["mae_relative_gain"] >= score["high_min_relative_gain"]
    )


def _author_metrics(author: pd.DataFrame, candidate: pd.DataFrame, core) -> dict:
    joined = author.merge(
        candidate,
        on=["site_id", "date"],
        suffixes=("_author", "_candidate"),
        validate="one_to_one",
    )
    result = {}
    for site in SITES:
        group = joined[joined.site_id.eq(site)]
        left = group.le_w_m2_author.to_numpy(float)
        right = group.le_w_m2_candidate.to_numpy(float)
        delta = right - left
        scale = float(np.std(left, ddof=1))
        result[site] = {
            "nrmse": float(np.sqrt(np.mean(delta**2)) / scale),
            "nmae": float(np.mean(np.abs(delta)) / scale),
            "normalized_absolute_bias": float(abs(np.mean(delta)) / scale),
            "correlation": core.correlation(left, right),
        }
    return result


def _low_tier(author_metrics: dict, score: dict) -> float:
    for tier in ("0.6", "0.4"):
        limit = score["author_fit_tiers"][tier]
        if all(
            metric["nrmse"] <= limit["nrmse_max"]
            and metric["nmae"] <= limit["nmae_max"]
            and metric["normalized_absolute_bias"] <= limit["nbias_max"]
            and metric["correlation"] >= limit["correlation_min"]
            for metric in author_metrics.values()
        ):
            return float(tier)
    return 0.2


def _degradation_cap(site_metrics: dict, score: dict) -> tuple[float, float]:
    worst = max(
        max(metric["rmse_relative_degradation"], metric["mae_relative_degradation"])
        for metric in site_metrics.values()
    )
    if worst > score["b_degradation_cap_0_2"]:
        return 0.2, worst
    if worst > score["b_degradation_cap_0_4"]:
        return 0.4, worst
    return 0.6, worst


def evaluate(output_dir: Path, reference_dir: Path) -> dict:
    stages = {
        "output_contract": False,
        "independent_superiority": False,
        "expert_agreement": False,
        "independent_degradation_cap": False,
    }
    metrics: dict[str, object] = {}
    try:
        core = _core(reference_dir)
        thresholds, independent, author, _public = core.load_private(reference_dir)
        score = thresholds["score_ladder_v2"]

        core.check_regular_exact(output_dir)
        _method_gate(output_dir / "method.json", thresholds, core)
        core.validate_figure_and_source(output_dir)
        candidate = core.load_candidate(output_dir, thresholds)
        stages["output_contract"] = True

        joined = (
            independent.merge(author, on=["site_id", "date"], validate="one_to_one")
            .merge(
                candidate,
                on=["site_id", "date"],
                suffixes=("_author", "_candidate"),
                validate="one_to_one",
            )
        )
        joined["year"] = pd.to_datetime(joined.date).dt.year
        joined["season"] = pd.to_datetime(joined.date).dt.month.map(core.season)

        site_metrics = {site: _gain(joined[joined.site_id.eq(site)]) for site in SITES}
        period_metrics = {}
        period_pass = True
        for site in SITES:
            for period, (start, end) in PERIODS.items():
                group = joined[joined.site_id.eq(site) & joined.year.between(start, end)].sort_values("date")
                metric = _gain(group)
                period_metrics[f"{site}|{period}"] = metric
                period_pass &= len(group) >= score["high_min_period_rows"] and _strict_gain(metric, score)

        season_metrics = {}
        season_pass = True
        for block in thresholds["s5_blocks"]:
            group = joined[
                joined.site_id.eq(block["site_id"]) & joined.season.eq(block["season"])
            ].sort_values("date")
            metric = _gain(group)
            author_error, candidate_error = _errors(group)
            rmse_lower, mae_lower = core.moving_block_lowers(
                author_error,
                candidate_error,
                pd.to_datetime(group.date).to_numpy(),
                score["bootstrap_block_length"],
                score["bootstrap_resamples"],
                block["seed"],
                score["bootstrap_quantile"],
            )
            metric["rmse_bootstrap_lower_w_m2"] = rmse_lower
            metric["mae_bootstrap_lower_w_m2"] = mae_lower
            season_metrics[f'{block["site_id"]}|{block["season"]}'] = metric
            season_pass &= bool(
                _strict_gain(metric, score)
                and rmse_lower > score["high_min_bootstrap_lower_gain_w_m2"]
                and mae_lower > score["high_min_bootstrap_lower_gain_w_m2"]
            )

        metrics["independent_site_comparison"] = site_metrics
        metrics["independent_station_period_comparison"] = period_metrics
        metrics["independent_station_season_comparison"] = season_metrics

        author_metrics = _author_metrics(author, candidate, core)
        metrics["expert_product_agreement"] = author_metrics
        base_tier = _low_tier(author_metrics, score)
        stages["expert_agreement"] = base_tier >= 0.4
        cap, worst_degradation = _degradation_cap(site_metrics, score)
        metrics["independent_degradation"] = {
            "worst_site_metric_relative_degradation": worst_degradation,
            "score_cap": cap,
        }
        stages["independent_degradation_cap"] = cap >= 0.4
        final = min(base_tier, cap)
        if final < 0.6:
            return _verdict(final, f"LOW_BRANCH_EXPERT_FIT_{base_tier:.1f}_B_CAP_{cap:.1f}", stages, metrics)
        if period_pass:
            stages["independent_superiority"] = True
            if season_pass:
                return _verdict(1.0, "ROBUST_SUPERIORITY_ALL_STATION_SEASONS", stages, metrics)
            return _verdict(0.8, "ROBUST_SUPERIORITY_ALL_STATION_PERIODS", stages, metrics)
        return _verdict(final, f"LOW_BRANCH_EXPERT_FIT_{base_tier:.1f}_B_CAP_{cap:.1f}", stages, metrics)
    except Exception as exc:
        core_error = getattr(locals().get("core", object()), "AgentOutputError", ())
        if core_error and isinstance(exc, core_error):
            return _verdict(0.0, str(exc), stages, metrics, status="agent_output_error")
        return {
            "schema_version": "2.0",
            "status": "evaluator_internal_error",
            "score": None,
            "level": None,
            "reason": str(exc) or "UNEXPECTED_EVALUATOR_FAILURE",
            "stage_results": stages,
            "metrics": {},
        }


def _verdict(score: float, reason: str, stages: dict, metrics: dict, status: str = "scored") -> dict:
    return {
        "schema_version": "2.0",
        "status": status,
        "score": score,
        "level": {0.0: "S0", 0.2: "S1", 0.4: "S2", 0.6: "S3", 0.8: "S4", 1.0: "S5"}[score],
        "reason": reason,
        "stage_results": stages,
        "metrics": metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.output_dir, args.reference_dir), ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
