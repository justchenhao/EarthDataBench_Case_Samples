#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluator_core


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluator_core.evaluate(args.output_dir, args.reference_dir), ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
