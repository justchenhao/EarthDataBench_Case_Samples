# Evaluator usage

Run from any working directory with the benchmark Python environment:

```bash
python -B reference/evaluator/verify.py   --output-dir /path/to/output   --reference-dir /path/to/this/case/reference
```

The final stdout JSON distinguishes `scored` and Agent-output failures from
`evaluator_internal_error`. The `reference` directory is private and must never
be mounted into the Agent container.
