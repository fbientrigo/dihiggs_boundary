# Modernization audit — canonical LLP observables and signal layer v1

Status: implementation contract for the LLP-aware Boundary v1 migration.

## Current-state audit

The existing three-stage architecture remains supported:

```text
evaluate_point_v1 -> dhb.enrich -> dhb.atlas (boundary_atlas_v0)
```

`boundary_atlas_v0` is a derived classifier. Its `tag_*` fields are finder aids and are not ATLAS DV+jets recast results.

The maintained `dihiggs` repository advanced after the July snapshot. The h-H2-H2 convention was validated in August 2026 using `THDM::get_coupling_hhh(1,2,2,c)` and the benchmark artifact records `g_hH2H2_GeV = abs(Im(c))`. As of `dihiggs` commit `9f8019690c44bb68d46a3b60f5ac2ac349d445f2`, `DihiggsPointV2Evaluator` serializes this canonical coupling directly in `dihiggs.point.v2`.

One migration gap remains: `dhb.enrich` needs the large HB/HS effective-coupling input block currently produced by `src/evaluate_point.cpp`. `dihiggs.point.v2` does not serialize that block. Therefore a direct replacement of `evaluate_point_v1` by `dihiggs.point.v2` would currently break the HB/HS stage.

A second design point was resolved before physical scan production: Boundary must not promote the controlled benchmark relation `sigma ~ g^2` into a general cross-section model. When a full physical 2HDM point changes, additional couplings, widths, interference or kinematics may change as well. MadGraph is sufficiently lightweight that the safer default is a direct production evaluation per physical point.

## REUSE

- `python/dhb/contracts.py` and committed YAML mirrors.
- `python/dhb/schema.py` for cross-stage column ownership.
- `python/dhb/validate.py` and fail-loud boundary validation.
- atomic CSV writes and one-input-row -> one-output-row behavior.
- `dhb.enrich` as the HiggsBounds/HiggsSignals stage.
- `dhb.atlas` / `boundary_atlas_v0` for historical campaigns and finder tags.
- manifest conventions, git provenance helper and best-effort Parquet export.
- golden characterization of `evaluate_point_v1` as a migration oracle, not as a second scientific authority.
- the existing MadGraph contracts and run infrastructure in `dihiggs_hep_cross` rather than rebuilding production machinery in Boundary.

## MODERNIZE

- Treat `evaluate_point_v1` as compatibility production, not the long-term model authority.
- Resolve canonical/legacy serialized aliases through one migration bridge (`dhb.point_fields`).
- Move `BR_bb` derivation for the LLP signal path into that bridge so Boundary Atlas v1 never repeats width arithmetic.
- Add an explicit, versioned LLP-response stage between HB/HS and classification.
- Join a direct MadGraph production result to each stable physical `point_id` before signal evaluation.
- Keep Trackless response calibration separate from production normalization.
- Add a new atlas v1 rather than mutating historical v0 semantics.

## DEPRECATE

- New scientific development that adds more 2HDMC model construction to `src/evaluate_point.cpp`.
- Treating `tag_displaced_candidate` as a recast or sensitivity decision.
- Applying a 150 GeV Trackless response to arbitrary `mH`.
- Using the later `modified` Trackless analysis response as if it were the published/original ATLAS Trackless selection.
- Using a coupling-rescaled production cross section as the default for varying physical 2HDM points.

`evaluate_point_v1` itself is not deleted by this migration. Historical campaigns and the HB/HS block still depend on it.

## ADD

The v1 path remains simple:

```text
hbhs_enriched.csv
  + MadGraph sigma per point
  -> dhb.llp_signal
  -> llp_signal_enriched.csv
  -> dhb.atlas_v1
  -> boundary_atlas_v1.csv
```

New responsibilities:

- `dhb.point_fields`: alias resolution only; no 2HDMC reconstruction and no coupling calculation.
- `dihiggs_hep_cross` / MadGraph layer: production cross section and integration uncertainty for each physical point, with production provenance.
- `dhb.llp_calibration`: validate a versioned external Trackless response and interpolate only inside declared support. Calibration v2 contains no production model.
- `dhb.llp_signal`: normalize `(mH, g, ctau, BR_bb)`, consume the direct per-point MadGraph cross section, apply `BR_bb^2`, Trackless Aeff and luminosity exactly once, and record domain/calibration status.
- `dhb.atlas_v1`: classify already-computed theory, HB/HS and signal states without executing new physics.

## Canonical point handoff status

### Already owned by `dihiggs.point.v2`

The canonical producer owns model-point identity/provenance, model parameters, theory flags, H2 widths, selected BRs, `ctau_mm`, and the validated `h-H2-H2` production coupling.

The migration bridge recognizes the following serialized aliases:

| Boundary-normalized field | Canonical `dihiggs.point.v2` field |
|---|---|
| `m_H2_GeV` | `mH_input_GeV` |
| `g_hH2H2_GeV` | `g_hH2H2_GeV` |
| `ctau_mm_H2` | `ctau_mm` |
| `br_bb_H2` | `br_bb` |
| `width_bb_H2` | `width_bb_GeV` |
| `total_width_H2` | `total_width_GeV` |

If both canonical and legacy aliases are present, they must agree or the signal row fails closed.

The coupling convention is core-owned and frozen upstream:

```text
2HDMC: c = -i*g
g_hH2H2_GeV = abs(Im(c))
UFO: GHphiphi = Im(c) = -g_hH2H2_GeV
```

Boundary consumes the serialized non-negative magnitude and never rederives this convention.

### Production handoff

A physical row entering `dhb.llp_signal` must additionally carry:

```text
sigma_production_fb
sigma_production_unc_fb
```

These values come from MadGraph for that same physical point. Boundary does not reconstruct them from `g_hH2H2_GeV`.

The earlier R9/R10 `g^2` scaling studies remain scientifically useful evidence for the restricted one-coupling benchmark setup. They are not promoted into a general physical-point production law.

### Trackless response handoff

The absolute-efficiency discrepancy is closed for the canonical ATLAS Trackless interpretation:

```text
canonical analysis = original/published Trackless
m_H2 = 150 GeV
ctau = 4.326221529733112 mm
Trackless_Aeff = 0.01573386
```

The later `modified` analysis response is a different selection and is retained only under that distinct interpretation. The historical weighted-Aeff uncertainty convention is still provisional and must not be presented as a detector systematic.

### Still missing from the canonical handoff

The full HB/HS effective-coupling block required by `dhb.enrich` is not present in `dihiggs.point.v2`.

Boundary v1 does not fill that gap by reconstructing the 2HDM. The clean long-term fix is a core-owned HB/HS handoff/export, followed by retirement of the duplicated construction path after equivalence/regression gates pass.

## Scientific invariants of LLP signal v1

- `g_hH2H2_GeV` is a non-negative magnitude. A negative serialized value is invalid; Boundary does not silently apply `abs()`.
- production normalization is a direct per-physical-point MadGraph input.
- no automatic `sigma(g)` or `g/g0` scaling is available in Boundary.
- `sigma_4b = sigma_production * BR_bb^2`.
- `sigma_visible = sigma_4b * Aeff`.
- `N_expected = luminosity * sigma_visible`.
- BR is applied exactly once.
- Aeff is never extrapolated outside the declared mass/lifetime domain.
- the canonical 150 GeV response uses the original/published R8/R10 Trackless selection.
- provisional response uncertainties remain visibly provisional.
- `N_over_S95` is a response metric, not by itself a published exclusion likelihood.
