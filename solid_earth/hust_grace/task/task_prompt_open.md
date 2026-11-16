# HUST-Grace2024 Monthly Low-Degree Anomalies and Degree Spectra, 2002–2022

## Objective

Use the complete official HUST-Grace2024 n60 monthly spherical-harmonic archive to reconstruct the paper-window `C20` and `C30` anomaly series and degree-2-to-60 RMS coefficient spectra for every available month from April 2002 through December 2022. The formal scientific products are the two low-degree anomaly pairs and the monthly degree spectra. Preserve missing calendar months; restore only coefficients lost from damaged source content with the fixed nearest-bracketing-month rule below.

Method choices are not prescribed.

## Input

- `input/HUST-Grace2024-n60.zip` contains 255 official monthly `.gfc` members whose filenames encode `YYYYMM`. Exactly 214 members fall in the inclusive paper window `200204`–`202212`; later members are context only and must not enter either product.
- `input/definition_contract.json` freezes the evaluation window, target terms, normalization and tide system, smoothing rule, spectrum formulas, corrupt-row policy, formal outputs, and required structured method metadata.
- The native archive retains headers, spherical-harmonic coefficients and formal uncertainties through degree 60, absent calendar months, one damaged member, and post-paper-window files. It has not been cropped or converted into anomaly or spectrum tables.

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
