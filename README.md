# dihiggs_boundary

`dihiggs_boundary` composes theory/model-point data, HiggsBounds/HiggsSignals results and versioned LLP-response information into analysis-ready boundary datasets.

External versions used by the existing HB/HS path:

- HiggsTools v1.2
  - HiggsBounds Dataset v1.7
  - HiggsSignals Dataset v1.1
- 2HDMC v1.8 for the historical compatibility evaluator

## Scientific ownership

The long-term model authority is `fbientrigo/dihiggs`, whose canonical producers own 2HDM construction, theory predicates, widths, BRs, lifetime and model-point provenance.

`dihiggs_boundary` should not become a second 2HDM authority. The historical `src/evaluate_point.cpp` is retained during migration because the current HB/HS adapter still needs its effective-coupling block. Its golden tests characterize compatibility behavior; they do not promote it over `dihiggs.point.v2`.

The August 2026 `dihiggs` work validated the native `h-H2-H2` convention, but the current `DihiggsPointV2Evaluator` does not yet serialize `g_hH2H2_GeV`. Boundary therefore consumes that observable when supplied and fails closed when it is missing; it does not recalculate the coupling.

See [`docs/modernization_llp_signal_v1.md`](docs/modernization_llp_signal_v1.md) for the migration audit and REUSE/MODERNIZE/DEPRECATE/ADD map.

## Pipelines

### Historical v0 path

```text
evaluate_point.csv
  -> dhb.enrich
  -> hbhs_enriched.csv
  -> dhb.atlas
  -> boundary_atlas.csv
```

`boundary_atlas_v0` remains supported for historical campaigns. Its `tag_*` columns are finder aids, not ATLAS DV+jets recast results.

### LLP-aware v1 path

```text
canonical/compatibility model row
  -> HB/HS enrichment
  -> hbhs_enriched.csv
  -> dhb.llp_signal + external versioned response
  -> llp_signal_enriched.csv
  -> dhb.atlas_v1
  -> boundary_atlas_v1.csv
```

`dhb.llp_signal` does **not** execute MadGraph or Pythia. It applies a declared production/recast response to the physically linked tuple:

```text
(m_H2_GeV, g_hH2H2_GeV, ctau_mm_H2, br_bb_H2)
```

with

```text
sigma_4b      = sigma_production * br_bb_H2^2
sigma_visible = sigma_4b * Trackless_Aeff
N_expected    = luminosity * sigma_visible
```

`BR_bb^2` is applied exactly once. The external calibration defines `sigma(g)`, Trackless `Aeff(ctau)`, its support, uncertainties, luminosity, `S95`, status and provenance.

There is deliberately **no built-in R14 absolute Aeff table**. A provisional or later validated response is supplied as a separate YAML artifact, so the unresolved absolute-Aeff calibration can change without rewriting boundary.

See:

- [`docs/llp_signal_contract.md`](docs/llp_signal_contract.md)
- [`docs/boundary_atlas_v1_contract.md`](docs/boundary_atlas_v1_contract.md)
- `contracts/llp_signal_enriched_v1.yaml`
- `contracts/boundary_atlas_v1.yaml`

## Domain semantics

The v1 signal stage never extrapolates silently. Each row receives one of:

```text
SUPPORTED
OUTSIDE_RECAST_CALIBRATION
MISSING_REQUIRED_OBSERVABLE
INVALID_CALIBRATION
```

The initial intended calibration domain is the Trackless response at `m_H2 = 150 GeV`. A future mass-dependent response should be introduced explicitly rather than reusing a 150 GeV curve at arbitrary mass.

Theory validity, HB/HS validity, signal-domain validity and signal usefulness remain separate fields.

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

## LLP signal + Atlas v1

Supply an explicit calibration artifact that satisfies `dhb.llp_signal_calibration.v1`:

```bash
bash scripts/run_llp_signal.sh \
  runs/<id> \
  /path/to/versioned_trackless_calibration.yaml

bash scripts/make_boundary_atlas_v1.sh runs/<id>
```

Outputs:

```text
runs/<id>/llp_signal_enriched.csv
runs/<id>/llp_signal_manifest.json
runs/<id>/boundary_atlas_v1.csv
runs/<id>/boundary_atlas_v1.parquet      # best effort
runs/<id>/boundary_atlas_v1_summary.json
runs/<id>/boundary_atlas_v1_manifest.json
```

A structurally invalid calibration still produces failure-marked signal rows and a manifest, then returns non-zero.

## Direct Python usage

```bash
python -m dhb.llp_signal \
  --input runs/<id>/hbhs_enriched.csv \
  --output runs/<id>/llp_signal_enriched.csv \
  --calibration /path/to/calibration.yaml

python -m dhb.atlas_v1 \
  --input runs/<id>/llp_signal_enriched.csv \
  --output-dir runs/<id>
```

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

## Plotting-ready output

`boundary_atlas_v1.csv` passes upstream columns through and adds the signal/classification fields, so downstream analysis can naturally construct, for example:

```text
3D: g_hH2H2_GeV vs ctau_mm_H2 vs br_bb_H2
color: N_expected / N_over_S95 / theory-HBHS-signal status / model parameter
```

This supports comparison between the effective `(g, ctau, BR_bb)` cube and the physically realizable cloud generated by 2HDM model points, without reducing that question to pairwise correlations.

## Historical context

[`docs/history/dihiggs_boundary_june2026.md`](docs/history/dihiggs_boundary_june2026.md) is a non-authoritative June 2026 source note. Current tracked contracts and implementation override it.
