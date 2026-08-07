# Modernization audit — canonical LLP observables and signal layer v1

Status: implementation contract for the `feat/llp-signal-boundary-atlas-v1` migration.

## Current-state audit

The repository HEAD before this work was `40086863f292616b201d046a1e758b5d696dcf99` (2026-07-18). The existing three-stage architecture is real and should be preserved:

```text
evaluate_point_v1 -> dhb.enrich -> dhb.atlas (boundary_atlas_v0)
```

`boundary_atlas_v0` is a derived classifier. Its `tag_*` fields are finder aids and are not ATLAS DV+jets recast results.

The maintained `dihiggs` repository advanced after the July snapshot. The h-H2-H2 convention was validated in August 2026 using `THDM::get_coupling_hhh(1,2,2,c)` and the benchmark artifact records `g_hH2H2_GeV = abs(Im(c))`. As of `dihiggs` commit `9f8019690c44bb68d46a3b60f5ac2ac349d445f2`, `DihiggsPointV2Evaluator` now serializes this canonical coupling directly in `dihiggs.point.v2`.

One migration gap remains: `dhb.enrich` needs the large HB/HS effective-coupling input block currently produced by `src/evaluate_point.cpp`. `dihiggs.point.v2` does not serialize that block. Therefore a direct replacement of `evaluate_point_v1` by `dihiggs.point.v2` would currently break the HB/HS stage.

## REUSE

- `python/dhb/contracts.py` and committed YAML mirrors.
- `python/dhb/schema.py` for cross-stage column ownership.
- `python/dhb/validate.py` and fail-loud boundary validation.
- atomic CSV writes and one-input-row -> one-output-row behavior.
- `dhb.enrich` as the HiggsBounds/HiggsSignals stage.
- `dhb.atlas` / `boundary_atlas_v0` for historical campaigns and finder tags.
- manifest conventions, git provenance helper and best-effort Parquet export.
- golden characterization of `evaluate_point_v1` as a migration oracle, not as a second scientific authority.

## MODERNIZE

- Treat `evaluate_point_v1` as compatibility production, not the long-term model authority.
- Resolve canonical/legacy serialized aliases through one migration bridge (`dhb.point_fields`).
- Move `BR_bb` derivation for the LLP signal path into that bridge so Boundary Atlas v1 never repeats width arithmetic.
- Add an explicit, versioned LLP-response stage between HB/HS and classification.
- Add a new atlas v1 rather than mutating historical v0 semantics.

## DEPRECATE

- New scientific development that adds more 2HDMC model construction to `src/evaluate_point.cpp`.
- Treating `tag_displaced_candidate` as a recast or sensitivity decision.
- Applying a 150 GeV Trackless response to arbitrary `mH`.
- Embedding an R14 absolute Aeff table in code or using it as a default before the absolute-calibration discrepancy is resolved.

`evaluate_point_v1` itself is not deleted by this migration. Historical campaigns and the HB/HS block still depend on it.

## ADD

The v1 path is additive:

```text
hbhs_enriched.csv
  -> dhb.llp_signal
  -> llp_signal_enriched.csv
  -> dhb.atlas_v1
  -> boundary_atlas_v1.csv
```

New responsibilities:

- `dhb.point_fields`: alias resolution only; no 2HDMC reconstruction and no coupling calculation.
- `dhb.llp_calibration`: validate a versioned external production/recast response and interpolate only inside declared support.
- `dhb.llp_signal`: normalize `(mH, g, ctau, BR_bb)`, apply `sigma(g)`, `BR_bb^2`, Trackless Aeff and luminosity exactly once, and record domain/calibration status.
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

Boundary consumes the serialized non-negative magnitude and never rederives this convention. Older or partial rows without the field remain valid historical inputs but receive:

```text
signal_domain_status = MISSING_REQUIRED_OBSERVABLE
signal_status = NOT_COMPUTED
```

### Still missing from the canonical handoff

The full HB/HS effective-coupling block required by `dhb.enrich` is not present in `dihiggs.point.v2`.

Boundary v1 does not fill that gap by reconstructing the 2HDM. The clean long-term fix is a core-owned HB/HS handoff/export, followed by retirement of the duplicated construction path after equivalence/regression gates pass.

## Scientific invariants of LLP signal v1

- `g_hH2H2_GeV` is a non-negative magnitude. A negative serialized value is invalid; boundary does not silently apply `abs()`.
- production response is supplied by the calibration; v1 currently accepts the measured `quadratic_anchor` form.
- `sigma_4b = sigma_production * BR_bb^2`.
- `sigma_visible = sigma_4b * Aeff`.
- `N_expected = luminosity * sigma_visible`.
- BR is applied exactly once.
- Aeff is never extrapolated outside the declared mass/lifetime domain.
- provisional calibrations remain visibly provisional in every row and in Atlas v1.
- `N_over_S95` is a response metric, not by itself a published exclusion likelihood.
