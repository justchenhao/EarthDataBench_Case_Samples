"""Private cumulative evaluator for HUST-Grace2024 v0.24."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np


FILES = {
    "low_degree_monthly.csv",
    "degree_spectrum.csv",
    "method.json",
    "low_degree_validation.png",
    "solution.py",
}
LOW_COLUMNS = [
    "month",
    "author_c20_1e10",
    "enhanced_c20_1e10",
    "author_c30_1e10",
    "enhanced_c30_1e10",
]
SPECTRUM_COLUMNS = ["month", "degree", "rms_power", "formal_rms_power"]
REFERENCE_HASHES = {
    "author_c.csv": "2dc1f7112bf6ac094ee9b97937f98d7679b1ec3d0cbcf75eaed8ba833525c151",
    "author_spectrum.csv": "c8f08668c1058d6ea3876a9c9ad44745bd0229a058bac6121cde220a87359d2a",
    "tn14_c20.csv": "2348ba1a8496cc16bbf6e8502142eedf93a49bbb3458a22b2b7f27211635f8c3",
    "tn14_c30.csv": "4195a17944cfa84dd7061c195e836d409728a52f2667b5fde8037c022bcd448d",
}
METHOD_REQUIRED = {
    "schema_version": "hust-grace2024-v24-method-v1",
    "input_archive": "HUST-Grace2024-n60.zip",
    "archive_member_count": 255,
    "evaluation_window_count": 214,
    "normalization": "fully_normalized",
    "tide_system": "zero_tide",
}


class CandidateError(Exception):
    """An Agent-controlled delivery or product error."""


class EvaluatorError(Exception):
    """A private evaluator/reference failure."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path, columns: list[str], *, candidate: bool) -> list[dict[str, str]]:
    error = CandidateError if candidate else EvaluatorError
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != columns:
                raise error("CSV_SCHEMA_INVALID")
            rows = list(reader)
    except error:
        raise
    except Exception as exc:
        raise error("CSV_PARSE_FAILED") from exc
    return rows


def _number(value: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CandidateError("NUMERIC_VALUE_INVALID") from exc
    if not math.isfinite(number):
        raise CandidateError("NUMERIC_VALUE_INVALID")
    if minimum is not None and number < minimum:
        raise CandidateError("NUMERIC_RANGE_INVALID")
    if maximum is not None and number > maximum:
        raise CandidateError("NUMERIC_RANGE_INVALID")
    return number


def _png_shape(path: Path) -> tuple[int, int, int]:
    try:
        header = path.read_bytes()[:29]
    except OSError as exc:
        raise CandidateError("PNG_READ_FAILED") from exc
    if len(header) != 29 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise CandidateError("PNG_INVALID")
    width, height = struct.unpack(">II", header[16:24])
    colour_type = header[25]
    if colour_type not in {2, 6} or path.stat().st_size <= 1000:
        raise CandidateError("PNG_CONTRACT_INVALID")
    return width, height, colour_type


def _rmse(first: list[float], second: list[float]) -> float:
    if not first or len(first) != len(second):
        raise EvaluatorError("RMSE_SUPPORT_INVALID")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(first, second)) / len(first))


def _correlation(first: list[float], second: list[float]) -> float | None:
    if len(first) < 2 or len(first) != len(second):
        return None
    mean_x = sum(first) / len(first)
    mean_y = sum(second) / len(second)
    dx = [value - mean_x for value in first]
    dy = [value - mean_y for value in second]
    denominator = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    return sum(x * y for x, y in zip(dx, dy)) / denominator if denominator > 0 else None


def _moving_block_improvement(
    expert: list[float], candidate: list[float], observations: list[float]
) -> dict:
    """Frozen 12-month moving-block test of squared-error improvement."""
    expert_array = np.asarray(expert, dtype=np.float64)
    candidate_array = np.asarray(candidate, dtype=np.float64)
    observation_array = np.asarray(observations, dtype=np.float64)
    if expert_array.size != candidate_array.size or expert_array.size != observation_array.size:
        raise EvaluatorError("BLOCK_BOOTSTRAP_SUPPORT_MISMATCH")
    if expert_array.size < 12:
        raise EvaluatorError("BLOCK_BOOTSTRAP_SUPPORT_TOO_SMALL")
    delta = (expert_array - observation_array) ** 2 - (candidate_array - observation_array) ** 2
    block = 12
    replicates = 5000
    seed = 20261114
    rng = np.random.default_rng(seed)
    starts = rng.integers(
        0,
        delta.size - block + 1,
        size=(replicates, int(math.ceil(delta.size / block))),
    )
    means = np.asarray([
        np.concatenate([delta[start : start + block] for start in row]).mean()
        for row in starts
    ])
    return {
        "block_months": block,
        "replicates": replicates,
        "seed": seed,
        "statistic": "mean of monthly squared-error improvement; positive is better",
        "lower_95_percent": float(np.quantile(means, 0.025)),
        "median": float(np.median(means)),
        "positive_month_fraction": float(np.mean(delta > 0)),
    }


