# Daily Latent-heat-flux Prolongation at Three FLUXNET Sites

## Objective

Use the supplied historical tower observations and aligned meteorological and vegetation predictors to reconstruct daily mean latent heat flux for `US-MMS`, `US-Ne1`, and `US-NR1` from 2015-01-01 through 2022-12-31. The sole formal scientific target is `le_w_m2` in `W m-2`. Produce every target site-date exactly once and preserve genuine temporal variability.

## Input

- `input/daily_predictors_and_training.csv.gz` is the complete bounded production input (SHA-256 `dc46e52754fe0e1d9c2a3ab7bf9f417c519732304ec9742b03a68c5f4b0b6c0e`). It contains `site_id`, `date`, `row_role`, seven predictors (`ta_c`, `ws_m_s`, `rh_percent`, `sw_in_w_m2`, `lw_in_w_m2`, `pa_kpa`, `ndvi`), `le_training_w_m2`, and `training_missing_ratio`.
- `input/source_lineage.json` maps each public column to FLUXNET2015, ERA5-Land, or MODIS MYD13Q1.061 and records the bounded scope. Its URLs are provenance records, not additional production inputs.
- `row_role=training` rows contain quality-controlled historical FLUXNET2015 daily LE labels and aligned predictors. `row_role=target` rows contain the complete 2015–2022 predictor series and deliberately omit both label fields.
- The predictors represent the paper's FLUXNET2015, ERA5-Land, and MODIS MYD13Q1.061 source families after site/date alignment and temporal preprocessing. The bounded table has 10,164 training rows and 8,766 target rows.
- Treat dates as each site's local calendar date.

Method choices are not prescribed.

## Prohibited data

- Do not use target-period tower labels, the author prolonged LE product, private validation observations, evaluator references, previous Agent outputs, or another evapotranspiration product.
- Do not use the network or manually encode target values.
- Use only the listed public input as scientific production data. Software libraries may implement algorithms but must not supply target-product values.

## Output

Place exactly four ordinary files under `output/`:

1. `output/daily_le_prolonged.csv.gz`: a real gzip CSV with header `site_id,date,le_w_m2`, exactly 8,766 unique rows, site order `US-MMS`, `US-Ne1`, `US-NR1`, and ascending `YYYY-MM-DD` dates within each site. Each site must contain all 2,922 dates from 2015-01-01 through 2022-12-31.
2. `output/method.json`: a valid JSON methodology and execution record. It must include `task_id`, `validation_fidelity`, `public_input_sha256`, `predictors`, and `sites`; set the first two to `hydrology/fluxnet2015_et_benchmark_v05` and `reconstructed`. `sites` must be a JSON object keyed exactly by `US-MMS`, `US-Ne1`, and `US-NR1` (do not use a list). Each value must be a JSON object and must contain integer `training_rows` equal to the complete public `row_role=training` row count before any filtering: `US-MMS=2970`, `US-Ne1=3504`, `US-NR1=3690`. If rows are screened or excluded, report those counts separately in clearly named fields such as `eligible_training_rows` or `used_training_rows`; never replace `training_rows` with a filtered count. Additional clearly named per-site diagnostic fields are allowed. Additional top-level diagnostic fields are also allowed, but the five required top-level keys must remain present.
3. `output/representative_daily_le.png`: three vertically stacked panels in the fixed site order showing the centred 7-day rolling mean of predicted daily LE over 2015–2022. Use date on the x axis, `Daily LE (W m-2)` on the y axis, a common `-30` to `200 W m-2` range, readable site/year labels, and readable and non-blank.
4. `output/solution.py`: the complete deterministic script used to read only `input/` and regenerate the other three deliverables. It must be syntactically valid and must not create additional output files.

## Evaluation

Evaluation first checks exact delivery, schema, support, physical validity, non-degenerate variation, figure readability, method provenance, and reproducibility; invalid or missing formal output receives 0. A valid `le_w_m2` product is then compared with a trusted expert product and independent post-2014 tower observations. Evaluation proceeds strictly through 0.2, 0.4, 0.6, 0.8, and 1.0, stopping at the first failed gate. The 0.4 and 0.6 gates require both expert-product agreement and independent-validation non-inferiority; the 0.8 and 1.0 gates then require robust improvement on the predefined independent station-period and station-season blocks. Private values, support details, uncertainty resampling, and numerical thresholds are not disclosed.
