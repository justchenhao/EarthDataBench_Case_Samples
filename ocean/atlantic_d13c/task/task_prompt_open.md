# Atlantic δ¹³C-DIC Observations, Point Reconstruction, and 3-D Climatology

## Objective

Use the supplied Atlantic cruise observations, GLODAPv2.2023 point predictors, GLODAPv2.2016b mapped predictors, and monthly atmospheric xCO2 to construct three linked products: a secondary-quality-controlled public observation table, a fixed-support Atlantic point reconstruction, and a `1° × 1° × 33-depth` Atlantic climatology. The sole formal scientific quantity is δ¹³C-DIC in per mille relative to VPDB. Point and grid products also require comprehensive uncertainty and quality or support information. Preserve declared missing support rather than inventing target values.

Method choices are not prescribed.

## Input

- `input/qc_observation_source.csv.gz` contains 96,079 non-private cruise rows with identifiers, date, nine ocean predictors, raw δ¹³C-DIC, and source flags. Two whole-cruise test sets are absent. Numeric source missing values use `-9999`.
- `input/cruise_adjustments.csv` supplies the paper Table 1 additional adjustment and model-eligibility decision for each public cruise. The archived raw field already incorporates applicable earlier Becker et al. adjustments. A blank adjustment denotes the explicitly rejected poor cruise.
- `input/point_prediction_support.csv.gz` contains exactly 152,127 target-free GLODAPv2.2023 Atlantic rows with ten finite predictors and five source flags on fixed `sample_id` support.
- `input/grid_prediction_support.nc` contains the native `depth=33, lat=180, lon=360` GLODAPv2.2016b mapped predictors and errors, a public predictor-derived `valid_mask` with 289,219 cells, and the disclosed timeless xCO2 reduction. Inspect its attributes, units, coordinates, and missing encodings.
- `input/xco2_monthly_1972_2023.csv.gz` contains the complete 624-month Mauna Loa xCO2 sequence. `input/README.md` and `input/input_manifest.json` document public rules, hashes, counts, and reconstructed choices.
- This is a bounded reconstructed Case: an executable row-wise 2023 micro-adjustment and per-record author uncertainty array are not published and must not be inferred from private or reference data.

## Prohibited data

- Do not use an author QC table, author point reconstruction, author gridded climatology, renamed or cropped copies of them, source-paper values, figures, or prior Agent outputs as target inputs.
- Do not use `reference/`, withheld cruise labels or identities, private support keys, independent validation observations, hidden thresholds, evaluator code, or network access.
- Use only the listed `input/` files as scientific production inputs. General-purpose software libraries are allowed, but they must not supply δ¹³C-DIC target-product values.

## Output

Place exactly the following six ordinary files under `output/`:

1. `output/qc_observations.csv.gz`: gzip CSV with exactly `observation_id,expocode,adjusted_d13c_dic_per_mille,quality_flag`, exactly 96,079 rows sorted by ascending `observation_id`, exact public support, float64 target text or `-9999`, and integer flags from `{2,3,9}`.
2. `output/reconstructed_points.csv.gz`: gzip CSV with exactly `sample_id,d13c_dic_per_mille,uncertainty_per_mille,quality_flag`, exactly 152,127 rows sorted by ascending `sample_id`, exact public support, finite δ¹³C-DIC in `[-2,3]‰`, finite uncertainty in `[0.07,1.0]‰`, and integer flags from `{2,3}`.
3. `output/climatology.nc`: NETCDF4 with dimensions ordered `depth=33, lat=180, lon=360`; float64 `depth`, `lat`, and `lon` copied exactly and in order from the grid input with units `m`, `degrees_north`, and `degrees_east`, and `depth:positive="down"`; exactly float32 scientific variables `d13c_dic(depth,lat,lon)` with `units="per_mille_VPDB"` and `uncertainty(depth,lat,lon)` with `units="per_mille"`; both use `_FillValue=-9999.0f`, are finite within `[-2,3]‰` and `[0.07,1.0]‰` on `valid_mask=1`, and are fill on `valid_mask=0`.
4. `output/representative.png`: four panels showing observation year–latitude coverage, point δ¹³C-DIC at `0–200 m`, and grid δ¹³C-DIC at `0 m` and `1000 m`; labeled axes, readable colorbars, no interpolation, distinct missing grid cells, `viridis` and fixed `0–2.2‰ VPDB` for the three spatial panels.
5. `output/methodology.md`: a concise scientific methodology and execution record. Wording and layout are not fixed.
6. `output/build_product.py`: complete deterministic code that reads only public input and regenerates all formal products and the figure from the task root.

Do not submit additional target products, target variables, cached intermediates, or extra files.

The `output/` directory itself must contain only these six files: do not leave subdirectories, `__pycache__`, `.pyc` bytecode, or other cache artifacts there. If you syntax-check the submitted program, direct bytecode outside `output/` or remove the generated cache before submission.

## Evaluation

Evaluation first checks exact delivery, schemas, identifiers, coordinates, mask behavior, ranges, non-degeneracy, reproducibility, and figure readability. Invalid or incomplete output receives zero. For a deterministic bounded run, the output gate also applies the following public limits: compressed files may not exceed 16 MiB for `qc_observations.csv.gz`, 32 MiB for `reconstructed_points.csv.gz`, 96 MiB for `climatology.nc`, 32 MiB for `representative.png`, 2 MiB for `methodology.md`, or 4 MiB for `build_product.py`; decompressed QC and point CSV content may not exceed 32 MiB and 64 MiB, respectively. A scientifically non-degenerate product must have at least 8,000 non-fill QC values, 500 distinct QC values, 1,000 distinct point predictions, and 1,000 distinct valid-grid predictions, with standard deviation at least `0.05‰` in each of those three value branches. The methodology must be nonempty valid UTF-8 and the production program must be syntactically valid Python. Breaching any of these declared delivery, safety, or non-degeneracy conditions makes the output invalid and therefore scores zero. Valid products are then compared with a trusted expert product and sampled directly on concealed whole-cruise observations. Evaluation proceeds strictly through `0.2`, `0.4`, `0.6`, `0.8`, and `1.0`, stopping at the first failed gate. The `0.4` and `0.6` gates require both expert-product agreement and independent-validation non-inferiority; the `0.8` and `1.0` gates then add strict independent improvement. Private reference values, support identities, comparison thresholds, and scoring implementation remain undisclosed.
