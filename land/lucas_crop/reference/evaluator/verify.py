"""Private cumulative evaluator for the LUCAS crop-sequence Case."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image


class AgentOutputError(ValueError):
    pass


class PrivateReferenceError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ordinary_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PrivateReferenceError("PRIVATE_JSON_NOT_OBJECT")
    return value


def _check_reference(reference_dir: Path, specification: dict) -> Path:
    path = reference_dir / specification["path"]
    if not _ordinary_file(path) or _sha256(path) != specification["sha256"]:
        raise PrivateReferenceError("PRIVATE_REFERENCE_HASH_MISMATCH")
    return path


def _load_private(reference_dir: Path) -> tuple[dict, pd.DataFrame, dict, dict]:
    try:
        contract = _load_json(reference_dir / "evaluation_contract.json")
        references = contract["references"]
        expert_path = _check_reference(reference_dir, references["expert_product"])
        lpis_path = _check_reference(reference_dir, references["lpis_targets"])
        eurostat_path = _check_reference(reference_dir, references["eurostat_support"])
        _check_reference(reference_dir, references["reference_visualization"])
        expert = pd.read_csv(expert_path, dtype=str, keep_default_na=False, na_filter=False)
        if tuple(expert.columns) != tuple(contract["output"]["columns"]):
            raise PrivateReferenceError("INVALID_EXPERT_SCHEMA")
        if len(expert) != int(contract["output"]["row_count"]):
            raise PrivateReferenceError("INVALID_EXPERT_ROWS")
        lpis = _load_json(lpis_path)
        eurostat = _load_json(eurostat_path)
        if [block["block_id"] for block in lpis["blocks"]] != contract["block_order"]:
            raise PrivateReferenceError("INVALID_BLOCK_ORDER")
        return contract, expert, lpis, eurostat
    except PrivateReferenceError:
        raise
    except Exception as exc:
        raise PrivateReferenceError("PRIVATE_REFERENCE_INVALID") from exc


def _check_delivery(output_dir: Path, contract: dict) -> None:
    output = contract["output"]
    for key in ("product", "code", "report", "figure"):
        path = output_dir / output[key]
        if not _ordinary_file(path):
            raise AgentOutputError(f"MISSING_OR_UNSAFE_{key.upper()}")
    if (output_dir / output["code"]).stat().st_size < int(output["code_min_bytes"]):
        raise AgentOutputError("MISSING_OR_SHORT_CODE")
    if (output_dir / output["report"]).stat().st_size < int(output["report_min_bytes"]):
        raise AgentOutputError("MISSING_OR_SHORT_REPORT")
    try:
        with Image.open(output_dir / output["figure"]) as image:
            if image.format != "PNG":
                raise AgentOutputError("INVALID_FIGURE")
            image.verify()
    except AgentOutputError:
        raise
    except Exception as exc:
        raise AgentOutputError("UNREADABLE_FIGURE") from exc


def _load_candidate(output_dir: Path, contract: dict) -> pd.DataFrame:
    _check_delivery(output_dir, contract)
    path = output_dir / contract["output"]["product"]
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    except Exception as exc:
        raise AgentOutputError("UNPARSEABLE_PRODUCT") from exc
    if tuple(frame.columns) != tuple(contract["output"]["columns"]):
        raise AgentOutputError("INVALID_SCHEMA")
    if len(frame) != int(contract["output"]["row_count"]):
        raise AgentOutputError("INVALID_ROW_COUNT")
    try:
        point_ids = pd.to_numeric(frame["point_id"], errors="raise").to_numpy(dtype=np.int64)
    except Exception as exc:
        raise AgentOutputError("INVALID_POINT_ID") from exc
    if len(np.unique(point_ids)) != len(point_ids) or np.any(point_ids[1:] <= point_ids[:-1]):
        raise AgentOutputError("INVALID_POINT_KEYS")
    frame["point_id"] = point_ids
    for field in contract["numeric_columns"]:
        text = frame[field].str.strip()
        try:
            values = pd.to_numeric(text, errors="raise").to_numpy(dtype=float)
        except Exception as exc:
            raise AgentOutputError(f"INVALID_NUMERIC_{field.upper()}") from exc
        if not np.isfinite(values).all():
            raise AgentOutputError(f"NONFINITE_{field.upper()}")
        frame[field] = values
    if not frame["crop_sequence_type"].isin(contract["class_order"]).all():
        raise AgentOutputError("INVALID_CLASS_LABEL")
    return frame


def _categorical_metrics(reference: pd.Series, candidate: pd.Series, labels: list[str]) -> dict:
    confusion = np.zeros((len(labels), len(labels)), dtype=int)
    lookup = {label: index for index, label in enumerate(labels)}
    for left, right in zip(reference, candidate):
        confusion[lookup[left], lookup[right]] += 1
    support = confusion.sum(axis=1)
    predicted = confusion.sum(axis=0)
    true_positive = np.diag(confusion).astype(float)
    recall = np.divide(true_positive, support, out=np.zeros_like(true_positive), where=support > 0)
    precision = np.divide(true_positive, predicted, out=np.zeros_like(true_positive), where=predicted > 0)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros_like(recall), where=(precision + recall) > 0)
    return {
        "accuracy": float(true_positive.sum() / confusion.sum()),
        "macro_f1": float(f1.mean()),
        "minimum_class_recall": float(recall.min()),
        "per_class_recall": {label: float(recall[index]) for index, label in enumerate(labels)},
        "confusion_matrix": confusion.tolist(),
    }


def _total_variation(candidate_counts: np.ndarray, target: np.ndarray) -> float:
    proportions = candidate_counts / candidate_counts.sum()
    return float(0.5 * np.abs(proportions - target).sum())


def _block_metrics(candidate: pd.DataFrame, lpis: dict, labels: list[str]) -> dict:
    output = {}
    for block in lpis["blocks"]:
        selected = candidate[candidate["nuts3"] == block["public_a_nuts3"]]
        counts = selected["crop_sequence_type"].value_counts().reindex(labels, fill_value=0).to_numpy(dtype=int)
        if len(selected) != int(block["public_a_points"]):
            raise PrivateReferenceError("CANDIDATE_BLOCK_SUPPORT_CHANGED_AFTER_S1")
        distance = _total_variation(counts, np.asarray(block["target_proportions"], dtype=float))
        gain = float(block["author_total_variation"] - distance)
        output[block["block_id"]] = {
            "tier": block["tier"],
            "candidate_counts": counts.tolist(),
            "candidate_total_variation": distance,
            "author_total_variation": float(block["author_total_variation"]),
            "attainable_total_variation": float(block["attainable_total_variation"]),
            "total_variation_gain": gain,
            "required_gain": float(block["required_gain"]),
            "strict_gain_passed": gain > float(block["required_gain"]),
        }
    return output


def _semantic_checks(candidate: pd.DataFrame, contract: dict) -> dict:
    labels = contract["class_order"]
    features = contract["feature_order"]
    centroids = candidate.groupby("crop_sequence_type")[features].mean().reindex(labels)
    checks = {}
    for label, named_feature in contract["label_feature"].items():
        values = centroids.loc[label]
        if label == "cereals":
            passed = values["cereals"] > values.drop("cereals").max()
        else:
            non_cereal = values.drop("cereals")
            passed = non_cereal[named_feature] > non_cereal.drop(named_feature).max()
        checks[label] = {
            "named_feature": named_feature,
            "named_feature_mean": float(values[named_feature]),
            "passed": bool(passed),
        }
    return {"per_label": checks, "all_passed": all(item["passed"] for item in checks.values())}


def _r_squared(left: np.ndarray, right: np.ndarray) -> float | None:
    finite = np.isfinite(left) & np.isfinite(right)
    left = left[finite]
    right = right[finite]
    if len(left) < 2 or np.std(left) == 0 or np.std(right) == 0:
        return None
    correlation = float(np.corrcoef(left, right)[0, 1])
    return correlation * correlation


def _eurostat_metrics(candidate: pd.DataFrame, support: dict, features: list[str]) -> dict:
    means = candidate.groupby("nuts0")[features].mean()
    means.loc["EU"] = candidate[features].mean()
    rows = []
    for geo, values in support["geographies"].items():
        if geo not in means.index:
            continue
        for feature in features:
            observed = values["observed"].get(feature)
            if observed is None:
                continue
            rows.append({
                "geo": geo,
                "feature": feature,
                "observed": float(observed),
                "predicted": float(means.loc[geo, feature] * values["arable_land_mean"]),
            })
    table = pd.DataFrame(rows)
    eu = table[table["geo"] == "EU"]
    differences = table["predicted"].to_numpy() - table["observed"].to_numpy()
    observed_std = float(np.std(table["observed"].to_numpy()))
    per_crop = {}
    for feature in features:
        selected = table[(table["geo"] != "EU") & (table["feature"] == feature)]
        per_crop[feature] = _r_squared(selected["observed"].to_numpy(), selected["predicted"].to_numpy())
    return {
        "comparison_pairs": int(len(table)),
        "eu_r_squared": _r_squared(eu["observed"].to_numpy(), eu["predicted"].to_numpy()),
        "global_nrmse": float(np.sqrt(np.mean(np.square(differences))) / observed_std),
        "country_r_squared_by_crop": per_crop,
    }


def _threshold_checks(metrics: dict, thresholds: dict) -> dict:
    checks = {
        "accuracy": metrics["accuracy"] >= float(thresholds["minimum_accuracy"]),
        "macro_f1": metrics["macro_f1"] >= float(thresholds["minimum_macro_f1"]),
        "minimum_class_recall": metrics["minimum_class_recall"] >= float(thresholds["minimum_class_recall"]),
    }
    return {"checks": checks, "passed": all(checks.values())}


def _clean(value):
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return round(number, 12) if math.isfinite(number) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _agent_error(detail: str) -> dict:
    return {
        "schema_version": "1.0",
        "status": "agent_output_error",
        "score": 0.0,
        "score_level": "S0",
        "detail": detail,
    }


def _internal_error() -> dict:
    return {
        "schema_version": "1.0",
        "status": "evaluator_internal_error",
        "score": None,
        "score_level": None,
        "detail": "PRIVATE_EVALUATOR_ERROR",
    }


def verify(output_dir: Path, reference_dir: Path) -> dict:
    try:
        contract, expert, lpis, eurostat = _load_private(Path(reference_dir))
    except Exception:
        return _internal_error()
    try:
        candidate = _load_candidate(Path(output_dir), contract)
    except AgentOutputError as exc:
        return _agent_error(str(exc))
    except Exception:
        return _agent_error("UNPARSEABLE_OUTPUT")

    try:
        string_fields = contract["exact_string_columns"]
        numeric_fields = contract["numeric_columns"]
        expected_ids = pd.to_numeric(expert["point_id"], errors="raise").to_numpy(dtype=np.int64)
        string_checks = {
            field: bool(candidate[field].astype(str).to_numpy().tolist() == expert[field].astype(str).to_numpy().tolist())
            for field in string_fields
        }
        string_checks["point_id"] = bool(np.array_equal(candidate["point_id"].to_numpy(), expected_ids))
        numeric_checks = {}
        for field in numeric_fields:
            expected = pd.to_numeric(expert[field], errors="raise").to_numpy(dtype=float)
            tolerance = float(contract["s1"]["numeric_tolerances"][field])
            numeric_checks[field] = bool(np.all(np.abs(candidate[field].to_numpy() - expected) <= tolerance))
        class_counts = candidate["crop_sequence_type"].value_counts().reindex(contract["class_order"], fill_value=0)
        s1_checks = {
            "exact_fixed_support_and_public_fields": all(string_checks.values()) and all(numeric_checks.values()),
            "all_classes_present": bool((class_counts >= int(contract["s1"]["minimum_class_count"])).all()),
            "frequency_bounds": bool(
                np.all(candidate[contract["feature_order"]].to_numpy() >= 0)
                and np.all(candidate[contract["feature_order"]].to_numpy() <= 1)
            ),
        }
        s1_passed = all(s1_checks.values())

        if not s1_passed:
            return _clean({
                "schema_version": "1.0",
                "status": "scored",
                "score": contract["scoring"]["S0"],
                "score_level": "S0",
                "artifact_checks": {"four_deliverables_present": True, "figure_readable_png": True},
                "metrics": {"class_counts": class_counts.to_dict()},
                "stage_evaluation": {
                    "achieved_stage": "S0",
                    "aggregation": "strict_cumulative_AND",
                    "stages": {
                        "S0": {"passed": True},
                        "S1": {"passed": False, "checks": s1_checks, "string_fields": string_checks, "numeric_fields": numeric_checks},
                        "S2": {"passed": False},
                        "S3": {"passed": False},
                        "S4": {"passed": False},
                        "S5": {"passed": False},
                    },
                },
            })

        direct = _categorical_metrics(expert["crop_sequence_type"], candidate["crop_sequence_type"], contract["class_order"])
        semantic = _semantic_checks(candidate, contract)
        s2_thresholds = _threshold_checks(direct, contract["s2"])
        s2_passed = s1_passed and s2_thresholds["passed"] and semantic["all_passed"]

        blocks = _block_metrics(candidate, lpis, contract["class_order"])
        euro_metrics = _eurostat_metrics(candidate, eurostat, contract["feature_order"])
        s3_thresholds = _threshold_checks(direct, contract["s3"]["author_agreement"])
        mean_distance = float(np.mean([item["candidate_total_variation"] for item in blocks.values()]))
        euro_tolerance = float(contract["s3"]["eurostat_tolerance"])
        euro_checks = {
            "eu_r_squared": euro_metrics["eu_r_squared"] is not None
            and euro_metrics["eu_r_squared"] + euro_tolerance >= eurostat["baseline_metrics"]["eu_r_squared"],
            "global_nrmse": euro_metrics["global_nrmse"] <= eurostat["baseline_metrics"]["global_nrmse"] + euro_tolerance,
            "country_crop_r_squared": all(
                euro_metrics["country_r_squared_by_crop"][feature] is not None
                and euro_metrics["country_r_squared_by_crop"][feature] + euro_tolerance >= baseline
                for feature, baseline in eurostat["baseline_metrics"]["country_r_squared_by_crop"].items()
            ),
        }
        s3_checks = {
            "author_agreement": s3_thresholds["passed"],
            "pooled_lpis_noninferiority": mean_distance
            <= float(contract["s3"]["author_mean_total_variation"]) + float(contract["s3"]["lpis_noninferiority_margin"]),
            "eurostat_consistency": all(euro_checks.values()),
        }
        s3_passed = s2_passed and all(s3_checks.values())

        core_ids = contract["s4"]["block_ids"]
        extension_ids = contract["s5"]["block_ids"]
        s4_block_checks = {block_id: blocks[block_id]["strict_gain_passed"] for block_id in core_ids}
        s5_block_checks = {block_id: blocks[block_id]["strict_gain_passed"] for block_id in extension_ids}
        s4_passed = s3_passed and all(s4_block_checks.values())
        s5_passed = s4_passed and all(s5_block_checks.values()) and all(euro_checks.values())
    except Exception:
        return _internal_error()

    achieved = "S5" if s5_passed else "S4" if s4_passed else "S3" if s3_passed else "S2" if s2_passed else "S1" if s1_passed else "S0"
    return _clean({
        "schema_version": "1.0",
        "status": "scored",
        "score": contract["scoring"][achieved],
        "score_level": achieved,
        "artifact_checks": {"four_deliverables_present": True, "figure_readable_png": True},
        "metrics": {
            "class_counts": class_counts.to_dict(),
            "author_product_agreement": direct,
            "semantic_centroids": semantic,
            "lpis_block_distribution": blocks,
            "mean_lpis_total_variation": mean_distance,
            "eurostat_consistency": euro_metrics,
        },
        "stage_evaluation": {
            "achieved_stage": achieved,
            "aggregation": "strict_cumulative_AND",
            "stages": {
                "S0": {"passed": True},
                "S1": {"passed": s1_passed, "checks": s1_checks, "string_fields": string_checks, "numeric_fields": numeric_checks},
                "S2": {"passed": s2_passed, "thresholds": s2_thresholds, "semantic_passed": semantic["all_passed"]},
                "S3": {"passed": s3_passed, "checks": s3_checks, "thresholds": s3_thresholds, "eurostat_checks": euro_checks},
                "S4": {"passed": s4_passed, "block_checks": s4_block_checks},
                "S5": {"passed": s5_passed, "block_checks": s5_block_checks, "eurostat_guard": all(euro_checks.values())},
            },
        },
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.output_dir, args.reference_dir)
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
    print(encoded, file=sys.stderr)
    print(encoded)


if __name__ == "__main__":
    main()
