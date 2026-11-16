# Antarctic Monthly Near-Surface Air Temperature Anomaly Reconstruction

## Objective

Construct a monthly gridded reconstruction of Antarctic 2 m air-temperature anomalies from January 1958 through December 2022. The formal target is `t2m_anomaly` in K on the 114 x 114, nominal 60 km polar-stereographic grid defined by `input/grid/grid_template.nc`. Anomalies and standard deviations use 1981-2010 as the reference period and are calculated separately for each calendar month. A temperature increment of 1 K equals an increment of 1 degree Celsius.

The product is intended for large-scale, long-term Antarctic temperature variability; it is not expected to resolve local effects of complex terrain.

Method choices are not prescribed.

## Input

- `input/era5/`: ERA5 global monthly-mean 2 m temperature for 1979-2022 in the original 0.25 degree GRIB representation. It contains 528 consecutive monthly fields on a 1440 x 721 regular latitude-longitude grid; the GRIB short name is `2t` and the unit is K.
- `input/stations/reader/`: complete released monthly-temperature text files for 13 anchor stations. The first line is the station name; subsequent rows contain a year and 12 monthly means in degrees Celsius. `-` denotes missing data, and files include years outside the task period.
- `input/stations/ghcnm/`: current GHCNm v4 QCF and QFE global fixed-width TAVG files and inventories. Monthly values are stored in 0.01 degrees Celsius with quality flags; `-9999` denotes missing data.
- `input/stations/byrd/`: a dedicated Byrd monthly-temperature record in text form. It contains valid values for 1957-2025 and an empty 2026 placeholder; use only 1958-2022.
- `input/stations/south_pole/`: a complete South Pole source ZIP containing yearly archives and monthly LCD text files.
- `input/grid/grid_template.nc`: a target-free NetCDF3 spatial template containing two-dimensional `lat`, `lon`, `HGT`, `LANDMASK`, and projection attributes. Preserve these spatial support fields exactly.

The 15 anchors and coordinates used to relate station temperatures to ERA5 are Belgrano II (-77.90, -34.60), Byrd (-80.10, -119.32), Casey (-66.30, 110.50), Davis (-68.60, 78.00), Dumont d'Urville (-67.00, 140.00), Esperanza (-63.20, -56.59), Faraday/Vernadsky (-65.10, -65.15), Mawson (-67.60, 62.90), Mirny (-66.50, 93.00), Novolazarevskaya (-70.50, 11.49), Orcadas (-60.40, -44.44), Scott Base (-77.50, 166.45), South Pole (-90.00, 0.00), Syowa (-69.00, 39.35), and Vostok (-78.50, 106.90), with coordinates given as latitude and longitude in degrees.

## Prohibited data

- Use only the listed public production inputs for scientific construction. Do not use any ready-made Antarctic temperature reconstruction, mirror, cache, derived target statistic, product-generating program, or precomputed weight file.
- Do not seek or use held-out validation stations, the private expert field or figure, private matching locations, scoring baselines, or thresholds.
- Submit code that regenerates the results from `input/`. Do not hard-code target fields or private values and do not draw an answer manually.

## Output

1. `output/antarctic_t2m_anomaly.nc`: NETCDF4 with dimensions exactly `time=780`, `south_north=114`, and `west_east=114`. It must contain `time`, `lat`, `lon`, `HGT`, `LANDMASK`, and the sole target variable `t2m_anomaly(time,south_north,west_east)`. Spatial support fields must equal the template values. Time is the first day of every month from 1958-01 through 2022-12, with units `days since 1951-01-01 00:00:00` and the standard calendar. The target is float32 in K with fill value `-999.9f`.
2. `output/representative.png`: readable and non-blank. Plot the cellwise arithmetic mean of the 12 submitted fields in 2022, on the template projection's x/y coordinates in km. Mask `LANDMASK < 0.5`, use `RdBu_r` with fixed limits -2.5 to 2.5 K and equal aspect, and include a colorbar, title, and axis labels without external overlays.
3. `output/method_report.md`: document input investigation, processing and modeling choices, missing-data treatment, quality control, software environment, and known limitations.
4. `output/reproduce.py`: an entry point that regenerates the NetCDF and figure from `input/`; it may call local modules included in the submission.

All 780 target months must be finite wherever `LANDMASK >= 0.1`. Outside that support, values may be finite extrapolations or `-999.9f`, but any missing mask must be static through time. The field-quality core is `LANDMASK >= 0.5`. A separately submitted station series, weight field, or ERA5 diagnostic is not an alternative validation target.

## Evaluation

Evaluation directly targets the submitted `t2m_anomaly`. It checks artifact completeness; file schema, time, coordinates, units, and coverage; monthly error, correlation, spatial structure, seasonality, and long-term trend consistency against a private expert field; bias, RMSE, linearly detrended Pearson correlation, centered fractional variance explained, and trend consistency at held-out stations using frozen private matching; physical plausibility; reference-period and anchor closure; reproducibility; and agreement of the representative figure with its deterministic plot contract. Held-out comparisons use the intersection of the task period and each observation record. Trends use annual means with at least nine paired months and require at least ten valid annual means for a station.