def _internal(reason: str, exc: Exception | None = None) -> dict:
    reasons = [reason]
    if exc is not None:
        reasons.append(type(exc).__name__)
    return {
        "status": "evaluator_internal_error",
        "score": None,
        "score_level": None,
        "checks": None,
        "metrics": {},
        "reason_codes": reasons,
    }


def _zero(reason: str, checks: dict[str, bool], metrics: dict) -> dict:
    return {
        "status": "scored",
        "score": 0.0,
        "score_level": "0.0",
        "checks": checks,
        "metrics": metrics,
        "reason_codes": [reason],
    }


def evaluate(output_dir: Path, reference_dir: Path) -> dict:
    checks = {f"score_{level:.1f}": False for level in (0.2, 0.4, 0.6, 0.8, 1.0)}
    metrics: dict = {}

    try:
        if not reference_dir.is_dir() or reference_dir.is_symlink():
            raise EvaluatorError("REFERENCE_ROOT_INVALID")
        for name, expected_hash in REFERENCE_HASHES.items():
            path = reference_dir / name
            if not path.is_file() or path.is_symlink() or _sha256(path) != expected_hash:
                raise EvaluatorError(f"REFERENCE_INVALID:{name}")
        author_rows = _read_csv(
            reference_dir / "author_c.csv",
            ["month", "c20", "formal_sigma_c20", "c30", "formal_sigma_c30"],
            candidate=False,
        )
        author_spectrum = _read_csv(reference_dir / "author_spectrum.csv", SPECTRUM_COLUMNS, candidate=False)
        b20_rows = _read_csv(reference_dir / "tn14_c20.csv", ["month", "c20"], candidate=False)
        b30_rows = _read_csv(reference_dir / "tn14_c30.csv", ["month", "c30"], candidate=False)
    except Exception as exc:
        return _internal("PRIVATE_REFERENCE_ERROR", exc)

    try:
        if not output_dir.is_dir() or output_dir.is_symlink():
            raise CandidateError("OUTPUT_DIRECTORY_INVALID")
        entries = list(output_dir.iterdir())
        if {path.name for path in entries} != FILES or any(not path.is_file() or path.is_symlink() for path in entries):
            raise CandidateError("OUTPUT_FILE_SET_INVALID")
        source = (output_dir / "solution.py").read_text(encoding="utf-8")
        compile(source, "solution.py", "exec")
        low_rows = _read_csv(output_dir / "low_degree_monthly.csv", LOW_COLUMNS, candidate=True)
        spectrum_rows = _read_csv(output_dir / "degree_spectrum.csv", SPECTRUM_COLUMNS, candidate=True)
        method = json.loads((output_dir / "method.json").read_text(encoding="utf-8"))
        if not isinstance(method, dict):
            raise CandidateError("METHOD_SCHEMA_INVALID")
        if any(type(method.get(key)) is not type(value) or method.get(key) != value for key, value in METHOD_REQUIRED.items()):
            raise CandidateError("METHOD_SCHEMA_INVALID")
        width, height, colour_type = _png_shape(output_dir / "low_degree_validation.png")

        expected_months = [row["month"] for row in author_rows]
        months = [row["month"] for row in low_rows]
        if len(low_rows) != 214 or months != expected_months or len(set(months)) != 214:
            raise CandidateError("MONTH_SUPPORT_INVALID")
        low_values: dict[str, dict[str, float]] = {}
        for row in low_rows:
            low_values[row["month"]] = {
                column: _number(row[column], minimum=-1000.0, maximum=1000.0)
                for column in LOW_COLUMNS[1:]
            }

        expected_spectrum_keys = [(month, degree) for month in expected_months for degree in range(2, 61)]
        spectrum_keys: list[tuple[str, int]] = []
        spectrum_values: dict[tuple[str, int], tuple[float, float]] = {}
        for row in spectrum_rows:
            try:
                degree = int(row["degree"])
            except ValueError as exc:
                raise CandidateError("DEGREE_INVALID") from exc
            key = (row["month"], degree)
            spectrum_keys.append(key)
            spectrum_values[key] = (
                _number(row["rms_power"], minimum=0.0, maximum=1.0),
                _number(row["formal_rms_power"], minimum=0.0, maximum=1.0),
            )
        if len(spectrum_rows) != 12626 or spectrum_keys != expected_spectrum_keys or len(spectrum_values) != 12626:
            raise CandidateError("SPECTRUM_SUPPORT_INVALID")
    except CandidateError as exc:
        return _zero(str(exc), checks, metrics)
    except (OSError, UnicodeError, json.JSONDecodeError, SyntaxError) as exc:
        return _zero("OUTPUT_PARSE_FAILED", checks, {"error_type": type(exc).__name__})
    except Exception as exc:
        return _internal("EVALUATOR_EXECUTION_ERROR", exc)

    checks["score_0.2"] = True
    metrics.update({
        "public_months": len(low_rows),
        "spectrum_rows": len(spectrum_rows),
        "figure_width": width,
        "figure_height": height,
        "figure_colour_type": colour_type,
    })

    try:
        author_by_month = {row["month"]: row for row in author_rows}
        means = {
            variable: sum(float(row[variable]) for row in author_rows) / len(author_rows)
            for variable in ("c20", "c30")
        }
        expert_low = {
            month: {
                variable: (float(author_by_month[month][variable]) - means[variable]) * 1e10
                for variable in ("c20", "c30")
            }
            for month in expected_months
        }
        low_errors = []
        for month in expected_months:
            low_errors.extend([
                abs(low_values[month]["author_c20_1e10"] - expert_low[month]["c20"]),
                abs(low_values[month]["author_c30_1e10"] - expert_low[month]["c30"]),
            ])
        reference_spectrum = {
            (row["month"], int(row["degree"])): (float(row["rms_power"]), float(row["formal_rms_power"]))
            for row in author_spectrum
        }
        if list(reference_spectrum) != expected_spectrum_keys:
            raise EvaluatorError("AUTHOR_SPECTRUM_SUPPORT_INVALID")
        spectrum_errors = [
            abs(submitted - trusted)
            for key in expected_spectrum_keys
            for submitted, trusted in zip(spectrum_values[key], reference_spectrum[key])
        ]
        metrics["expert_product_gap"] = {
            "low_degree_max_abs_error_1e10": max(low_errors),
            "low_degree_rmse_1e10": math.sqrt(sum(value * value for value in low_errors) / len(low_errors)),
            "spectrum_max_abs_error": max(spectrum_errors),
            "spectrum_rmse": math.sqrt(sum(value * value for value in spectrum_errors) / len(spectrum_errors)),
        }

        independent: dict[str, dict] = {}
        for variable, rows, enhanced_column in (
            ("c20", b20_rows, "enhanced_c20_1e10"),
            ("c30", b30_rows, "enhanced_c30_1e10"),
        ):
            b_values = {row["month"]: float(row[variable]) for row in rows}
            common = sorted(set(expected_months) & set(b_values))
            observations = [(b_values[month] - means[variable]) * 1e10 for month in common]
            expert = [expert_low[month][variable] for month in common]
            candidate = [low_values[month][enhanced_column] for month in common]
            expert_rmse = _rmse(expert, observations)
            candidate_rmse = _rmse(candidate, observations)
            independent[variable] = {
                "matched_rows": len(common),
                "expert_rmse": expert_rmse,
                "candidate_rmse": candidate_rmse,
                "candidate_minus_expert_rmse": candidate_rmse - expert_rmse,
                "rmse_gain": expert_rmse - candidate_rmse,
                "relative_rmse_gain": (expert_rmse - candidate_rmse) / max(expert_rmse, 1e-15),
                "expert_correlation": _correlation(expert, observations),
                "candidate_correlation": _correlation(candidate, observations),
            }
            independent[variable]["block_bootstrap"] = _moving_block_improvement(
                expert, candidate, observations
            )
        metrics["independent_validation"] = independent
    except Exception as exc:
        return _internal("PRIVATE_COMPARISON_ERROR", exc)

    c_gap = metrics["expert_product_gap"]
    checks["score_0.4"] = (
        c_gap["low_degree_max_abs_error_1e10"] <= 0.1
        and c_gap["spectrum_max_abs_error"] <= 0.001
    )
    c_0_6 = (
        checks["score_0.4"]
        and c_gap["low_degree_max_abs_error_1e10"] <= 1e-10
        and c_gap["spectrum_max_abs_error"] <= 1e-12
    )
    b_metrics = metrics["independent_validation"]
    b_noninferior = all(
        values["matched_rows"] >= 20
        and values["candidate_rmse"] <= 1.05 * values["expert_rmse"]
        for values in b_metrics.values()
    )
    checks["score_0.6"] = c_0_6 and b_noninferior
    checks["score_0.8"] = checks["score_0.6"] and all(
        values["matched_rows"] >= 20
        and values["rmse_gain"] > 0.0
        and values["block_bootstrap"]["lower_95_percent"] > 0.0
        for values in b_metrics.values()
    )
    checks["score_1.0"] = (
        checks["score_0.8"]
        and b_metrics["c20"]["relative_rmse_gain"] >= 0.002
        and b_metrics["c30"]["relative_rmse_gain"] >= 0.10
    )

    score = next(
        (level for level in (1.0, 0.8, 0.6, 0.4, 0.2) if checks[f"score_{level:.1f}"]),
        0.0,
    )
    reason = {
        0.2: "VALID_DELIVERY_EXPERT_GAP_LARGE",
        0.4: "COARSE_EXPERT_FIT_INDEPENDENT_GAP_REPORTED",
        0.6: "EXPERT_REPLAY_NO_INDEPENDENT_SUPERIORITY",
        0.8: "INDEPENDENT_SUPERIORITY",
        1.0: "STRONG_INDEPENDENT_SUPERIORITY",
    }[score]
    if c_0_6 and not b_noninferior:
        reason = "BOUNDARY_C_PASSED_BUT_B_NONINFERIORITY_FAILED"
    return {
        "status": "scored",
        "score": score,
        "score_level": f"{score:.1f}",
        "checks": checks,
        "metrics": metrics,
        "reason_codes": [reason],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(evaluate(arguments.output_dir, arguments.reference_dir), sort_keys=True))
