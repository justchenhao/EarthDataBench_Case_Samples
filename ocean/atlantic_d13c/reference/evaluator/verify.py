#!/usr/bin/env python3
"""Integrity-check and invoke the Atlantic d13C-DIC v0.3 evaluator."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

EXPECTED_HASHES = {'core.py': '7ac0a8dac74b45b5137c7d72307e4fc3f41d788aeb1997c7c041ae0619371867', 'io_guard.py': 'faf3b4cef916dcaa8c9cb12a72b21d8850671f62166273ea05dce4e2a9514529', 'contract.json': 'a131f809fda745650720e668b6a3cbfeebdcf5a77b469d01055fe96effc6cf1a', 'public_support.npz': '61e43f67e9a6da716b691b26b1b8e2731c25b713a0999e2bc451b362ac3119a5', 'data/independent_holdout_reference.csv.gz': '16574aef8a68a7778f374ac0504ea701d21c10ad19fa25cd3a3a8d43d290f3c1', 'data/expert_qc_observations.csv.gz': '184e0d6f44d49c6aee31a3b0c4f195dc43023c40379a4fc891851ae7b4c9fbaf', 'data/expert_point_product.csv.gz': '2891d7ba479f278989952c6a19bc94430980708573683d50c1819ffbc504971e', 'data/expert_climatology.nc': '5ae49b19d7a1eb46744a7a8f6ebe3960c857d036f2cb0afb164f126d682ab8ff'}

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

def internal(detail: str) -> dict:
    return {"schema_version": "1.0", "status": "evaluator_internal_error", "score": None, "score_level": None, "detail": detail}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", required=True, type=Path)
    args = parser.parse_args()
    evaluation = args.reference_dir / "evaluation"
    try:
        for relative, expected_hash in EXPECTED_HASHES.items():
            path = evaluation / relative
            if path.is_symlink() or not path.is_file() or sha256(path) != expected_hash:
                print(json.dumps(internal(f"PRIVATE_INTEGRITY:{relative}"), sort_keys=True))
                return
        sys.path.insert(0, str(evaluation))
        from core import evaluate
        result = evaluate(args.output_dir, evaluation)
    except Exception as exc:
        result = internal(f"PRIVATE_EVALUATOR_EXCEPTION:{type(exc).__name__}:{exc}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))

if __name__ == "__main__":
    main()
