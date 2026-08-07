# LLP signal enrichment contract v1

Schema: `llp_signal_enriched_v1`  
Producer: `python -m dhb.llp_signal`  
Input: normally `hbhs_enriched.csv`  
Output: `llp_signal_enriched.csv` + `llp_signal_manifest.json`

## Responsibility

`dhb.llp_signal` maps already-computed model observables onto an already-calibrated DV+jets response. It does **not** reconstruct a 2HDM point and does **not** execute MadGraph, Pythia or the ATLAS recast.

```text
model/HBHS row
  + versioned production/recast calibration
  -> normalized (mH, g, ctau, BR_bb)
  -> sigma_production
  -> Trackless_Aeff
  -> sigma_visible
  -> N_expected / S95
```

The stage preserves every input row.

## Required physical observables

The normalized LLP tuple is:

```text
m_H2_GeV
g_hH2H2_GeV
ctau_mm_H2
br_bb_H2
```

`dhb.point_fields` accepts documented serialized aliases. It does not compute `g_hH2H2_GeV` from 2HDMC. If both canonical and legacy aliases are present, finite values must agree or the observable is treated as missing/invalid.

For `BR(H2->bb)`, an explicit serialized `br_bb`/`br_bb_H2` is preferred. If it is absent, the bridge may derive exactly once:

```text
br_bb_H2 = width_bb_H2 / total_width_H2
```

using widths from the same row. If both forms are present, they must agree.

## Calibration schema

The calibration is an **external file** with schema:

```text
dhb.llp_signal_calibration.v1
```

There is deliberately no built-in R8/R10/R14 calibration. The unresolved absolute-Aeff comparison can therefore be settled by changing the calibration artifact without changing the architecture.

Required structure:

```yaml
schema_version: dhb.llp_signal_calibration.v1
calibration_version: <immutable human-readable id>
calibration_status: PROVISIONAL  # or VALIDATED

domain:
  m_H2_GeV:
    value: 150.0
    abs_tolerance: <declared numerical/model tolerance>
  ctau_min_mm: <positive lower support>
  ctau_max_mm: <positive upper support>

production:
  model: quadratic_anchor
  anchor_g_GeV: <validated anchor magnitude>
  anchor_sigma_fb: <production cross section>
  anchor_sigma_unc_fb: <absolute uncertainty>

acceptance:
  analysis: Trackless
  model: log_linear_ctau
  points:
    - {ctau_mm: <x1>, aeff: <a1>, aeff_unc: <u1>}
    - {ctau_mm: <x2>, aeff: <a2>, aeff_unc: <u2>}
    # strictly increasing ctau; table must cover declared domain

normalization:
  luminosity_fb: 139.0
  S95: <frozen signal-yield threshold>

classification:
  near_fraction: <fractional band around N/S95 = 1>

provenance:
  # free-form artifact identifiers, commits, hashes, campaign ids, etc.
```

Only `PROVISIONAL` and `VALIDATED` are accepted calibration states. A structurally invalid calibration produces failure-marked rows, a failure manifest and a non-zero exit status.

## Response arithmetic

For a supported point:

```text
sigma_production(g)
  = sigma_anchor * (g / g_anchor)^2

sigma_4b
  = sigma_production * BR_bb^2

sigma_visible
  = sigma_4b * Trackless_Aeff

N_expected
  = luminosity * sigma_visible

N_over_S95
  = N_expected / S95
```

`BR_bb^2` is applied exactly once in this stage. The recast calibration is defined for samples where `H2 -> bb` is forced, so `Trackless_Aeff` must not contain an additional physical BR factor.

The v1 uncertainty propagation treats the declared production and Aeff uncertainties as independent absolute uncertainties:

```text
(delta sigma_visible)^2
  = (BR_bb^2 * Aeff * delta sigma_production)^2
  + (BR_bb^2 * sigma_production * delta Aeff)^2
```

No BR uncertainty is introduced by v1 because the current model row supplies BR deterministically. A future uncertainty model must be an explicit contract change.

## Interpolation and domain

Acceptance interpolation is linear in `log(ctau)` between neighboring calibration points. There is no extrapolation.

A row is `SUPPORTED` only if both:

- `m_H2_GeV` is within the declared fixed-mass tolerance;
- `ctau_mm_H2` lies within the declared lifetime domain and acceptance-table support.

The initial intended scientific domain is the 150 GeV Trackless response. A broader `Aeff(mH,ctau)` calibration requires a later schema/version.

## Status vocabulary

### `signal_domain_status`

| Value | Meaning |
|---|---|
| `SUPPORTED` | all required observables exist and the point is inside calibration support |
| `OUTSIDE_RECAST_CALIBRATION` | observables exist but mass/lifetime is outside support |
| `MISSING_REQUIRED_OBSERVABLE` | one or more of mH, g, ctau, BR_bb is missing/invalid/conflicting |
| `INVALID_CALIBRATION` | the supplied response artifact failed its structural/scientific contract |

### `signal_status`

| Value | Meaning |
|---|---|
| `COMPUTED_VALIDATED` | numbers computed with a calibration marked `VALIDATED` |
| `COMPUTED_PROVISIONAL` | numbers computed with a calibration marked `PROVISIONAL` |
| `NOT_COMPUTED` | no supported response was applied |

A provisional response can be inspected and plotted but must not be silently described as the final absolute recast calibration.

## Threshold class

The calibration declares a `near_fraction` around `N_over_S95 = 1`:

```text
BELOW: ratio < 1 - near_fraction
NEAR:  1 - near_fraction <= ratio <= 1 + near_fraction
ABOVE: ratio > 1 + near_fraction
```

This is a boundary-analysis convenience. It is not a replacement for a full likelihood or a claim of model exclusion.

## Provenance

Every output records:

- calibration version and status;
- source alias used for each normalized observable;
- row-level notes/domain status;
- run-level calibration path and validity;
- dhb version and Git commit;
- row counts and UTC timestamps.
