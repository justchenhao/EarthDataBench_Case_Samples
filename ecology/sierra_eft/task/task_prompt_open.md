# Sierra Nevada Ecosystem Functional Types, 2001–2018

## Objective

Use the complete public MOD13Q1 EVI input for 2001–2018 to reconstruct annual Ecosystem Functional Attributes (EFAs), Ecosystem Functional Types (EFTs), functional diversity, and interannual stability over the fixed Sierra Nevada source-grid window. The formal target includes annual EVI mean, seasonality and peak month; annual EFT, richness and rarity; and the paper's interannual summaries, including EFT-composition dissimilarity.

## Input

- `input/a_evi_aoi/` contains annual NPZ/JSON pairs for 2001–2018 and `aoi_evi_manifest.json`. Each NPZ contains all 23 MOD13Q1 16-day EVI composites for the year on the same `164 × 410` source window, together with native row and column indices.
- Annual JSON records provide the corresponding acquisition timestamps, source-granule provenance, MODIS grid metadata, scale and fixed geographic bounding box. Inspect and use them to establish chronological completeness and calendar months.
- EVI is stored on the original 10,000 scale. Source fill and negative EVI have already been mapped to zero as recorded in the metadata. Zero is not a positive vegetation observation.

Method choices are not prescribed.

## Prohibited data

- Do not use the PANGAEA author product, paper code, cached targets, private evaluation data, or values inferred from them.
- Do not use GBIF/DEIMS field phenology in production; it is reserved for independent evaluation.
- Do not access the network or use libraries that supply target values.

## Output

Place exactly these five regular files under `output/`:

1. `output/sierra_nevada_eft.npz`, containing exactly:
   - int16 `(18,164,410)`: `evi_mean_scaled`, `evi_ssd_scaled`;
   - uint8 `(18,164,410)`: `evi_dmax_month`, `eft_code`, `eft_richness`;
   - float32 `(18,164,410)`: `eft_rarity`;
   - float32 `(164,410)`: `evi_mean_interannual_mean`, `evi_ssd_interannual_mean`, `evi_dmax_interannual_mean`, `eft_richness_interannual_mean`, `eft_rarity_interannual_mean`, `eft_interannual_dissimilarity`; `evi_dmax_interannual_mean` must lie in `[1,12]`;
   - uint8 `(164,410)`: `eft_mode`, `eft_interannual_variability`.
2. `output/thresholds.json`, with the integer list 2001–2018 and strictly increasing three-element fixed-break arrays named `evi_mean_scaled` and `evi_ssd_scaled`.
3. `output/representative.png`, readable and non-blank, showing EFT mode, mean EVI, circular mean DMAX, mean richness, mean rarity, and dissimilarity on longitude/latitude axes with labeled colorbars and no display interpolation. Use the explicit fixed geographic bounding box in the annual metadata for the axes rather than deriving the extent from the tile label.
4. `output/methodology.md`, documenting completeness, scientific choices, equations, thresholds, window behavior, software, run command, and limitations.
5. `output/build_product.py`, valid deterministic Python no larger than 2 MiB that regenerates the other deliverables from `input/a_evi_aoi/` when run from the task root.

Do not submit any additional files or directories.

## Evaluation

Evaluation first checks delivery and schema, then expert-product similarity and independent field-phenology performance. Evaluation proceeds strictly through 0.2, 0.4, 0.6, 0.8, and 1.0, stopping at the first failed gate. The 0.4 and 0.6 gates require both expert-product similarity and independent-validation non-inferiority; the 0.8 and 1.0 gates then add strict independent improvement. Private references, support partitions, and numerical thresholds remain hidden.
