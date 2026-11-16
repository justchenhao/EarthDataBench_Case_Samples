#!/usr/bin/env python3
"""Canonical CLI for the HUST private evaluator."""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evaluator import evaluate


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(evaluate(arguments.output_dir, arguments.reference_dir), sort_keys=True))
