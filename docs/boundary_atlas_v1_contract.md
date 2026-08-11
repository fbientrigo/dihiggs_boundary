# Boundary Atlas v1 contract

Schema: `boundary_atlas_v1`  
Producer: `python -m dhb.atlas_v1`  
Input: `llp_signal_enriched.csv`  
Output: `boundary_atlas_v1.csv` + summary/manifest (+ Parquet best-effort)

## Responsibility

Boundary Atlas v1 is a classifier over already-computed columns. It does not execute 2HDMC, HiggsBounds/HiggsSignals, MadGraph, Pythia or the recast.

It keeps four questions separate:

```text
1. Is the point theory-valid?
2. Does it pass the evaluated HB/HS layer?
3. Is it inside the domain of the LLP response?
4. What signal-threshold class does the supplied response imply?
```

`is_allowed` continues to mean theory + HB/HS acceptance only. Signal-domain support is not folded into that boolean.

## Required handoff

The input must contain:

- `theory_ok`, `hb_allowed`, `hs_delta_chi2`, `exp_ok`, `enrich_status`;
- all normalized LLP inputs from `llp_signal_enriched_v1`;
- all LLP signal/status columns from `llp_signal_enriched_v1`.

Every input row produces one output row.

## Appended fields

```text
atlas_schema_version
region_class
is_theory_ok
is_exp_ok
is_allowed
is_signal_domain_supported
is_signal_calibration_validated
is_signal_at_or_above_S95
atlas_notes
```

## Region classes

Classification precedence is deliberate:

| `region_class` | Meaning |
|---|---|
| `invalid_input` | required theory acceptance encoding is malformed |
| `theory_fail` | model theory predicates fail |
| `hbhs_not_run` | HB/HS enrichment is absent/not completed for the point |
| `hb_excluded` | HiggsBounds fails |
| `hs_tension` | evaluated experimental layer fails with finite HS delta-chi2 context |
| `exp_fail` | experimental composite flag fails for another/unknown reason |
| `allowed_no_signal_calibration` | theory+HB/HS allowed but usable LLP signal response is missing/invalid |
| `allowed_outside_recast_domain` | allowed point has LLP observables but lies outside response support |
| `allowed_signal_below` | allowed, supported point with threshold class `BELOW` |
| `allowed_signal_near_threshold` | allowed, supported point with threshold class `NEAR` |
| `allowed_signal_above` | allowed, supported point with threshold class `ABOVE` |

A `PROVISIONAL` calibration does not change the numerical threshold class, but `is_signal_calibration_validated` is false and `atlas_notes` records that the calibration is not validated.

For a row declaring `signal_domain_status = SUPPORTED`, Atlas v1 also verifies
that the LLP schema version is current, the calibration and signal statuses
agree, and the finite `N_expected`, `S95`, `N_over_S95`, `Trackless_Aeff`, and
`sigma_visible_fb` fields are mutually usable.  An inconsistent serialized
signal state is fail-closed as `allowed_no_signal_calibration`, with
`inconsistent_supported_signal_state` in `atlas_notes`; it is never assigned a
threshold signal class.

## Non-claims

- `allowed_signal_above` means the calibrated yield metric is above the declared `S95` threshold; it is not by itself a full statistical exclusion.
- The historical `tag_displaced_candidate` in `boundary_atlas_v0` remains a finder aid and is not promoted or aliased to any v1 signal class.
- A point outside the 150 GeV response domain remains physically theory/HBHS allowed if those layers pass; it is simply unsupported by the current recast calibration.

## Plotting contract

Because `llp_signal_enriched_v1` carries the normalized physical tuple and Atlas v1 passes all input columns through, the final dataset can directly support:

```text
g_hH2H2_GeV vs ctau_mm_H2 vs br_bb_H2
```

colored/faceted by `N_expected`, `N_over_S95`, theory/HBHS status, signal-domain status or any upstream 2HDM parameter retained in the row.
