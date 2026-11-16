# Public production inputs

This bounded reconstructed Case retains the paper's three product branches.

- `qc_observation_source.csv.gz`: raw non-private cruise observations; apply `cruise_adjustments.csv`.
- `point_prediction_support.csv.gz`: fixed predictor-only GLODAPv2.2023 Atlantic point support and source flags.
- `grid_prediction_support.nc`: GLODAPv2.2016b mapped predictors, errors, fixed public Atlantic mask, and timeless xCO2 reduction.
- `xco2_monthly_1972_2023.csv.gz`: pinned monthly Mauna Loa xCO2 projection.

QC rule: when the adjustment is present and raw delta-13C is finite, add the adjustment; write flag 2 only for an eligible cruise with source c13 flag in {2,6}, otherwise flag 3. A blank adjustment with finite raw data receives fill value and flag 3; a missing raw observation receives fill value and flag 9. For model training additionally require c13 and all predictor flags in {2,6}, finite predictors, and a finite adjusted target.
