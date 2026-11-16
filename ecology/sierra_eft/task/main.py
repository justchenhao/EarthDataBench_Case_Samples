from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _error(detail):
    return {"schema_version": "1.0", "status": "evaluator_internal_error", "score": None, "detail": detail}


def evaluate(output_dir, reference_dir=None):
    if reference_dir is None:
        return _error("PRIVATE_EVALUATOR_MISSING")
    reference_dir = Path(reference_dir)
    verify = reference_dir / "evaluator" / "verify.py"
    if not verify.is_file() or verify.is_symlink():
        return _error("PRIVATE_EVALUATOR_MISSING")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [sys.executable, "-B", str(verify), "--output-dir", str(output_dir), "--reference-dir", str(reference_dir)],
        capture_output=True, text=True, check=False, env=env,
    )
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError:
        return _error("PRIVATE_EVALUATOR_INVALID_RESULT")
    if process.returncode != 0 or not isinstance(result, dict):
        return _error("PRIVATE_EVALUATOR_FAILED")
    return result
