# dihiggs_boundary
Extension to the repo dihiggs, with the single goal of estabilishing the theoretical and experimental limits of variables using MCMC methods
Using versions:
- (HiggsTools v1.2)[https://gitlab.com/higgsbounds/higgstools/-/tree/v1.2?ref_type=tags]
  - (HiggsBounds Dataset v1.7)[https://gitlab.com/higgsbounds/hbdataset/-/tree/v1.7?ref_type=tags]
  - (HiggsSignals Dataset v1.1)[https://gitlab.com/higgsbounds/hsdataset/-/tree/v1.1?ref_type=tags]
- 2HDMC v1.8

## Pipeline

Two stages, connected by CSV (see `docs/evaluate_point_contract.md` and
`docs/hbhs_contract.md`):

1. **Theory stage** (C++/2HDMC): LHS points -> `build/bin/evaluate_point`
   checks positivity/unitarity/perturbativity/stability and exports the
   HiggsBounds/HiggsSignals input block for the points that pass.
2. **Experiment stage** (python/HiggsTools): `python -m dhb.enrich` runs
   HiggsBounds + HiggsSignals over `theory_ok` points and appends
   `hb_allowed`, `hs_delta_chi2`, `exp_ok`, ...

```bash
source scripts/setup_env.sh
scripts/build_2hdmc.sh && scripts/build_evaluate_point.sh
scripts/build_higgstools.sh                      # pip install of lib/higgstools-v1.2 (build/venv)
build/venv/bin/pip install -e "python[test]"     # the dhb enrichment package

scripts/run_refined_lhs_boundary.sh 5000 12345   # theory scan into runs/<id>/
scripts/run_hbhs_enrichment.sh runs/<id>         # -> runs/<id>/hbhs_enriched.csv

# boundary maps for theory-and-experiment acceptance
python3 scripts/inspect_boundary_coordinates.py \
  --input runs/<id>/hbhs_enriched.csv --outdir runs/<id>/inspect_exp \
  --flag-column exp_ok
```

Tests: `build/venv/bin/python -m pytest` (unit tests need no HiggsTools;
`-m integration` exercises the real datasets). End-to-end smoke:
`scripts/smoke_enrich_hbhs.sh`.

## Citing
