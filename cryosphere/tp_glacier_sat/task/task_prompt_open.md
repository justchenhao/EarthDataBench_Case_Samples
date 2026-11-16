# Tibetan glacier monthly SAT reconstruction with source-complete bounded inputs

## Objective

Produce two 1 km-equivalent monthly surface-air-temperature rasters for the fixed Parlung window and dates 2019-01 and 2019-07. The window is 96.50–97.30 E, 29.00–29.70 N, on a 0.01 degree EPSG:4326 grid with 80 columns by 70 rows. Temperature is in degrees Celsius, finite, and bounded to [-80,50].

Method choices are not prescribed.

## Input

Use only `input/public_a.tar.gz`. The public projection contains Terra/Aqua day/night MODIS LST, MOD13A3 EVI, MCD43A3 albedo, SRTM elevation, ERA5 2 m temperature fallback/context, station SAT calibration labels, and `source_catalog.json` recording CMA, NCEI and TPDC/RGI provenance. Inspect archive contents, arrays, units, CRS, transform, nodata and missingness before calculation. Do not use network or external source versions.

## Prohibited data

Do not use the network, previous runs, hidden B/C, author rasters, host project files, other temperature products, target labels, or filenames as labels. Do not alter the supplied archive or create extra output files.

## Output

Create exactly four ordinary files in `output/`: `sat_201901.tif`, `sat_201907.tif`, `representative_sat.png`, and `method_report.md`.

Both GeoTIFFs must have the exact 80×70 shape, EPSG:4326 CRS and geotransform, finite floating-point temperature, and units degrees Celsius. `representative_sat.png` must be readable, non-blank, and show both months as spatial maps with longitude/latitude and station locations or a clearly labelled spatiotemporal panel. `method_report.md` must be at least 800 bytes and state source filenames and hashes, formula/features, station-level validation, regularization/fallback, units, uncertainty, grid checks and limitations. Include the literal tokens `RMSE`, `MBE`, `R2`, `MOD11A1`, `MYD11A1`, `MOD13A3`, `MCD43A3`, `SRTM`, `ERA5`, `CMA`, `NCEI`, `TPDC`, `self-check`, and `spatiotemporal`.

Before finishing, reopen all four files and verify exact names, raster shape, CRS, transform, finite/range checks, figure size and report tokens.

## Evaluation

Output-first raster delivery checks, then concealed C raster comparison and station-disjoint B comparison against the author spatial-transfer baseline are evaluated. Delivery, schema, physical validity, expert-product consistency and station-disjoint independent validation are evaluated. References, support, thresholds and scoring logic are private.
