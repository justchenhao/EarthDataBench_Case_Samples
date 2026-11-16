# Sierra Nevada Ecosystem Functional Types, 2001–2018

## Objective

Use the complete public MOD13Q1 EVI input for 2001–2018 to reconstruct annual Ecosystem Functional Attributes (EFAs), annual Ecosystem Functional Types (EFTs), annual richness and rarity, and their interannual summaries over the fixed Sierra Nevada source-grid window. The formal product includes the paper's two stability measures: pixel-level EFT variability and 4 × 4-window EFT-composition dissimilarity. Preserve the native source-grid ordering and do not use a reference product, field observations, or precomputed EFT layers.

## Input

- `input/a_evi_aoi/` contains 18 annual NPZ files, `evi_2001.npz` through `evi_2018.npz`. Each contains `evi_scaled_int16(23,164,410)`, `x_window(410)`, and `y_window(164)` from the complete 23 MOD13Q1 16-day composites for that year.
- The matching annual JSON file records the 23 composite timestamps, source granule identifiers, native MODIS sinusoidal grid metadata, scale, fill handling, and the fixed geographic bounding box. Use these timestamps to convert the earliest maximum-EVI composite to a calendar month.
- `input/a_evi_aoi/aoi_evi_manifest.json` is the deterministic completeness and provenance manifest. Process every listed annual NPZ/JSON pair.
- EVI values are scaled by 10,000. Source fill and negative EVI have already been converted to zero, as documented in the annual records. Zero is excluded when calculating EVI annual mean and population standard deviation; if a pixel has no positive composite, all of its integer annual targets are zero and float targets are zero.

## Product construction

1. Read years in ascending order. For every year and pixel, calculate the mean and population standard deviation of positive EVI composites and store both on the original 10,000 scale. Determine `evi_dmax_month` from the earliest composite attaining the annual maximum, using its timestamp month.
2. For each year, calculate the first, second, and third spatial quartiles of positive annual EVI mean and EVI standard deviation. Average each corresponding quartile across all 18 years to obtain three fixed breaks for each attribute. Use those fixed breaks for every year.
3. Divide EVI mean into four ascending classes. Divide EVI standard deviation into four classes in the paper's decreasing-seasonality order: class `a` is above the highest break and class `d` is at or below the lowest break. Divide EVI_DMAX into spring (April–June), summer (July–September), fall (October–December), and winter (January–March). Combine the three four-level attributes deterministically into `eft_code` values 1–64, ordered first by ascending productivity, then decreasing seasonality, then spring/summer/fall/winter.
4. For each year, calculate EFT richness as the number of distinct nonzero EFT codes in the 4 × 4 window whose top-left pixel is the output cell. Write zero in the trailing three rows and columns where a full window is unavailable.
5. For each year and EFT class `i`, calculate paper-defined rarity as

   `rarity_i = (area_max - area_i) / area_max`

   where `area_i` is the number of pixels occupied by class `i` and `area_max` is the count of the year's most abundant class. Assign that class rarity to its pixels. This is not `1 - area_i / total_area` and not inverse frequency.
6. Calculate 2001–2018 interannual means of EVI mean, EVI standard deviation, richness, and rarity. For the EVI_DMAX circular summary, map January–December to zero-based angles, take the circular mean direction, round to the nearest zero-based calendar-month index, apply modulo 12, and add one. Store the result as float32 in the closed interval `[1,12]`; January is `1`, never `0` or `13`. Calculate EFT mode with the lowest numeric code resolving an exact frequency tie, and EFT interannual variability as the number of distinct annual EFT codes at each pixel.
7. Calculate EFT interannual dissimilarity for every complete 4 × 4 window. For each of the 153 unordered year pairs, form the set of nonzero EFT classes in that window, calculate `1 - |intersection| / |union|`, and average the 153 values. Write zero in the trailing three rows and columns.
8. Use deterministic array operations and file ordering. Do not smooth, interpolate, replace outputs with constants, or use field phenology as a production input.

## Prohibited data

- Do not use the PANGAEA author EFT/EFA product, source-paper code, cached target arrays, private evaluation files, or values inferred from them.
- Do not use GBIF/DEIMS field phenology in production; it is reserved for independent evaluation.
- Do not access the network. Use only the listed public input and ordinary software libraries that do not supply target values.

## Output

Place exactly these five regular files under `output/`:

1. `output/sierra_nevada_eft.npz`, an unpickled NumPy archive containing exactly these arrays:
   - `evi_mean_scaled`, `evi_ssd_scaled`: int16 `(18,164,410)`;
   - `evi_dmax_month`, `eft_code`, `eft_richness`: uint8 `(18,164,410)`;
   - `eft_rarity`: float32 `(18,164,410)`;
   - `evi_mean_interannual_mean`, `evi_ssd_interannual_mean`, `evi_dmax_interannual_mean`, `eft_richness_interannual_mean`, `eft_rarity_interannual_mean`, `eft_interannual_dissimilarity`: float32 `(164,410)`. Every `evi_dmax_interannual_mean` value must be in `[1,12]`;
   - `eft_mode`, `eft_interannual_variability`: uint8 `(164,410)`.
2. `output/thresholds.json`, containing `years` equal to the integer list 2001–2018 and strictly increasing three-element arrays `evi_mean_scaled` and `evi_ssd_scaled` containing the fixed breaks.
3. `output/representative.png`, a spatially explicit multi-panel figure showing at least EFT mode, mean EVI, circular mean DMAX, mean richness, mean rarity, and interannual dissimilarity. Use the explicit fixed geographic bounding box in the annual metadata for longitude/latitude axes; do not infer the figure extent from the source tile label. Include labeled colorbars with units, use no interpolated display, and use a readable and non-blank.
4. `output/methodology.md`, a concise execution record describing input completeness, EFA/EFT equations, threshold values, window anchoring, rarity denominator, circular mean, Jaccard dissimilarity, software versions, run command, and known limitations.
5. `output/build_product.py`, complete deterministic code that reads only `input/a_evi_aoi/` and regenerates the other four deliverables when run from the task root.

Do not add other files or directories. The build script must be valid Python and no larger than 2 MiB.

## Evaluation

Evaluation first checks the exact delivery set, schemas, dtypes, shapes, ranges, non-degeneracy, figure dimensions, and reproducibility. A valid product is then compared with a trusted expert product and with independent field-phenology support. Evaluation proceeds strictly through 0.2, 0.4, 0.6, 0.8, and 1.0, stopping at the first failed gate. The 0.4 and 0.6 gates require both expert-product similarity and independent-validation non-inferiority; the 0.8 and 1.0 gates then add strict independent improvement. Private reference values, support partitions, and numerical thresholds are not disclosed.
