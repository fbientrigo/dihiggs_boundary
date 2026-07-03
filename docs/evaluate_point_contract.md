# `evaluate_point` contract

## Purpose

`evaluate_point` evaluates individual CP-conserving 2HDM points using 2HDMC.

The executable is the first theory-level evaluator for the `dihiggs_boundary`
project. It must remain independent from HiggsTools: it never links or calls
HiggsTools, but since schema `evaluate_point_v1` it exports the HBHS input
block (effective couplings and non-SM branching ratios) that the separate
python enrichment stage feeds to HiggsBounds/HiggsSignals
(see `docs/hbhs_contract.md`). Experimental constraints themselves are applied
only in that later stage.

## Physics model

Current model contract:

- CP-conserving 2HDM.
- SM-like light Higgs with `mh = 125.09 GeV`.
- Exact alignment: `sin(beta-alpha) = 1.0`.
- `mHp = mA`.
- `lambda7 = 0`.
- `lambda6` may be nonzero.
- Type-I Yukawa assignment via `set_yukawas_type(1)`.

Important wording:

This is not the standard softly-broken Z2 Type-I 2HDM, because nonzero
`lambda6` hard-breaks the scalar-sector Z2 symmetry. The intended wording is:

`CP-conserving 2HDM with Type-I Yukawa assignment and hard-Z2-breaking scalar potential through nonzero lambda6.`

The Type-I label refers to the Yukawa assignment, not to a fully Z2-symmetric scalar potential.

## Canonical input coordinates

Each point is defined by:

- `point_id`
- `mH`
- `mA`
- `tan_beta`
- `lambda6`
- `M`

Fixed parameters:

- `mh = 125.09`
- `sin_ba = 1.0`
- `lambda7 = 0.0`
- `mHp = mA`
- `yukawa_assignment = type-I`

Derived parameters:

- `beta = atan(tan_beta)`
- `sin_beta = sin(beta)`
- `cos_beta = cos(beta)`
- `M2 = M * M`
- `m12_sq = M2 * sin_beta * cos_beta`

2HDMC call:

`set_param_phys(mh, mH, mA, mHp, sin_ba, lambda6, lambda7, m12_sq, tan_beta)`

## Object lifecycle

For each evaluated point:

- create one fresh `SM` object;
- create one fresh `THDM` object;
- create one fresh `Constraints` object after successful model construction;
- create one fresh `DecayTable` object after successful model construction.

Do not share mutable 2HDMC objects across points.

## Output policy

Every input point must produce exactly one output row, including points that fail.

This is mandatory because the atlas must learn boundaries, not only valid regions.

## Boolean definitions

- `set_param_phys_ok`: return value of `set_param_phys`.
- `positivity_ok`: result of `check_positivity`.
- `unitarity_ok`: result of `check_unitarity`.
- `perturbativity_ok`: result of `check_perturbativity`.
- `stability_ok`: result of `check_stability`.

Historical compatibility flag:

`triple_ok = positivity_ok && unitarity_ok && perturbativity_ok`

Theory-atlas flag:

`theory_ok = set_param_phys_ok && positivity_ok && unitarity_ok && perturbativity_ok && stability_ok`

## Rejection stages

Allowed `rejection_stage` values:

- `none`
- `input_parse`
- `derived_parameter`
- `set_param_phys`
- `positivity`
- `unitarity`
- `perturbativity`
- `stability`
- `width`

For a fully accepted theory point:

- `rejection_stage = none`
- `rejection_reason = ok`

For failed points, fill all unavailable numerical outputs with `nan`.

## Width and lifetime convention

Widths are in GeV.

For H2:

- `total_width_H2 = DecayTable::get_gammatot_h(2)`
- `br_gammagamma_H2 = width_gammagamma_H2 / total_width_H2` if `total_width_H2 > 0`

Lifetime proxy:

`ctau_mm_H2 = hbar_c_GeV_mm / total_width_H2`

with:

`hbar_c_GeV_mm = 1.973269804e-13`

If `total_width_H2 <= 0`, set `ctau_mm_H2 = nan` and reject at `width`.

## Required output columns

Minimum required CSV columns:

- `point_id`
- `mh`
- `mH`
- `mA`
- `mHp`
- `tan_beta`
- `beta`
- `sin_ba`
- `lambda6_input`
- `lambda7_input`
- `M`
- `M2`
- `m12_sq_input`
- `M2_recomputed`
- `relative_M2_reconstruction_error`
- `set_param_phys_ok`
- `positivity_ok`
- `unitarity_ok`
- `perturbativity_ok`
- `stability_ok`
- `triple_ok`
- `theory_ok`
- `lambda1`
- `lambda2`
- `lambda3`
- `lambda4`
- `lambda5`
- `lambda6_derived`
- `lambda7_derived`
- `m12_sq_derived`
- `tan_beta_derived`
- `width_bb_H2`
- `width_tautau_H2`
- `width_WW_H2`
- `width_ZZ_H2`
- `width_gammagamma_H2`
- `width_Zgamma_H2`
- `width_gg_H2`
- `width_hh_H2`
- `total_width_H2`
- `br_gammagamma_H2`
- `ctau_mm_H2`
- `yukawa_assignment`
- `scalar_z2_status`
- `soft_z2_only`
- `rejection_stage`
- `rejection_reason`

## HBHS input block columns (schema `evaluate_point_v1`)

Appended after `rejection_reason`, in the order emitted by
`write_hbhs_header()` in `src/evaluate_point.cpp`. All values are NaN unless
`theory_ok = 1`; `hbhs_block_ok` is `1` when the block is valid. Particle
labels: `h1 = h`, `h2 = H`, `h3 = A`, `hc = H+`.

- `hbhs_block_ok`
- Per neutral `hk` in `h1, h2, h3`:
  - `eff_<hk>_<ff>_s`, `eff_<hk>_<ff>_p` for `ff` in
    `ss, cc, bb, tt, mumu, tautau`
  - `eff_<hk>_WW`, `eff_<hk>_ZZ`, `eff_<hk>_Zga`, `eff_<hk>_gaga`,
    `eff_<hk>_gg`
  - `eff_<hk>_h1Z`, `eff_<hk>_h2Z`, `eff_<hk>_h3Z`
- `total_width_h1`, `total_width_h3`, `total_width_hc`
- Per neutral `hk`:
  - `br_<hk>_<pair>` for `pair` in `h1h1, h2h2, h3h3, h1h2, h1h3, h2h3`
  - `br_<hk>_h1Z`, `br_<hk>_h2Z`, `br_<hk>_h3Z`
  - `br_<hk>_hcW`
- `br_t_hcb`, `br_hc_cs`, `br_hc_cb`, `br_hc_tb`, `br_hc_taunu`,
  `br_hc_h1W`, `br_hc_h2W`, `br_hc_h3W`, `hc_kappa_t`, `hc_kappa_b`

Conventions are ported from `lib/2HDMC-1.8.0/src/HBHS.cpp`; the definitive
description lives in `docs/hbhs_contract.md`. The python mirror of this
column list is `python/dhb/schema.py` (`HBHS_BLOCK_COLUMNS`) and is enforced
against a committed fixture by `tests/test_schema.py`.

## Precision

All floating-point outputs must use scientific notation with 17 significant digits.

## Initial smoke requirement

The first smoke must evaluate exactly three points and produce exactly three rows.

At least one point may fail theory constraints. That is acceptable and expected.
