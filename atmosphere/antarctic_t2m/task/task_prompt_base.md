# Antarctic Monthly Near-Surface Air Temperature Anomaly Reconstruction

## Objective

Construct a monthly gridded reconstruction of Antarctic 2 m air-temperature anomalies from January 1958 through December 2022. The formal target is `t2m_anomaly` in K on the 114 x 114, nominal 60 km polar-stereographic grid defined by `input/grid/grid_template.nc`. Anomalies and standard deviations use 1981-2010 as the reference period and are calculated separately for each calendar month. A temperature increment of 1 K equals an increment of 1 degree Celsius.

The product is intended for large-scale, long-term Antarctic temperature variability; it is not expected to resolve local effects of complex terrain.

## Input

- `input/era5/`: ERA5 global monthly-mean 2 m temperature for 1979-2022 in the original 0.25 degree GRIB representation. It contains 528 consecutive monthly fields on a 1440 x 721 regular latitude-longitude grid; the GRIB short name is `2t` and the unit is K.
- `input/stations/reader/`: complete released monthly-temperature text files for 13 anchor stations. The first line is the station name; subsequent rows contain a year and 12 monthly means in degrees Celsius. `-` denotes missing data, and files include years outside the task period.
- `input/stations/ghcnm/`: current GHCNm v4 QCF and QFE global fixed-width TAVG files and inventories. Monthly values are stored in 0.01 degrees Celsius with quality flags; `-9999` denotes missing data.
- `input/stations/byrd/`: the dedicated Byrd monthly-temperature reconstruction in text form. It contains valid values for 1957-2025 and an empty 2026 placeholder; use only 1958-2022.
- `input/stations/south_pole/`: the complete South Pole source ZIP, containing yearly ZIP archives and monthly LCD text files. Prefer a declared `AVG MONTHLY` value; if absent, calculate the monthly mean from valid daily means and document the choice.
- `input/grid/grid_template.nc`: a target-free NetCDF3 spatial template containing two-dimensional `lat`, `lon`, `HGT`, `LANDMASK`, and projection attributes. Preserve the floating-point `LANDMASK` field exactly rather than replacing it with a binary mask.

The station coordinates used for ERA5 interpolation are:

| Anchor | Latitude | Longitude |
|---|---:|---:|
| Belgrano II | -77.90 | -34.60 |
| Byrd | -80.10 | -119.32 |
| Casey | -66.30 | 110.50 |
| Davis | -68.60 | 78.00 |
| Dumont d'Urville | -67.00 | 140.00 |
| Esperanza | -63.20 | -56.59 |
| Faraday/Vernadsky | -65.10 | -65.15 |
| Mawson | -67.60 | 62.90 |
| Mirny | -66.50 | 93.00 |
| Novolazarevskaya | -70.50 | 11.49 |
| Orcadas | -60.40 | -44.44 |
| Scott Base | -77.50 | 166.45 |
| South Pole | -90.00 | 0.00 |
| Syowa | -69.00 | 39.35 |
| Vostok | -78.50 | 106.90 |

## Product construction

