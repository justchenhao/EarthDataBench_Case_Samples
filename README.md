# EarthDataBench: seven representative cases

Date: 2026-11-16

This package presents seven complete cases, one from each scientific domain, to demonstrate the benchmark's scientific workflows, data products, and cumulative evaluation. It is a representative-case showcase rather than a paper snapshot or leaderboard.

## Representative cases

Archive paths use short display labels without version suffixes. The `task/task_card.json` files retain the canonical case IDs required by the evaluators, and `selection_manifest.json` records the mapping to those source IDs. The package exposes two prompt variants only: Base and Open. Open contains the complete prompt formerly labelled Hard, and no separate Hard prompt remains.

| Domain | Archive directory | Canonical case ID | Scientific workflow and evaluation coverage |
|---|---|---|---|
| Atmosphere | `atmosphere/antarctic_t2m/` | `atmosphere/antarctic_monthly_t2m_reconstruction` | Long-term station/reanalysis reconstruction with regional and station-based C+B checks. |
| Cryosphere | `cryosphere/tp_glacier_sat/` | `cryosphere/tp_glacier_sat_station_correction_v13` | Satellite/station SAT reconstruction. C uses author-published grids; B is observed station truth; the reconstructed stacking model is only the B comparator. |
| Biosphere | `ecology/sierra_eft/` | `ecology/sierra_nevada_eft_v09` | Multi-year EVI/EFT production with circular phenology errors and explicit cumulative regression coverage. |
| Terrestrial Hydrosphere | `hydrology/fluxnet_et/` | `hydrology/fluxnet2015_et_benchmark_v05` | Site-specific two-stage RF prolongation. C is a three-site subset of the author Zenodo V1.0 product; B is independent post-2014 tower LE. |
| Land Surface | `land/lucas_crop/` | `land/crop_sequence_eu_lucas_2012_2018` | Point-based crop-sequence classification with public semantic checks and independent spatial/block validation. |
| Oceans | `ocean/atlantic_d13c/` | `ocean/atlantic_d13c_dic_gpr_v03` | DIC-isotope point, gridded and uncertainty products with independent North/South validation. |
| Solid Earth | `solid_earth/hust_grace/` | `solid_earth/hust_grace2024_paper_evaluation_v24` | Official GFC archive parsing, damaged-member recovery, low-degree/spectrum products, TN-14 B validation and moving-block S4. |

## Directory roles and evaluation boundary

Each case contains `input/`, `task/`, `reference/`, and `expert_product/`.

- `input/`: scientific production inputs available to the agent.
- `task/`: Base/Open prompts, output contract, runtime configuration, and canonical host bridge. Open uses the former Hard prompt content.
- `reference/`: evaluator and private validation material.
- `expert_product/`: reference product or declared deterministic derivative.

**Evaluation boundary:** the package includes evaluator and validation material so that scientific scoring can be inspected. Do not mount `reference/` or `expert_product/` into an agent's runtime. Agent execution must expose only the declared public task and input boundary.

## Scoring structure

Scores are 0.0/0.2/0.4/0.6/0.8/1.0 for S0/S1/S2/S3/S4/S5. Evaluation is cumulative: S3 requires both the C tolerance and independent-B non-inferiority; S4 inherits S3 and adds predefined B improvement; S5 inherits S4 and adds a second validation axis or stronger frozen B evidence. S2 may include coarse C/B checks as part of task-specific scientific consistency; it is not claimed to be reference-free across every task.

The cases retain their own metrics, supports, thresholds, and environment requirements. See each `task/evaluator_usage.md`, `task/run_config.yaml`, and `reference/evaluator/verify.py`. There is no claim that all seven evaluators share one Python environment or run without their declared dependencies.

## Integrity

Every case includes `task/manifest.sha256`, covering all case files except the manifest itself. `selection_manifest.json` records case IDs, file counts, byte totals, and current task-card/manifest hashes. All seven source packages passed the canonical package validator before inclusion, and the two-prompt transformation and regenerated metadata were checked during package assembly.
