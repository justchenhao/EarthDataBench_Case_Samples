# Antarctic T2m evaluator v6 dual-constraint design

## Scientific binding

Both private references evaluate the same formal target as the submission:
monthly 2 m air-temperature anomaly in K for 1958-01 through 2022-12 on the
114×114 template. C is the frozen expert reconstruction on the field-quality
core (`LANDMASK >= 0.5`). B is the independently withheld READER station set,
matched to the same gridded anomaly on `LANDMASK >= 0.1`, with station-specific
temporal intersections and the same 1981–2010 monthly climatology convention.
The expert product is evaluated on B before candidate scoring and remains the
0.6 anchor. Mount Siple remains excluded because the available file is a
different station; no substitute is introduced.

## Low branch

The evaluator computes the two constraints independently:

`low_score = min(S_C, S_B)`

- `S_C` is 0.2, 0.4, or 0.6 from strict-AND expert-field consistency checks.
- `S_B` is 0.2, 0.4, or 0.6 from strict-AND degradation checks against the
  expert's B baseline.
- S2 passes only if both values are at least 0.4; S3 passes only if both are
  0.6. A valid submission that misses the minimum C skill tier remains S0.

The 0.6 B cap preserves Candidate v5's approved aggregate tolerances: station
RMSE ratio ≤1.10, detrended-correlation drop ≤0.05, and trend-MAE excess ≤0.05
K/decade. It adds non-compensable support and regional guards: at least 30 of
33 stations must be within 0.35 K RMSE deficit and 0.10 correlation deficit,
no station may exceed either bound, and at least 30 monthly stations plus 8
trend stations must be usable.

The 0.4 B cap preserves the former S2 aggregate tolerances: RMSE ratio ≤1.70,
correlation drop ≤0.20, and trend-MAE excess ≤0.20 K/decade. At least 27 of 33
stations must be within 0.75 K RMSE deficit and 0.20 correlation deficit; the
hard maxima are 0.75 K and 0.35, with the same support minima.

## Metric roles and calibration

The frozen private configuration declares one design role for each B metric.
Mean station RMSE is primary. Mean detrended correlation, station support, and
regional RMSE/correlation stability are guards. Mean station trend absolute
error is secondary-scored: its 0.4 tolerance is intentionally wider than its
0.6 tolerance, but it is never ignored. The executable code implements named
metrics and thresholds directly; it does not dispatch on these role labels.

Deterministic fixtures separate the caps with margin:

| Fixture | RMSE ratio | correlation drop | regions within medium guard | intended B cap |
|---|---:|---:|---:|---:|
| expert | 1.000 | 0.000 | 33 | 0.6 |
| 0.5 K noise | 1.039 | 0.038 | 33 | 0.6 |
| 1.0 K noise | 1.140 | 0.114 | 29 | 0.4 |
| 2.0 K noise | 1.469 | 0.261 | 7 | 0.2 |

The historical frozen Agent output supplies the asymmetric veto case:
`S_C=0.6`, `S_B=0.4`, therefore score 0.4. A synthetic boundary fixture covers
`S_C=0.4`, `S_B=0.2`, therefore score 0.2. Tests also isolate primary, guard,
and secondary-scored failures and exercise equality at every strict cap.

## High branch

S4 and S5 are reachable only after S3. Their local checks use B only: aggregate
RMSE improvement, correlation gain, trend-error improvement, improved-station
fractions, and adequate support. C similarity cannot unlock or veto 0.8/1.0
after the 0.6 entry condition has been satisfied.

Evaluator or trusted-reference faults return `score=null`; delivery, schema,
coverage, physical-validity, and reproducibility failures remain prerequisites
and are not averaged into the dual-constraint score.
