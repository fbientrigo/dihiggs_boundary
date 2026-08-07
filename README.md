# dihiggs_boundary

`dihiggs_boundary` composes theory/model-point data, HiggsBounds/HiggsSignals results, direct production results and versioned LLP-response information into analysis-ready boundary datasets.

External versions used by the existing HB/HS path:

- HiggsTools v1.2
  - HiggsBounds Dataset v1.7
  - HiggsSignals Dataset v1.1
- 2HDMC v1.8 for the historical compatibility evaluator

## Scientific ownership

The long-term model authority is `fbientrigo/dihiggs`, whose canonical producers own 2HDM construction, theory predicates, widths, BRs, lifetime and model-point provenance.

`dihiggs_boundary` should not become a second 2HDM authority. The historical `src/evaluate_point.cpp` is retained during migration because the current HB/HS adapter still needs its effective-coupling block. Its golden tests characterize compatibility behavior; they do not promote it over `dihiggs.point.v2`.

As of `fbientrigo/dihiggs` commit `9f8019690c44bb68d46a3b60f5ac2ac349d445f2`, `DihiggsPointV2Evaluator` serializes the validated canonical observable `g_hH2H2_GeV` directly in `dihiggs.point.v2`. Boundary consumes that field without recalculating the coupling convention and still fails closed for older/partial rows where it is absent.

Production cross sections are owned upstream by the MadGraph production layer. For new physical-point scans, Boundary requires the direct per-point fields `sigma_production_fb` and `sigma_production_unc_fb`; it does **not** infer a general cross section from `g_hH2H2_GeV`.

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
  -> join direct MadGraph production by point_id
  -> dhb.llp_signal + external Trackless response
  -> llp_signal_enriched.csv
  -> dhb.atlas_v1
  -> boundary_atlas_v1.csv
```

`dhb.llp_signal` does **not** execute MadGraph or Pythia. It combines the physically linked tuple

```text
(m_H2_GeV, g_hH2H2_GeV, ctau_mm_H2, br_bb_H2)
```

with the direct production result for that same point:

```text
sigma_production_fb
sigma_production_unc_fb
```

and then computes

```text
sigma_4b      = sigma_production * br_bb_H2^2
sigma_visible = sigma_4b * Trackless_Aeff
N_expected    = luminosity * sigma_visible
```

`BR_bb^2` is applied exactly once. The external calibration defines only the Trackless `Aeff(ctau)` response, its support, uncertainty, luminosity, `S95`, status and provenance.

For new physical-point scans there is no automatic `sigma ~ g^2` fallback. Such scaling can still be tested as a controlled diagnostic when only the relevant coupling changes and all other production ingredients are proven fixed.

The canonical 150 GeV absolute Trackless response is the frozen original/published R8/R10 response. The later `modified` analysis is a distinct selection and must not replace it silently. At the benchmark `ctau = 4.326221529733112 mm`, `Trackless_Aeff = 0.01573386`.

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

The current calibration domain is the Trackless response at `m_H2 = 150 GeV`. A future mass-dependent response should be introduced explicitly rather than reusing a 150 GeV curve at arbitrary mass.

Theory validity, HB/HS validity, production provenance, signal-domain validity and signal usefulness remain separate concepts.

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

Before the LLP signal stage, join the direct MadGraph result for each stable `point_id` so the input contains:

```text
sigma_production_fb
sigma_production_unc_fb
```

The MadGraph cards, logs, process definition, UFO provenance, PDF/scale settings and run metadata stay owned by the production repository rather than being duplicated here.

## LLP signal + Atlas v1

Supply an explicit Trackless response artifact that satisfies `dhb.llp_signal_calibration.v2`:

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
  --input runs/<id>/hbhs_plus_madgraph.csv \
  --output runs/<id>/llp_signal_enriched.csv \
  --calibration /path/to/trackless_calibration.yaml

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
color: sigma_production_fb / N_expected / N_over_S95 / model parameter
```

This supports comparison between physical 2HDM points and their DV+jets signal without pretending that production is determined by the trilinear magnitude alone.

## Historical context

[`docs/history/dihiggs_boundary_june2026.md`](docs/history/dihiggs_boundary_june2026.md) is a non-authoritative June 2026 source note. Current tracked contracts and implementation override it.
