# LLP signal enrichment contract v1

Schema: `llp_signal_enriched_v1`  
Producer: `python -m dhb.llp_signal`  
Input: model/HBHS rows already joined with one MadGraph production result per physical point  
Output: `llp_signal_enriched.csv` + `llp_signal_manifest.json`

## Responsibility

`dhb.llp_signal` combines already-computed model observables, a **direct per-point MadGraph production cross section**, and an already-calibrated DV+jets response. It does **not** reconstruct a 2HDM point and does **not** execute MadGraph, Pythia or the ATLAS recast.

```text
model/HBHS row
  + direct MadGraph sigma for the same point
  + versioned Trackless response
  -> normalized (mH, g, ctau, BR_bb)
  -> BR_bb^2
  -> Trackless_Aeff
  -> sigma_visible
  -> N_expected / S95
```

The stage preserves every input row.

## Required physical inputs

The normalized LLP tuple is:

```text
m_H2_GeV
g_hH2H2_GeV
ctau_mm_H2
br_bb_H2
```

The same row must also carry the production result:

```text
sigma_production_fb
sigma_production_unc_fb
```

These production fields are upstream physics inputs. They are not reconstructed from `g_hH2H2_GeV` inside Boundary.

`dhb.point_fields` accepts documented serialized aliases for the model observables. It does not compute `g_hH2H2_GeV` from 2HDMC. If both canonical and legacy aliases are present, finite values must agree or the observable is treated as missing/invalid.

For `BR(H2->bb)`, an explicit serialized `br_bb`/`br_bb_H2` is preferred. If it is absent, the bridge may derive exactly once:

```text
br_bb_H2 = width_bb_H2 / total_width_H2
```

using widths from the same row. If both forms are present, they must agree.

## Production policy

For new physical-point scans, the default and required production handoff is:

```text
canonical 2HDM point
  -> parameter/UFO mapping
  -> MadGraph
  -> sigma_production_fb + integration uncertainty
  -> join by stable point_id
  -> dhb.llp_signal
```

Boundary has **no coupling-rescaling fallback**.

A relation such as

```text
sigma(g) = sigma0 * (g/g0)^2
```

may remain useful as a controlled validation diagnostic when only that coupling is varied and the relevant diagrams, widths, coupling orders and all other model inputs are proven fixed. It is **not** the general production prescription for varying physical 2HDM points, where additional couplings, widths, interference or kinematics may also change.

The production repository must preserve the MadGraph process, cards, UFO provenance, PDF/scale configuration, seed, integration result and uncertainty according to the project MadGraph contract. Boundary consumes the resulting cross section; it does not duplicate that provenance machinery.

## Trackless calibration schema

The Trackless response is an **external file** with schema:

```text
dhb.llp_signal_calibration.v2
```

Calibration v2 intentionally contains no production model. This prevents an acceptance artifact from becoming an implicit cross-section model.

Required structure:

```yaml
schema_version: dhb.llp_signal_calibration.v2
calibration_version: <immutable human-readable id>
calibration_status: PROVISIONAL  # or VALIDATED

domain:
  m_H2_GeV:
    value: 150.0
    abs_tolerance: <declared numerical/model tolerance>
  ctau_min_mm: <positive lower support>
  ctau_max_mm: <positive upper support>

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
  # recast campaign, commit, hashes and scientific status
```

Only `PROVISIONAL` and `VALIDATED` are accepted calibration states. A structurally invalid calibration produces failure-marked rows, a failure manifest and a non-zero exit status.

For the current 150 GeV canonical Trackless use, the authoritative absolute response is the frozen **original/published Trackless** R8/R10 line. The later `modified` analysis response is a different selection and must not silently replace the published Trackless calibration.

At the validated benchmark:

```text
m_H2 = 150 GeV
ctau = 4.326221529733112 mm
Trackless_Aeff = 0.01573386
raw Trackless acceptance = 40 / 2000 = 0.020000
weighted Acc x Eff = 31.46772 / 2000
```

The historical carried weighted-Aeff uncertainty convention remains provisional; do not reinterpret it as a detector systematic.

## Signal arithmetic

For a supported point:

```text
sigma_4b
  = sigma_production_fb * BR_bb^2

sigma_visible
  = sigma_4b * Trackless_Aeff

N_expected
  = luminosity * sigma_visible

N_over_S95
  = N_expected / S95
```

`BR_bb^2` is applied exactly once in this stage. The recast response is defined for samples where `H2 -> bb` is forced, so `Trackless_Aeff` must not contain an additional physical BR factor.

The v1 uncertainty propagation treats the supplied MadGraph integration uncertainty and declared Aeff uncertainty as independent absolute uncertainties:

```text
(delta sigma_visible)^2
  = (BR_bb^2 * Aeff * delta sigma_production)^2
  + (BR_bb^2 * sigma_production * delta Aeff)^2
```

No BR uncertainty is introduced by v1 because the current model row supplies BR deterministically. Scale/PDF/model uncertainties are separate from the MadGraph integration uncertainty and should only be added by an explicit later uncertainty contract.

## Interpolation and domain

Acceptance interpolation is linear in `log(ctau)` between neighboring calibration points. There is no extrapolation.

A row is `SUPPORTED` only if:

- the required model observables exist and are valid;
- `sigma_production_fb` and `sigma_production_unc_fb` are finite and non-negative;
- `m_H2_GeV` is within the declared fixed-mass tolerance;
- `ctau_mm_H2` lies within the declared lifetime domain and acceptance-table support.

The current intended scientific domain is the 150 GeV Trackless response. A broader `Aeff(mH,ctau)` calibration requires a later explicit calibration update rather than reusing the 150 GeV curve at arbitrary mass.

## Status vocabulary

### `signal_domain_status`

| Value | Meaning |
|---|---|
| `SUPPORTED` | all required inputs exist and the point is inside recast support |
| `OUTSIDE_RECAST_CALIBRATION` | production/model inputs exist but mass/lifetime is outside response support |
| `MISSING_REQUIRED_OBSERVABLE` | one or more model observables or direct production fields is missing/invalid/conflicting |
| `INVALID_CALIBRATION` | the supplied Trackless response artifact failed its contract |

### `signal_status`

| Value | Meaning |
|---|---|
| `COMPUTED_VALIDATED` | numbers computed with a Trackless calibration marked `VALIDATED` |
| `COMPUTED_PROVISIONAL` | numbers computed with a Trackless calibration marked `PROVISIONAL` |
| `NOT_COMPUTED` | no supported response was applied |

The calibration status describes the Trackless response. MadGraph production provenance remains owned by the upstream production artifact.

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

- Trackless calibration version and status;
- source alias used for each normalized model observable;
- explicit source fields for the direct production cross section and uncertainty;
- row-level notes/domain status;
- run-level calibration path and validity;
- the production policy `MADGRAPH_PER_PHYSICAL_POINT_REQUIRED` in the manifest;
- dhb version and Git commit;
- row counts and UTC timestamps.
