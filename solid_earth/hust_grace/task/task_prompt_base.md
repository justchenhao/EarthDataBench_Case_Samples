# HUST-Grace2024 Monthly Low-Degree Anomalies and Degree Spectra, 2002–2022

## Objective

Use the complete official HUST-Grace2024 n60 monthly spherical-harmonic archive to reconstruct the paper-window `C20` and `C30` anomaly series and degree-2-to-60 RMS coefficient spectra for every available month from April 2002 through December 2022. The formal scientific products are the two low-degree anomaly pairs and the monthly degree spectra. Preserve missing calendar months; restore only coefficients lost from the damaged member with the fixed nearest-bracketing-month rule below.

## Input

- `input/HUST-Grace2024-n60.zip` contains 255 official monthly `.gfc` members. Member filenames encode `YYYYMM`. Exactly 214 members fall in the inclusive paper window `200204`–`202212`; the remaining 41 later members are context only and must not enter either product.
- `input/definition_contract.json` freezes the evaluation window, target terms, normalization and tide system, smoothing rule, spectrum formulas, corrupt-row policy, formal outputs, and required structured method metadata.
- Each usable `gfc` row contains record type, degree `l`, order `m`, cosine coefficient `C_lm`, sine coefficient `S_lm`, formal uncertainties `sigma_C_lm` and `sigma_S_lm`. Use only `gfc` records. Coefficients are dimensionless, fully normalized, and zero tide.
- The January 2014 member is CRC-damaged from degree-60/order-34 onward. Retain every valid triangular row recovered before and within the damaged tail. For each missing `(l,m)` coefficient, use the component-wise arithmetic mean of the same `(l,m)` from the nearest earlier and later available paper-window months; record both source months. Do not restore any value that is already valid.
- The archive is not cropped to the paper window and has not been converted into anomaly or spectrum tables.

## Product construction

1. Inventory all 255 ZIP members deterministically, derive month from each member filename, and process exactly the 214 members whose `YYYYMM` lies in `200204`–`202212`. Sort all output by month and then degree.
2. Parse finite `gfc` values for degrees 0–60. Reject malformed, duplicate, out-of-range, or physically invalid coefficient rows explicitly. For the damaged January 2014 member, preserve streamed valid rows even when the final CRC check fails, then restore each missing triangular coefficient by the fixed nearest-earlier/nearest-later component-wise mean. Record every rejected and restored row and both source months in `method.json`.
3. For each included month, extract `C20=C(2,0)` and `C30=C(3,0)`. For each term separately, subtract its arithmetic mean over all 214 included months and multiply by `1e10`; write these baseline anomalies as `author_c20_1e10` and `author_c30_1e10`.
4. Construct each enhanced coefficient series by applying `0.25*previous + 0.50*current + 0.25*next` only when the previous and next calendar months both exist in the 214-month window. Otherwise retain the original coefficient. Recenter the resulting 214 values by their own window mean and multiply by `1e10`; do not fill missing months or add rows.
5. For every included month and each degree 2–60, compute `rms_power = sqrt(sum(C_lm^2 + S_lm^2) / (2*l + 1))` and `formal_rms_power = sqrt(sum(sigma_C_lm^2 + sigma_S_lm^2) / (2*l + 1))` over that degree's usable orders. Do not replace RMS power with a sum, degree amplitude, zonal-only value, or spatial synthesis.
6. Retain float64 precision during accumulation. Use deterministic ordering, numeric formatting, plotting parameters, and serialization. Report inventory, window exclusions, parsing anomalies, row counts, formulas, software versions, execution command, and limitations in the structured method record.
7. Supply complete code that reads only the two listed public inputs and regenerates all non-code products in a new empty output directory without network access.

## Prohibited data

- Do not use precomputed HUST-Grace2024 low-degree tables, degree spectra, maps, replacement-coefficient products, screenshots, prior Case outputs, or values copied from any of them.
- Do not use author processing code, NASA TN-14 values, independent validation data, private references, hidden matching support, or any `reference/` directory.
- Do not read outside the task root or access the network. General-purpose Python scientific libraries are allowed but must not supply target-product values.

## Output

Place exactly these five ordinary files under `output/`, with no extra files, directories, caches, or bytecode:

1. `output/low_degree_monthly.csv`: UTF-8 CSV with exact header `month,author_c20_1e10,enhanced_c20_1e10,author_c30_1e10,enhanced_c30_1e10` and exactly 214 data rows. `month` is a unique six-digit `YYYYMM` in strictly increasing archive order within `200204`–`202212`; missing calendar months remain absent. All four product columns are finite decimal values in `1e-10` coefficient units.
2. `output/degree_spectrum.csv`: UTF-8 CSV with exact header `month,degree,rms_power,formal_rms_power` and exactly 12,626 data rows: one unique row for every submitted month and every integer degree 2–60, sorted by month then degree. Both RMS columns are finite, non-negative, dimensionless values.
3. `output/method.json`: a valid UTF-8 JSON object. It must contain exactly the disclosed product metadata, including at least `schema_version="hust-grace2024-v24-method-v1"`, `input_archive="HUST-Grace2024-n60.zip"`, integer `archive_member_count=255`, integer `evaluation_window_count=214`, `normalization="fully_normalized"`, and `tide_system="zero_tide"`. It must also record the inclusive window, excluded-member count, missing-month policy, low-degree scaling and smoothing, spectrum formulas, parsing diagnostics, output row counts, software versions, and executed command. Field order and wording of explanatory values are not fixed.
4. `output/low_degree_validation.png`: an RGB or RGBA PNG readable and non-blank. Show labeled UTC time-series panels for baseline and enhanced `C20` and `C30` anomalies, plus a month-versus-degree visualization or representative degree-spectrum panel. Include axis labels, units, legends, and a labeled colorbar where a two-dimensional spectrum is shown; do not draw across missing months as if observations existed.
5. `output/solution.py`: complete deterministic code supporting `python output/solution.py --input input --output <new-empty-directory>` from the task root. The replay command must write exactly the four non-code deliverables above, must not read neighboring submitted products, and must not access private paths or the network.

Do not submit the input ZIP, intermediate coefficient tables, additional scientific variables, logs, sidecars, or cached files.

## Evaluation

Evaluation first checks exact delivery, structured schemas, month/degree support, finite physical values, missing-month behavior, figure readability, and isolated deterministic replay. Invalid or malformed Agent output receives zero. Valid products are then compared with a trusted expert reconstruction and, at higher cumulative levels, with concealed independent low-degree observations using guarded association and RMSE diagnostics. Scores of 0.8 or 1.0 require the submitted enhanced products to outperform the expert baseline on independent validation. Private reference values, matching support, thresholds, and scoring implementation remain undisclosed.
