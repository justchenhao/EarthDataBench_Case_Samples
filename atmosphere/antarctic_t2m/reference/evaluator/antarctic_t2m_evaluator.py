#!/usr/bin/env python3
"""Core evaluator for the Antarctic monthly T2m reconstruction task."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset, date2num, num2date
from PIL import Image


DEFAULT_CONFIG = "reference/evaluator_config.json"


class EvaluatorFault(RuntimeError):
    """A failure in trusted evaluator resources or configuration."""


class AgentFailure(RuntimeError):
    """A failure caused by the submitted delivery."""


@dataclass
class TrustedResources:
    config: dict[str, Any]
    template_lat: np.ndarray
    template_lon: np.ndarray
    template_hgt: np.ndarray
    template_landmask: np.ndarray
    core_mask: np.ndarray
    coverage_mask: np.ndarray
    validation_mask: np.ndarray
    reference: np.ndarray
    station_records: dict[str, dict[tuple[int, int], float]]
    task_years: np.ndarray
    task_months: np.ndarray
    reference_filled_cell_count: int


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return _finite_float(value)
    return value


def _load_station_file(path: Path) -> dict[tuple[int, int], float]:
    values: dict[tuple[int, int], float] = {}
    try:
        lines = path.read_text(encoding="latin-1").splitlines()[1:]
    except OSError as exc:
        raise EvaluatorFault(f"independent station file unreadable: {path}: {exc}") from exc
    for line in lines:
        fields = line.split()
        if not fields or not fields[0].isdigit():
            continue
        year = int(fields[0])
        for month, token in enumerate(fields[1:13], start=1):
            values[(year, month)] = float(token) if token != "-" else math.nan
    if not values:
        raise EvaluatorFault(f"independent station file has no parsable values: {path}")
    return values


def _read_target(variable: Any) -> np.ndarray:
    raw = variable[:]
    if np.ma.isMaskedArray(raw):
        return np.asarray(raw.filled(np.nan), dtype=np.float64)
    result = np.asarray(raw, dtype=np.float64)
    fill = getattr(variable, "_FillValue", None)
    if fill is not None:
        result[result == float(fill)] = np.nan
    missing = getattr(variable, "missing_value", None)
    if missing is not None:
        result[result == float(missing)] = np.nan
    return result


def _monthly_keys(start: datetime, end: datetime) -> list[tuple[int, int]]:
    if start.day != 1 or end.day != 1 or (end.year, end.month) < (start.year, start.month):
        raise EvaluatorFault("expectedTime must use ordered first-of-month dates")
    keys = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return keys


def _preflight(repo: Path, config_path: Path) -> TrustedResources:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise EvaluatorFault(f"private evaluator configuration unreadable: {exc}") from exc
    required = {"taskId", "template", "authorProduct", "authorVariable", "independentStations",
                "independentValidationProtocol", "independentValidationMetrics", "expectedTime",
                "discreteScoring", "evaluatorVersion", "validationFidelity", "maxScore"}
    scoring = config.get("discreteScoring", {})
    low = scoring.get("lowBranch", {})
    stages = scoring.get("stages", {})
    expected_stages = {"S1": 0.2, "S2": 0.4, "S3": 0.6, "S4": 0.8, "S5": 1.0}
    configured_stages = {name: stage.get("score") for name, stage in stages.items()
                         if isinstance(stage, dict)}
    rule = str(low.get("rule", "")).replace(" ", "").replace("_", "").lower()
    if (not required.issubset(config) or configured_stages != expected_stages or
            scoring.get("allowedScores") != [0.0, 0.2, 0.4, 0.6, 0.8, 1.0] or
            scoring.get("cumulative") is not True or scoring.get("expertReferenceAnchor") != 0.6 or
            rule != "min(productconsistencytier,independentvalidationcap)" or
            set(low.get("productConsistencyTiers", {})) != {"0.2", "0.4", "0.6"} or
            set(low.get("independentValidationCaps", {})) != {"0.4", "0.6"} or
            len(config["independentStations"]) != 34 or float(config["maxScore"]) not in {0.6, 1.0}):
        raise EvaluatorFault("private evaluator configuration is incomplete or invalid")

    try:
        expected_start = datetime.fromisoformat(config["expectedTime"]["start"])
        expected_end = datetime.fromisoformat(config["expectedTime"]["end"])
        task_keys = _monthly_keys(expected_start, expected_end)
    except (KeyError, TypeError, ValueError) as exc:
        raise EvaluatorFault(f"invalid expectedTime configuration: {exc}") from exc
    if len(task_keys) != int(config["expectedTime"]["count"]):
        raise EvaluatorFault("expectedTime count does not match its monthly date range")
    protocol = config["independentValidationProtocol"]
    protocol_required = {"landmaskMinimum", "maxMatchingDistanceKm", "minimumPairedMonths",
                         "minimumUsableStations", "minimumMonthsPerAnnualMean", "minimumTrendYears"}
    if not protocol_required.issubset(protocol):
        raise EvaluatorFault("independent validation protocol is incomplete")

    template_path = repo / config["template"]
    reference_path = repo / config["authorProduct"]
    station_root = repo / config["independentDataRoot"]
    try:
        with Dataset(template_path) as ds:
            lat = np.asarray(ds.variables["lat"][:], dtype=np.float32)
            lon = np.asarray(ds.variables["lon"][:], dtype=np.float32)
            hgt = np.asarray(ds.variables["HGT"][:], dtype=np.float32)
            land = np.asarray(ds.variables["LANDMASK"][:], dtype=np.float32)
    except Exception as exc:
        raise EvaluatorFault(f"required public grid template unreadable: {exc}") from exc
    if lat.shape != (114, 114) or any(x.shape != lat.shape for x in (lon, hgt, land)):
        raise EvaluatorFault("trusted template has an invalid grid shape")
    core = np.isfinite(land) & (land >= 0.5)
    coverage = np.isfinite(land) & (land >= float(protocol["landmaskMinimum"]))
    if int(core.sum()) < 1000:
        raise EvaluatorFault("trusted template land core is invalid")
    if int(coverage.sum()) < int(core.sum()):
        raise EvaluatorFault("station-validation support cannot be smaller than the land core")

    try:
        with Dataset(reference_path) as ds:
            time = ds.variables["time"]
            dates = num2date(time[:], units=time.units, calendar=getattr(time, "calendar", "standard"))
            lookup = {(int(date.year), int(date.month)): index for index, date in enumerate(dates)}
            missing = [key for key in task_keys if key not in lookup]
            if missing:
                raise EvaluatorFault(f"author product does not cover task months: {missing[:3]}")
            reference = _read_target(ds.variables[config["authorVariable"]])[
                [lookup[key] for key in task_keys]
            ]
    except Exception as exc:
        raise EvaluatorFault(f"author reference product unreadable: {exc}") from exc
    if reference.shape != (len(task_keys), 114, 114) or not np.all(np.isfinite(reference[:, core])):
        raise EvaluatorFault("author reference product has invalid shape or core coverage")
    complete_reference = np.all(np.isfinite(reference), axis=0)
    incomplete_coverage_cells = np.argwhere(coverage & ~complete_reference)
    for row, column in incomplete_coverage_cells:
        source_row, source_column, _ = _nearest_supported_index(
            lat, lon, complete_reference, float(lat[row, column]), float(lon[row, column])
        )
        missing = ~np.isfinite(reference[:, row, column])
        reference[missing, row, column] = reference[missing, source_row, source_column]
    validation = coverage & np.all(np.isfinite(reference), axis=0)
    if int(validation.sum()) < int(core.sum()):
        raise EvaluatorFault("author product has insufficient finite coastal validation support")

    records = {}
    for station in config["independentStations"]:
        if station.get("availableForReplay", True):
            records[station["file"]] = _load_station_file(station_root / station["file"])
    years = np.asarray([key[0] for key in task_keys], dtype=np.int32)
    months = np.asarray([key[1] for key in task_keys], dtype=np.int8)
    return TrustedResources(config, lat, lon, hgt, land, core, coverage, validation,
                            reference, records, years, months, len(incomplete_coverage_cells))


def _validate_artifacts(submission: Path, resources: TrustedResources) -> tuple[np.ndarray, dict[str, Any]]:
    cfg = resources.config
    time_count = len(resources.task_years)
    output = submission / "output"
    product = submission / cfg["formalProduct"]
    figure = output / "representative.png"
    report = output / "method_report.md"
    reproduce = output / "reproduce.py"
    for path in (product, figure, report, reproduce):
        if not path.is_file():
            raise AgentFailure(f"missing required artifact: {path.relative_to(submission)}")
    if report.stat().st_size < 200:
        raise AgentFailure("method_report.md is empty or uninformative")
    if reproduce.stat().st_size < 200:
        raise AgentFailure("reproduce.py is empty or uninformative")
    try:
        with Image.open(figure) as image:
            image.verify()
        with Image.open(figure) as image:
            width, height = image.size
            extrema = image.convert("RGB").getextrema()
    except Exception as exc:
        raise AgentFailure(f"representative figure is invalid: {exc}") from exc
    if all(lo == hi for lo, hi in extrema):
        raise AgentFailure("representative figure fails nonblank-content requirements")

    try:
        with Dataset(product) as ds:
            if ds.data_model not in {"NETCDF4", "NETCDF4_CLASSIC"}:
                raise AgentFailure(f"main product is not NETCDF4: {ds.data_model}")
            required_vars = {"time", "lat", "lon", "HGT", "LANDMASK", cfg["targetVariable"]}
            if not required_vars.issubset(ds.variables):
                raise AgentFailure("main product is missing one or more required variables")
            var = ds.variables[cfg["targetVariable"]]
            if (tuple(var.dimensions) != ("time", "south_north", "west_east") or
                    var.shape != (time_count, 114, 114)):
                raise AgentFailure("target variable dimensions or shape do not match the contract")
            if np.dtype(var.dtype) != np.dtype("float32") or getattr(var, "units", None) != "K":
                raise AgentFailure("target variable dtype or units do not match the contract")
            if abs(float(getattr(var, "_FillValue", math.nan)) - (-999.9)) > 1e-3:
                raise AgentFailure("target variable fill value does not match the contract")
            for name, trusted in (("lat", resources.template_lat), ("lon", resources.template_lon),
                                  ("HGT", resources.template_hgt), ("LANDMASK", resources.template_landmask)):
                submitted = np.asarray(ds.variables[name][:], dtype=np.float32)
                if submitted.shape != (114, 114) or not np.array_equal(submitted, trusted, equal_nan=True):
                    raise AgentFailure(f"{name} does not exactly equal the public grid template")
            time_var = ds.variables["time"]
            if tuple(time_var.dimensions) != ("time",) or np.dtype(time_var.dtype) != np.dtype("float64"):
                raise AgentFailure("time coordinate dimensions or dtype do not match the contract")
            units = getattr(time_var, "units", "")
            calendar = getattr(time_var, "calendar", "standard")
            expected_dates = [datetime(int(year), int(month), 1)
                              for year, month in zip(resources.task_years, resources.task_months)]
            try:
                expected_time = date2num(expected_dates, units=units, calendar=calendar)
            except Exception as exc:
                raise AgentFailure(f"time units/calendar are invalid: {exc}") from exc
            if units != cfg["expectedTime"]["units"] or calendar != "standard":
                raise AgentFailure("time units or calendar do not match the contract")
            if not np.array_equal(np.asarray(time_var[:], dtype=np.float64), np.asarray(expected_time, dtype=np.float64)):
                raise AgentFailure("time coordinate is not the configured complete monthly task axis")
            target = _read_target(var)
    except AgentFailure:
        raise
    except Exception as exc:
        raise AgentFailure(f"main product is unreadable or malformed: {exc}") from exc

    core = resources.core_mask
    coverage = resources.coverage_mask
    if not np.all(np.isfinite(target[:, coverage])):
        threshold = resources.config["independentValidationProtocol"]["landmaskMinimum"]
        raise AgentFailure(f"target has incomplete finite coverage where LANDMASK >= {threshold}")
    outside_finite = np.isfinite(target[:, ~core])
    if outside_finite.size and not np.all(outside_finite == outside_finite[0]):
        raise AgentFailure("target has a time-varying missing-value mask outside the core")
    hard_max = float(cfg["physicalLimits"]["absoluteAnomalyHardMaxK"])
    if float(np.max(np.abs(target[:, core]))) > hard_max:
        raise AgentFailure("target contains physically implausible anomalies beyond the hard limit")
    if float(np.std(target[:, core])) < float(cfg["physicalLimits"]["minimumTargetStandardDeviationK"]):
        raise AgentFailure("target is degenerate or nearly constant")
    return target, {"figureWidth": width, "figureHeight": height, "methodReportBytes": report.stat().st_size,
                    "reproductionCodeBytes": reproduce.stat().st_size}


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    valid = np.isfinite(a) & np.isfinite(b)
    if int(valid.sum()) < 3:
        return math.nan
    av = a[valid] - np.mean(a[valid])
    bv = b[valid] - np.mean(b[valid])
    denom = math.sqrt(float(np.dot(av, av) * np.dot(bv, bv)))
    return float(np.dot(av, bv) / denom) if denom > 0 else math.nan


def _slope_per_decade(years: np.ndarray, values: np.ndarray) -> float:
    valid = np.isfinite(values)
    if int(valid.sum()) < 3:
        return math.nan
    x = np.asarray(years[valid], dtype=np.float64)
    y = np.asarray(values[valid], dtype=np.float64)
    x -= np.mean(x)
    return float(np.dot(x, y - np.mean(y)) / np.dot(x, x) * 10.0)


def _detrend_slope_only(time_index: np.ndarray, values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64).copy()
    valid = np.isfinite(result)
    x = np.asarray(time_index, dtype=np.float64)
    xc = x[valid] - np.mean(x[valid])
    slope = np.dot(xc, result[valid] - np.mean(result[valid])) / np.dot(xc, xc)
    result[valid] -= slope * xc
    return result


def _nearest_supported_index(lat: np.ndarray, lon: np.ndarray, support: np.ndarray, latitude: float,
                             longitude: float) -> tuple[int, int, float]:
    p0 = math.radians(latitude)
    p = np.deg2rad(lat.astype(np.float64))
    dl = np.deg2rad(((lon.astype(np.float64) - longitude + 180.0) % 360.0) - 180.0)
    cosine = np.sin(p0) * np.sin(p) + math.cos(p0) * np.cos(p) * np.cos(dl)
    angular = np.arccos(np.clip(cosine, -1.0, 1.0))
    angular[~support] = np.inf
    row, column = np.unravel_index(int(np.argmin(angular)), angular.shape)
    return int(row), int(column), float(angular[row, column] * 6370.0)


def _station_metrics(field: np.ndarray, resources: TrustedResources) -> dict[str, Any]:
    rows = []
    trend_errors = []
    exclusions = []
    protocol = resources.config["independentValidationProtocol"]
    task_month_count = len(resources.task_years)
    minimum_pairs = min(int(protocol["minimumPairedMonths"]), task_month_count)
    for station in resources.config["independentStations"]:
        if not station.get("availableForReplay", True):
            exclusions.append({"name": station["name"], "reason": "validation record unavailable"})
            continue
        record = resources.station_records[station["file"]]
        row, col, distance = _nearest_supported_index(
            resources.template_lat, resources.template_lon, resources.validation_mask,
            station["latitude"], station["longitude"]
        )
        if distance > float(protocol["maxMatchingDistanceKm"]):
            exclusions.append({"name": station["name"], "reason": "no nearby supported grid cell",
                               "matchingDistanceKm": distance})
            continue
        climatology = []
        for month in range(1, 13):
            values = [record.get((year, month), math.nan) for year in range(1981, 2011)]
            climatology.append(float(np.nanmean(values)) if np.any(np.isfinite(values)) else math.nan)
        excluded = set(station.get("excludeYears", []))
        times, observations, predictions = [], [], []
        for index, (year, month) in enumerate(zip(resources.task_years, resources.task_months)):
            year, month = int(year), int(month)
            if year < station["startYear"] or year > station["endYear"]:
                continue
            if year in excluded:
                continue
            obs = record.get((year, month), math.nan)
            pred = float(field[index, row, col])
            if math.isfinite(obs) and math.isfinite(pred) and math.isfinite(climatology[month - 1]):
                times.append(index)
                observations.append(obs - climatology[month - 1])
                predictions.append(pred)
        t = np.asarray(times, dtype=np.float64)
        obs = np.asarray(observations, dtype=np.float64)
        pred = np.asarray(predictions, dtype=np.float64)
        if len(obs) < minimum_pairs:
            exclusions.append({"name": station["name"], "reason": "too few paired task-period months",
                               "pairedMonths": len(obs), "minimumRequired": minimum_pairs})
            continue
        obs_d = _detrend_slope_only(t, obs)
        pred_d = _detrend_slope_only(t, pred)
        obs_centered = obs_d - np.mean(obs_d)
        denominator = float(np.sum(obs_centered * obs_centered))
        if denominator <= 0:
            exclusions.append({"name": station["name"], "reason": "zero detrended observational variance"})
            continue
        metrics = {
            "name": station["name"], "count": len(obs), "gridRow": row, "gridColumn": col,
            "matchingDistanceKm": distance, "biasObsMinusProductK": float(np.mean(obs - pred)),
            "rmseK": float(np.sqrt(np.mean((obs - pred) ** 2))),
            "detrendedPearsonR": _correlation(obs_d, pred_d),
            "fractionalVarianceR2": float(1.0 - np.sum((obs_d - pred_d) ** 2) / denominator),
            "paper": station["paper"]
        }
        if "trend" in station:
            trend = station["trend"]
            paired_years = resources.task_years[t.astype(np.int64)]
            annual_years, annual_obs, annual_pred = [], [], []
            for year in sorted(set(int(value) for value in paired_years)):
                if year < trend["startYear"] or year > trend["endYear"]:
                    continue
                select = paired_years == year
                if int(select.sum()) < int(protocol["minimumMonthsPerAnnualMean"]):
                    continue
                annual_years.append(year)
                annual_obs.append(float(np.mean(obs[select])))
                annual_pred.append(float(np.mean(pred[select])))
            if len(annual_years) >= int(protocol["minimumTrendYears"]):
                product_trend = _slope_per_decade(np.asarray(annual_years), np.asarray(annual_pred))
                observation_trend = _slope_per_decade(np.asarray(annual_years), np.asarray(annual_obs))
                metrics["trendKPerDecade"] = {
                    "observation": observation_trend, "product": product_trend,
                    "paperObservation": trend["observation"],
                    "paperReconstruction": trend["reconstruction"],
                    "annualYearCount": len(annual_years),
                    "minimumMonthsPerAnnualMean": int(protocol["minimumMonthsPerAnnualMean"])
                }
                trend_errors.append(abs(product_trend - observation_trend))
        rows.append(metrics)
    if len(rows) < int(protocol["minimumUsableStations"]):
        raise EvaluatorFault("too few usable independent stations within the task period")
    trend_mae = float(np.mean(trend_errors)) if trend_errors else None
    return {
        "stations": rows,
        "excludedStations": exclusions,
        "aggregate": {
            "stationCount": len(rows),
            "meanBiasObsMinusProductK": float(np.mean([x["biasObsMinusProductK"] for x in rows])),
            "meanRmseK": float(np.mean([x["rmseK"] for x in rows])),
            "meanDetrendedPearsonR": float(np.mean([x["detrendedPearsonR"] for x in rows])),
            "meanFractionalVarianceR2": float(np.mean([x["fractionalVarianceR2"] for x in rows])),
            "absoluteBiasBelow1KCount": int(sum(abs(x["biasObsMinusProductK"]) < 1.0 for x in rows)),
            "correlationAtLeast0p7Count": int(sum(x["detrendedPearsonR"] >= 0.7 for x in rows)),
            "trendStationCount": len(trend_errors),
            "meanTrendAbsoluteErrorKPerDecade": trend_mae
        }
    }


def _field_metrics(candidate: np.ndarray, resources: TrustedResources) -> dict[str, Any]:
    core = resources.core_mask
    reference = resources.reference
    protocol = resources.config["independentValidationProtocol"]
    cand = candidate[:, core]
    ref = reference[:, core]
    error = cand - ref
    candidate_monthly = np.mean(cand, axis=1)
    reference_monthly = np.mean(ref, axis=1)
    annual_years, candidate_annual, reference_annual = [], [], []
    for year in sorted(set(int(value) for value in resources.task_years)):
        select = resources.task_years == year
        if int(select.sum()) < int(protocol["minimumMonthsPerAnnualMean"]):
            continue
        annual_years.append(year)
        candidate_annual.append(np.mean(cand[select], axis=0))
        reference_annual.append(np.mean(ref[select], axis=0))
    trend_rmse = None
    if len(annual_years) >= int(protocol["minimumTrendYears"]):
        x = np.asarray(annual_years, dtype=np.float64)
        x -= np.mean(x)
        denominator = float(np.dot(x, x))
        candidate_annual_array = np.asarray(candidate_annual)
        reference_annual_array = np.asarray(reference_annual)
        candidate_trend = np.tensordot(
            x, candidate_annual_array - candidate_annual_array.mean(axis=0), axes=(0, 0)
        ) / denominator * 10.0
        reference_trend = np.tensordot(
            x, reference_annual_array - reference_annual_array.mean(axis=0), axes=(0, 0)
        ) / denominator * 10.0
        trend_rmse = float(np.sqrt(np.mean((candidate_trend - reference_trend) ** 2)))

    base = ((resources.task_years >= 1981) & (resources.task_years <= 2010))
    complete_baseline = int(base.sum()) == 30 * 12
    candidate_closure = reference_closure = None
    if complete_baseline:
        candidate_base = cand[base].reshape(30, 12, -1)
        reference_base = ref[base].reshape(30, 12, -1)
        candidate_closure = float(np.mean(np.abs(candidate_base.mean(axis=0))))
        reference_closure = float(np.mean(np.abs(reference_base.mean(axis=0))))

    candidate_std, reference_std = [], []
    for month in range(1, 13):
        select = resources.task_months == month
        if int(select.sum()) >= 2:
            candidate_std.append(np.std(cand[select], axis=0))
            reference_std.append(np.std(ref[select], axis=0))
    seasonal_std_rmse = None
    if candidate_std:
        seasonal_std_rmse = float(np.sqrt(np.mean(
            (np.asarray(candidate_std) - np.asarray(reference_std)) ** 2
        )))
    return {
        "fieldRmseK": float(np.sqrt(np.mean(error * error))),
        "fieldMaeK": float(np.mean(np.abs(error))),
        "fieldCorrelation": _correlation(cand, ref),
        "domainMeanRmseK": float(np.sqrt(np.mean((candidate_monthly - reference_monthly) ** 2))),
        "domainMeanCorrelation": _correlation(candidate_monthly, reference_monthly),
        "trendRmseKPerDecade": trend_rmse,
        "trendYearCount": len(annual_years),
        "seasonalStdRmseK": seasonal_std_rmse,
        "baselineMeanAbsoluteK": candidate_closure,
        "referenceBaselineMeanAbsoluteK": reference_closure,
        "baselineClosureExcessK": (max(0.0, candidate_closure - reference_closure)
                                   if complete_baseline else None),
        "baselineClosureApplicable": complete_baseline
    }


def _independent_comparison(station: dict[str, Any], baseline_station: dict[str, Any]) -> dict[str, Any]:
    agg = station["aggregate"]
    base = baseline_station["aggregate"]
    candidate_rows = {row["name"]: row for row in station["stations"]}
    baseline_rows = {row["name"]: row for row in baseline_station["stations"]}
    rows = []
    for name in sorted(candidate_rows):
        candidate = candidate_rows[name]
        baseline = baseline_rows[name]
        row = {
            "region": name,
            "n": candidate["count"],
            "coverage": 1.0,
            "rmseK": {
                "agentMetric": candidate["rmseK"],
                "expertBaseline": baseline["rmseK"],
                "deficit": max(0.0, candidate["rmseK"] - baseline["rmseK"]),
                "gain": baseline["rmseK"] - candidate["rmseK"]
            },
            "detrendedPearsonR": {
                "agentMetric": candidate["detrendedPearsonR"],
                "expertBaseline": baseline["detrendedPearsonR"],
                "deficit": max(0.0, baseline["detrendedPearsonR"] - candidate["detrendedPearsonR"]),
                "gain": candidate["detrendedPearsonR"] - baseline["detrendedPearsonR"]
            }
        }
        if "trendKPerDecade" in candidate and "trendKPerDecade" in baseline:
            candidate_error = abs(candidate["trendKPerDecade"]["product"] -
                                  candidate["trendKPerDecade"]["observation"])
            baseline_error = abs(baseline["trendKPerDecade"]["product"] -
                                 baseline["trendKPerDecade"]["observation"])
            row["trendAbsoluteErrorKPerDecade"] = {
                "agentMetric": candidate_error,
                "expertBaseline": baseline_error,
                "deficit": max(0.0, candidate_error - baseline_error),
                "gain": baseline_error - candidate_error
            }
        rows.append(row)
    trend_count = min(int(agg["trendStationCount"]), int(base["trendStationCount"]))
    trend_available = trend_count > 0
    trend_denominator = base["meanTrendAbsoluteErrorKPerDecade"] if trend_available else None
    aggregate = {
        "stationCount": len(rows),
        "stationRmseRatio": agg["meanRmseK"] / base["meanRmseK"],
        "stationCorrelationGain": agg["meanDetrendedPearsonR"] - base["meanDetrendedPearsonR"],
        "stationCorrelationDrop": max(0.0, base["meanDetrendedPearsonR"] - agg["meanDetrendedPearsonR"]),
        "trendStationCount": trend_count,
        "stationTrendMaeRatio": (agg["meanTrendAbsoluteErrorKPerDecade"] / trend_denominator
                                 if trend_available and trend_denominator > 0 else None),
        "stationTrendMaeExcess": (max(0.0, agg["meanTrendAbsoluteErrorKPerDecade"] -
                                          base["meanTrendAbsoluteErrorKPerDecade"])
                                  if trend_available else None),
        "stationRmseImprovedFraction": float(np.mean([
            row["rmseK"]["gain"] > 0 for row in rows
        ])),
        "stationCorrelationImprovedFraction": float(np.mean([
            row["detrendedPearsonR"]["gain"] > 0 for row in rows
        ]))
    }
    selected = ("meanRmseK", "meanDetrendedPearsonR", "trendStationCount",
                "meanTrendAbsoluteErrorKPerDecade")
    return {
        "regions": rows,
        "aggregate": aggregate,
        "agentAggregate": {name: agg[name] for name in selected},
        "expertBaselineAggregate": {name: base[name] for name in selected},
        "excludedStations": station["excludedStations"]
    }


def _check(metric: str, actual: float | int, direction: str, threshold: float | int,
           score_effect: str) -> dict[str, Any]:
    if direction == "<=":
        passed = actual <= threshold
    elif direction == ">=":
        passed = actual >= threshold
    else:
        raise EvaluatorFault(f"unsupported comparison direction: {direction}")
    return {"metric": metric, "actual": actual, "direction": direction, "threshold": threshold,
            "scoreEffect": score_effect, "passed": bool(passed)}


def _product_tier_checks(field: dict[str, Any], limits: dict[str, Any],
                         score_effect: str) -> list[dict[str, Any]]:
    definitions = (
        ("fieldRmseK", "fieldRmseMax", "<="),
        ("fieldCorrelation", "fieldCorrelationMin", ">="),
        ("domainMeanRmseK", "domainMeanRmseMax", "<="),
        ("domainMeanCorrelation", "domainMeanCorrelationMin", ">="),
        ("trendRmseKPerDecade", "trendRmseMax", "<="),
        ("seasonalStdRmseK", "seasonalStdRmseMax", "<="),
        ("baselineClosureExcessK", "baselineClosureExcessMax", "<="),
    )
    checks = []
    for metric, threshold_name, direction in definitions:
        actual = field.get(metric)
        if actual is None:
            checks.append({"metric": f"product.{metric}", "actual": None, "direction": direction,
                           "threshold": limits[threshold_name], "scoreEffect": score_effect,
                           "passed": False})
        else:
            checks.append(_check(f"product.{metric}", actual, direction,
                                 float(limits[threshold_name]), score_effect))
    return checks


def _score_product_consistency(field: dict[str, Any], tiers: dict[str, Any]
                               ) -> tuple[float, list[dict[str, Any]]]:
    score = 0.0
    evaluations = []
    for label in ("0.2", "0.4", "0.6"):
        checks = _product_tier_checks(field, tiers[label], f"S_C_{label}")
        passed = all(check["passed"] for check in checks)
        evaluations.append({"score": float(label), "checks": checks, "passed": passed})
        if passed:
            score = float(label)
    return score, evaluations


def _independent_cap_checks(comparison: dict[str, Any], limits: dict[str, Any],
                            score_effect: str) -> list[dict[str, Any]]:
    aggregate = comparison["aggregate"]
    region_count = sum(
        region["rmseK"]["deficit"] <= float(limits["regionRmseDeficitMax"]) and
        region["detrendedPearsonR"]["deficit"] <= float(limits["regionCorrelationDeficitMax"])
        for region in comparison["regions"]
    )
    trend_excess = aggregate["stationTrendMaeExcess"]
    checks = [
        _check("independent.aggregate.stationRmseRatio", aggregate["stationRmseRatio"], "<=",
               float(limits["stationRmseRatioMax"]), score_effect),
        _check("independent.aggregate.stationCorrelationDrop", aggregate["stationCorrelationDrop"], "<=",
               float(limits["stationCorrelationDropMax"]), score_effect),
        _check("independent.support.stationCount", aggregate["stationCount"], ">=",
               int(limits["minimumUsableStations"]), score_effect),
        _check("independent.support.trendStationCount", aggregate["trendStationCount"], ">=",
               int(limits["minimumTrendStations"]), score_effect),
        _check("independent.regions.withinToleranceCount", region_count, ">=",
               int(limits["minimumRegionsWithinTolerance"]), score_effect),
    ]
    if trend_excess is None:
        checks.append({"metric": "independent.aggregate.stationTrendMaeExcess", "actual": None,
                       "direction": "<=", "threshold": limits["stationTrendMaeExcessMax"],
                       "scoreEffect": score_effect, "passed": False})
    else:
        checks.append(_check("independent.aggregate.stationTrendMaeExcess", trend_excess, "<=",
                             float(limits["stationTrendMaeExcessMax"]), score_effect))
    checks.extend([
        _check("independent.regions.rmseDeficit", max(
            region["rmseK"]["deficit"] for region in comparison["regions"]
        ), "<=", float(limits["regionRmseDeficitHardMax"]), score_effect),
        _check("independent.regions.correlationDeficit", max(
            region["detrendedPearsonR"]["deficit"] for region in comparison["regions"]
        ), "<=", float(limits["regionCorrelationDeficitHardMax"]), score_effect),
    ])
    return checks


def _score_independent_cap(comparison: dict[str, Any], caps: dict[str, Any]
                           ) -> tuple[float, list[dict[str, Any]]]:
    evaluations = []
    passed_by_score = {}
    for label in ("0.4", "0.6"):
        checks = _independent_cap_checks(comparison, caps[label], f"S_B_{label}")
        passed = all(check["passed"] for check in checks)
        evaluations.append({"score": float(label), "checks": checks, "passed": passed})
        passed_by_score[label] = passed
    score = 0.6 if passed_by_score["0.6"] else 0.4 if passed_by_score["0.4"] else 0.2
    return score, evaluations


def _high_branch_checks(comparison: dict[str, Any], limits: dict[str, Any],
                        score_effect: str) -> list[dict[str, Any]]:
    aggregate = comparison["aggregate"]
    definitions = (
        ("stationRmseRatio", "stationRmseRatioMax", "<="),
        ("stationCorrelationGain", "stationCorrelationGainMin", ">="),
        ("stationTrendMaeRatio", "stationTrendMaeRatioMax", "<="),
        ("stationRmseImprovedFraction", "stationRmseImprovedFractionMin", ">="),
        ("stationCorrelationImprovedFraction", "stationCorrelationImprovedFractionMin", ">="),
        ("stationCount", "minimumUsableStations", ">="),
        ("trendStationCount", "minimumTrendStations", ">="),
    )
    checks = []
    for metric, threshold_name, direction in definitions:
        actual = aggregate.get(metric)
        full_name = (f"independent.support.{metric}" if metric.endswith("Count")
                     else f"independent.aggregate.{metric}")
        if actual is None:
            checks.append({"metric": full_name, "actual": None, "direction": direction,
                           "threshold": limits[threshold_name], "scoreEffect": score_effect,
                           "passed": False})
        else:
            checks.append(_check(full_name, actual, direction, limits[threshold_name], score_effect))
    return checks


def _evaluate_stages(product_score: float, validation_score: float, low_score: float,
                     comparison: dict[str, Any], scoring: dict[str, Any], max_score: float
                     ) -> tuple[float, str, str, list[dict[str, Any]]]:
    stages = scoring["stages"]
    evaluations = []
    cumulative = True
    achieved_score, achieved_stage, score_level = 0.0, "S0", "no_scientific_skill"
    for name, threshold in (("S1", 0.2), ("S2", 0.4), ("S3", 0.6)):
        checks = [
            _check("product.productConsistencyTier", product_score, ">=", threshold, name),
            _check("independent.independentValidationCap", validation_score, ">=", threshold, name),
        ]
        own_pass = all(check["passed"] for check in checks)
        passed = cumulative and own_pass
        stage = stages[name]
        evaluations.append({"stage": name, "score": stage["score"],
                            "scoreLevel": stage["scoreLevel"],
                            "prerequisitesPassed": cumulative, "checks": checks,
                            "requirements": {check["metric"]: check["passed"] for check in checks},
                            "passed": passed})
        cumulative = passed
        if passed:
            achieved_score, achieved_stage = float(stage["score"]), name
            score_level = stage["scoreLevel"]

    if low_score != min(product_score, validation_score):
        raise EvaluatorFault("low-branch result disagrees with min(S_C,S_B)")
    if evaluations[1]["passed"] != (product_score >= 0.4 and validation_score >= 0.4):
        raise EvaluatorFault("S2 stage disagrees with the dual constraint")
    if evaluations[2]["passed"] != (product_score >= 0.6 and validation_score >= 0.6):
        raise EvaluatorFault("S3 stage disagrees with the dual constraint")

    for name in ("S4", "S5"):
        stage = stages[name]
        checks = _high_branch_checks(comparison, stage["thresholds"], name)
        own_pass = all(check["passed"] for check in checks) and float(stage["score"]) <= max_score
        passed = cumulative and own_pass
        evaluations.append({"stage": name, "score": stage["score"],
                            "scoreLevel": stage["scoreLevel"],
                            "prerequisitesPassed": cumulative, "checks": checks,
                            "requirements": {check["metric"]: check["passed"] for check in checks},
                            "passed": passed})
        cumulative = passed
        if passed:
            achieved_score, achieved_stage = float(stage["score"]), name
            score_level = stage["scoreLevel"]
    return achieved_score, achieved_stage, score_level, evaluations


def evaluate(repo: Path, submission: Path, config_path: Path) -> dict[str, Any]:
    resources = _preflight(repo, config_path)
    version = resources.config["evaluatorVersion"]
    try:
        candidate, artifact_diagnostics = _validate_artifacts(submission, resources)
    except AgentFailure as exc:
        return {"status": "agent_output_error", "score": 0.0, "score_level": "invalid_output",
                "evaluatorVersion": version,
                "product_vs_expert_reference": {}, "independent_validation": {},
                "stage_evaluation": {"achieved_stage": "S0", "stages": []}, "detail": str(exc)}
    field = _field_metrics(candidate, resources)
    station = _station_metrics(candidate, resources)
    baseline_station = _station_metrics(resources.reference, resources)
    comparison = _independent_comparison(station, baseline_station)
    scoring = resources.config["discreteScoring"]
    low_config = scoring["lowBranch"]
    product_score, product_evaluations = _score_product_consistency(
        field, low_config["productConsistencyTiers"]
    )
    validation_score, validation_evaluations = _score_independent_cap(
        comparison, low_config["independentValidationCaps"]
    )
    low_score = min(product_score, validation_score)
    score, achieved_stage, score_level, stage_evaluation = _evaluate_stages(
        product_score, validation_score, low_score, comparison, scoring,
        float(resources.config["maxScore"])
    )
    detail = "" if score else "submission did not reach S1 minimum scientific validity"
    return {
        "status": "scored",
        "score": score,
        "score_level": score_level,
        "evaluatorVersion": version,
        "validation_fidelity": resources.config["validationFidelity"],
        "max_score": resources.config["maxScore"],
        "product_vs_expert_reference": field,
        "independent_validation": comparison,
        "low_branch_scoring": {
            "rule": "min(product_consistency_tier, independent_validation_cap)",
            "product_consistency_tier": {"score": product_score, "tiers": product_evaluations},
            "independent_validation_cap": {"score": validation_score, "caps": validation_evaluations},
            "score": low_score,
        },
        "stage_evaluation": {"achieved_stage": achieved_stage, "stages": stage_evaluation},
        "detail": detail,
        "diagnostics": {
            "formalProductValidatedDirectly": True,
            "submittedIntermediateUsed": False,
            "artifacts": artifact_diagnostics,
            "stationCount": station["aggregate"]["stationCount"],
            "trendStationCount": station["aggregate"]["trendStationCount"],
            "maximumStationMatchingDistanceKm": max(
                row["matchingDistanceKm"] for row in station["stations"]
            ),
            "taskPeriod": {
                "start": f"{int(resources.task_years[0]):04d}-{int(resources.task_months[0]):02d}",
                "end": f"{int(resources.task_years[-1]):04d}-{int(resources.task_months[-1]):02d}",
                "months": len(resources.task_years)
            },
            "referenceCoastalCellsNormalized": resources.reference_filled_cell_count
        }
    }


def evaluate_safe(repo: Path, submission: Path, config_path: Path) -> dict[str, Any]:
    """Return the required machine result even when trusted evaluator state is faulty."""
    try:
        return evaluate(repo, submission, config_path)
    except EvaluatorFault as exc:
        return {"status": "evaluator_internal_error", "score": None, "score_level": None,
                "evaluatorVersion": None,
                "product_vs_expert_reference": {}, "independent_validation": {},
                "stage_evaluation": {}, "detail": str(exc)}
    except Exception as exc:
        return {"status": "evaluator_internal_error", "score": None, "score_level": None,
                "evaluatorVersion": None,
                "product_vs_expert_reference": {}, "independent_validation": {},
                "stage_evaluation": {},
                "detail": f"unexpected evaluator exception: {type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission-dir", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--result", type=Path, default=None)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    config = args.config.resolve() if args.config else repo / DEFAULT_CONFIG
    result = evaluate_safe(repo, args.submission_dir.resolve(), config)
    payload = json.dumps(_json_safe(result), ensure_ascii=False, indent=2, sort_keys=True)
    if args.result:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result["status"] in {"scored", "agent_output_error"} else 2


if __name__ == "__main__":
    sys.exit(main())
