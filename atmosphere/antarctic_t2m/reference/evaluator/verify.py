#!/usr/bin/env python3
"""Standalone CLI adapter for the native Antarctic T2m scorer."""

import argparse
import json
import tempfile
from pathlib import Path

import antarctic_t2m_evaluator as core


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    args = parser.parse_args()
    reference = args.reference_dir.resolve()
    with tempfile.TemporaryDirectory(prefix="antarctic-t2m-eval-") as temporary:
        submission = Path(temporary) / "submission"
        submission.mkdir()
        (submission / "output").symlink_to(args.output_dir.resolve(), target_is_directory=True)
        result = core.evaluate_safe(
            reference.parent, submission, reference / "evaluator_config.json"
        )
    result = core._json_safe(result)
    result.setdefault("schema_version", "1.0")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 2 if result.get("score") is None else 0


if __name__ == "__main__":
    raise SystemExit(main())
