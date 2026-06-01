# `evaluate_point` contract

## Purpose

`evaluate_point` evaluates individual CP-conserving 2HDM points using 2HDMC.

The executable is the first theory-level evaluator for the `dihiggs_boundary`
project. It must remain independent from HiggsTools. Experimental constraints are
added only after the theory atlas is reproducible.

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

## Precision

All floating-point outputs must use scientific notation with 17 significant digits.

## Initial smoke requirement

The first smoke must evaluate exactly three points and produce exactly three rows.

At least one point may fail theory constraints. That is acceptable and expected.
