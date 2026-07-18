# dihiggs_boundary
Extension to the repo dihiggs, with the single goal of estabilishing the theoretical and experimental limits of variables using MCMC methods
Using versions:
- (HiggsTools v1.2)[https://gitlab.com/higgsbounds/higgstools/-/tree/v1.2?ref_type=tags]
  - (HiggsBounds Dataset v1.7)[https://gitlab.com/higgsbounds/hbdataset/-/tree/v1.7?ref_type=tags]
  - (HiggsSignals Dataset v1.1)[https://gitlab.com/higgsbounds/hsdataset/-/tree/v1.1?ref_type=tags]
- 2HDMC v1.8

## Pipeline

Three stages, connected by CSV (see `docs/evaluate_point_contract.md`,
`docs/hbhs_contract.md`, and `docs/boundary_atlas_contract.md`):

1. **Theory stage** (C++/2HDMC): LHS points -> `build/bin/evaluate_point`
   checks positivity/unitarity/perturbativity/stability and exports the
   HiggsBounds/HiggsSignals input block for the points that pass.
2. **Experiment stage** (python/HiggsTools): `python -m dhb.enrich` runs
   HiggsBounds + HiggsSignals over `theory_ok` points and appends
   `hb_allowed`, `hs_delta_chi2`, `exp_ok`, ... -> `hbhs_enriched.csv`.
3. **Atlas stage** (python, no HiggsTools needed): `python -m dhb.atlas`
   reads `hbhs_enriched.csv` and adds one explicit `region_class` verdict
   per point (`theory_fail`, `hbhs_not_run`, `hb_excluded`, `hs_tension`,
   `exp_fail`, `allowed_low_signal`) plus non-authoritative
   hh/diphoton/displaced/prompt candidate tags -> `boundary_atlas.csv` /
   `.parquet` (best-effort) + a summary and manifest for auditability.

```bash
source scripts/setup_env.sh
scripts/build_2hdmc.sh && scripts/build_evaluate_point.sh
scripts/build_higgstools.sh                      # pip install of lib/higgstools-v1.2 (build/venv)
build/venv/bin/pip install -e "python[test]"     # the dhb enrichment package

scripts/run_refined_lhs_boundary.sh 5000 12345   # theory scan into runs/<id>/
scripts/run_hbhs_enrichment.sh runs/<id>         # -> runs/<id>/hbhs_enriched.csv
scripts/make_boundary_atlas.sh runs/<id>         # -> runs/<id>/boundary_atlas.csv

# boundary maps for theory-and-experiment acceptance
python3 scripts/inspect_boundary_coordinates.py \
  --input runs/<id>/hbhs_enriched.csv --outdir runs/<id>/inspect_exp \
  --flag-column exp_ok
```

Tests: `build/venv/bin/python -m pytest` (unit tests need no HiggsTools;
`-m integration` exercises the real datasets). End-to-end smoke:
`scripts/smoke_enrich_hbhs.sh`.

Historical context: [`docs/history/dihiggs_boundary_june2026.md`](docs/history/dihiggs_boundary_june2026.md)
is a non-authoritative June 2026 source note. Current tracked contracts and
implementation override it.

### Next steps

- `scripts/make_boundary_atlas.sh runs/<id>` works standalone against any
  well-formed `hbhs_enriched.csv` (no HiggsTools build required for this
  stage). Try it against `runs/<id>/hbhs_enriched.csv` from an existing
  enrichment run.
- Parquet output is best-effort: neither `pyarrow` nor `pandas` is a
  declared dependency of `python/pyproject.toml`, so on a fresh
  environment `boundary_atlas.parquet` is skipped and the reason is
  recorded in `boundary_atlas_manifest.json`. Install `pyarrow` (or
  `pandas` with a parquet engine) in the venv if you want the parquet
  file produced.
- `configs/boundary_atlas_v0.yaml` holds the `hs_delta_chi2_max` and
  candidate-tag thresholds; adjust it and re-run
  `scripts/make_boundary_atlas.sh` to reclassify a run without
  re-running theory/HiggsTools.
- See `docs/boundary_atlas_contract.md` for exactly what `region_class`
  and the `tag_*` columns mean (and the explicit warning that the tags
  are finder-aids, not exclusions or paper-level recasts).

## Citing
