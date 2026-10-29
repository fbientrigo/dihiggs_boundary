# dihiggs_boundary

`dihiggs_boundary` composes theory/model-point data, HiggsBounds/HiggsSignals results, and direct production results into analysis-ready boundary datasets.

External versions used by the existing HB/HS path:

- HiggsTools v1.2
  - HiggsBounds Dataset v1.7
  - HiggsSignals Dataset v1.1
- 2HDMC v1.8 for the historical compatibility evaluator: the patched copy in `dihiggs/2hdmc`
  (`$DHB_2HDMC_ROOT`, default `../dihiggs/2hdmc`; the vendored `lib/2HDMC-1.8.0` is in lake
  `20261028T200807Z-d116d2`)

## Scientific ownership

The long-term model authority is `fbientrigo/dihiggs`, whose canonical producers own 2HDM construction, theory predicates, widths, BRs, lifetime and model-point provenance.

`dihiggs_boundary` should not become a second 2HDM authority. The historical `src/evaluate_point.cpp` is retained during migration because the current HB/HS adapter still needs its effective-coupling block. Its golden tests characterize compatibility behavior; they do not promote it over `dihiggs.point.v2`.

As of `fbientrigo/dihiggs` commit `9f8019690c44bb68d46a3b60f5ac2ac349d445f2`, `DihiggsPointV2Evaluator` serializes the validated canonical observable `g_hH2H2_GeV` directly in `dihiggs.point.v2`. Boundary consumes that field without recalculating the coupling convention and still fails closed for older/partial rows where it is absent.

Production cross sections are owned upstream by the MadGraph production layer. For new physical-point scans, Boundary requires the direct per-point fields `sigma_production_fb` and `sigma_production_unc_fb`; it does **not** infer a general cross section from `g_hH2H2_GeV`.


## Pipelines

### Historical v0 path

```text
evaluate_point.csv
  -> dhb.enrich
  -> hbhs_enriched.csv
  -> dhb.atlas
  -> boundary_atlas.csv
```

`boundary_atlas_v0` remains supported for historical campaigns. Its `tag_*` columns are finder aids.

## Campaign layout

One rule: `campaigns/<id>/campaign.yaml` is tracked; everything else under `campaigns/<id>/` (raw points, leaves, `*_state.json`, manifests, aggregates) is ignored and lives in the lake. The old `data/runs/<id>/` layout is gone: pass `--output-dir campaigns/<id>` (resumable `*_state.json` are found there; `lake sync` never prunes `*_state.json` or `*.yaml`). Restore a campaign with `python ../lake/lake.py restore <cid> campaigns/<id>` (find `<cid>` with `python ../lake/lake.py ls | grep <id>`), e.g. survivor v2: `20261013T000618Z-8292bb`.

## Setup

```bash
source scripts/setup_env.sh
scripts/build_2hdmc.sh && scripts/build_evaluate_point.sh
scripts/build_higgstools.sh
build/venv/bin/pip install -e "python[test]"
```

## Existing theory + HB/HS production

```bash
scripts/run_refined_lhs_boundary.sh 5000 12345
scripts/run_hbhs_enrichment.sh runs/<id>
```

This produces `runs/<id>/hbhs_enriched.csv` using the compatibility theory/HBHS path.

`dhb.join_signal` joins the production cross section onto those points by `point_id`. It takes sigma only from the table
that `dihiggs_hep_cross/state/CURRENT_CAMPAIGN.yaml` registers (`madgraph.authoritative_results`); with none
registered (today: `null`), no row gets a sigma:

```bash
python -m dhb.join_signal --points runs/<id>/hbhs_enriched.csv \
  --registry ../dihiggs_hep_cross/state/CURRENT_CAMPAIGN.yaml \
  --output runs/<id>/hbhs_plus_sigma.csv
```

The MadGraph cards, logs, process definition, UFO provenance, PDF/scale settings and run metadata stay owned by the production repository rather than being duplicated here.

## Contracts and validation

The repository follows:

```text
contract -> implementation -> YAML mirror -> validator/test
```

Regenerate the committed mirrors with:

```bash
python -m dhb.contracts --emit contracts
```

Run tests with:

```bash
build/venv/bin/python -m pytest
```

Unit tests do not require HiggsTools. Tests marked `integration` exercise the real external datasets.

## Historical context

[`docs/history/dihiggs_boundary_june2026.md`](docs/history/dihiggs_boundary_june2026.md) is a non-authoritative June 2026 source note. Current tracked contracts and implementation override it.