1. Inspect and document every input format, coverage, unit, missing-value code, and quality flag. Map records explicitly by station name, coordinates, and GHCNm identifier. Convert monthly temperatures to degrees Celsius before calculating anomalies.
2. Use READER as the general primary record. Use QCF for applicable short gaps and QFE where the source strategy calls for extended estimates, retaining a source audit. In particular, use QFE for Belgrano II in 1961-1979, 1980-01 through 1980-09, 1981-01 through 1981-05, and 2002-03 through 2003-03; Davis in 1964-11 through 1969-02; Syowa in 1962-02 through 1966-01; and Vostok in 1962-01 through 1963-01, 1994-02 through 1994-11, all of 1996, and 2003-02 through 2004-02.
3. Belgrano II has no direct record for 1958-1960. Estimate it separately for each calendar month using the 1958-1960 Belgrano I and Halley records in GHCNm and months in which Halley and Belgrano II overlap. Report the fitted model and cross-validation.
4. Use the dedicated Byrd and South Pole inputs throughout the task period. For Dumont d'Urville in 2014-04, 2014-11, 2015-01 through 2015-06, 2015-09 through 2015-10, 2016-01, 2016-03 through 2016-06, and 2016-08 through 2016-12, and for Scott Base in 2016-2022, use values actually present in READER and otherwise retain missing values. Also retain Scott Base 1994-01 through 1994-02 as missing. Do not fabricate absent values from an unprovided source.
5. For each anchor and calendar month, calculate the 1981-2010 climatological mean and standard deviation from valid observations, then form the standardized station anomaly. Never interpret missing values as zero; document any defensible treatment of an invalid standard deviation.
6. Bilinearly interpolate ERA5 to the anchor coordinates and template grid. For each calendar month, use the 1979-2022 ERA5 series, form anomalies relative to 1981-2010, and linearly detrend them. At each grid cell, calculate the Pearson correlation with each anchor, its sign, and the anchor covariance or correlation structure. Use squared station-grid correlation as the spatial linkage strength and ordinary-kriging optimization to account for redundancy among anchors while constraining the weights to sum to one. Make the handling of negative weights and ill-conditioned systems reproducible.
7. For grid point `x`, calendar month `m`, and time `t`, reconstruct the anomaly as

   `A_hat(x,t) = sigma_ERA5(x,m) * sum_[i in I(t)] { eta_i(x,m) * w_i(x,m,I(t)) * [(T_i(t)-mu_i(m))/sigma_i(m)] }`,

   where `I(t)` is the set of anchors available at `t`, `eta_i` is the sign of the detrended ERA5 station-grid correlation, and the non-signed spatial linkage is based on its squared magnitude. Re-solve the weights for the available subset: use 13 anchors in 1958 without Syowa and Novolazarevskaya, 14 in 1959-1960 without Novolazarevskaya, and never replace another missing anchor anomaly with zero.
8. Check anchor closure, time continuity, monthly weight sums, finite coverage, units, extremes, spatial discontinuities, and the 1981-2010 monthly-anomaly closure. Record methodological choices, missing anchors, and quality-control results in the report.

## Prohibited data

- Use only the listed public production inputs for scientific construction. Do not use any ready-made Antarctic temperature reconstruction, mirror, cache, derived target statistic, product-generating program, or precomputed weight file.
- Do not seek or use held-out validation stations, the private expert field or figure, private matching locations, scoring baselines, or thresholds.
- Submit code that regenerates the results from `input/`. Do not hard-code target fields or private values and do not draw an answer manually.

## Output

1. `output/antarctic_t2m_anomaly.nc`: NETCDF4 with dimensions exactly `time=780`, `south_north=114`, and `west_east=114`. It must contain `time`, `lat`, `lon`, `HGT`, `LANDMASK`, and the sole target variable `t2m_anomaly(time,south_north,west_east)`. Spatial support fields must equal the template values. Time is the first day of every month from 1958-01 through 2022-12, with units `days since 1951-01-01 00:00:00` and the standard calendar. The target is float32 in K with fill value `-999.9f`.
2. `output/representative.png`: readable and non-blank. Plot the cellwise arithmetic mean of the 12 submitted fields in 2022, on the template projection's x/y coordinates in km. Mask `LANDMASK < 0.5`, use `RdBu_r` with fixed limits -2.5 to 2.5 K and equal aspect, and include a colorbar, title, and axis labels without external overlays.
3. `output/method_report.md`: document input inspection, station mapping and source priority, missing-data treatment, spatial estimation, quality control, software environment, and known limitations.
4. `output/reproduce.py`: an entry point that regenerates the NetCDF and figure from `input/`; it may call local modules included in the submission.

All 780 target months must be finite wherever `LANDMASK >= 0.1`. Outside that support, values may be finite extrapolations or `-999.9f`, but any missing mask must be static through time. The field-quality core is `LANDMASK >= 0.5`. A separately submitted station series, weight field, or ERA5 diagnostic is not an alternative validation target.

## Evaluation

Evaluation directly targets the submitted `t2m_anomaly`. It checks artifact completeness; file schema, time, coordinates, units, and coverage; monthly error, correlation, spatial structure, seasonality, and long-term trend consistency against a private expert field; bias, RMSE, linearly detrended Pearson correlation, centered fractional variance explained, and trend consistency at held-out stations using frozen private matching; physical plausibility; reference-period and anchor closure; reproducibility; and agreement of the representative figure with its deterministic plot contract. Held-out comparisons use the intersection of the task period and each observation record. Trends use annual means with at least nine paired months and require at least ten valid annual means for a station.
