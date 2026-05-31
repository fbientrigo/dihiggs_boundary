# Model Contract — `type1_lambda6_alignment_v0`

## 1. Purpose

This document defines the physics contract for the first reproducible atlas of valid and invalid regions in the `dihiggsbounds` project.

The immediate goal is not MCMC and not a full experimental recast. The immediate goal is to build a clean, auditable, point-by-point atlas for a constrained 2HDM setup, separating:

1. theory-only validity,
2. experimental validity,
3. combined signal usefulness.

This contract is the root of the project. Code, samplers, runners, schemas, and plots must conform to it unless this file is explicitly updated.

---

## 2. Scope

This project studies a CP-conserving Two-Higgs-Doublet Model using a Type-I Yukawa assignment, exact alignment, nonzero (\lambda_6), and (\lambda_7=0).

The model should be described as:

> CP-conserving 2HDM with Type-I Yukawa assignment and nonzero (\lambda_6).

It should not be described without qualification as the standard softly broken (Z_2) Type-I 2HDM, because nonzero (\lambda_6) generally goes beyond the usual softly broken (Z_2) potential convention used in many Type-I benchmark papers.

---

## 3. Fixed physical assumptions

The baseline contract is:

```
model_family: CP-conserving 2HDM
yukawa_type: Type I
observed_higgs_mass:
  mh: 125.09 GeV
  role: SM-like Higgs
alignment:
  sin(beta-alpha): 1.0
  cos(beta-alpha): 0.0
charged_scalar_relation:
  mHp: mA
  reason: first-pass simplification; helps control the oblique T parameter
lambda7:
  value: 0.0
  reason: simplification
lambda6:
  value: scanned
  constraint: nonzero in the intended physics region
external_calculators:
  theory: 2HDMC
  experimental_later: HiggsTools
  production_later: SusHi or equivalent
```

---

## 4. Input coordinates

The canonical input coordinates for Atlas v0 are:

```
theta = {
  mH,
  mA,
  tan_beta,
  lambda6,
  M
}
```

where:

```
mHp = mA
mh = 125.09 GeV
sin(beta-alpha) = 1.0
lambda7 = 0.0
```

The parameter (M) is a soft-scale coordinate used to define:

[
M^2 = M \times M
]

and

[
m_{12}^2 = M^2 , s_\beta c_\beta.
]

For Atlas v0, (M^2 \geq 0) unless a later contract explicitly enables signed (M^2).

---

## 5. Derived coordinates

For each point, the evaluator must compute and store:

```
beta
sin_beta
cos_beta
M2
m12_sq
lambda1
lambda2
lambda3
lambda4
lambda5
lambda6_gen
lambda7_gen
tan_beta_gen
```

The values `lambda1..lambda7` must be the values returned by the calculator after constructing the model, not guessed from input labels.

The evaluator must preserve both input and recomputed values where relevant:

```
M_input
M2_input
m12_sq_used
M2_recomputed = m12_sq_used / (sin_beta * cos_beta)
relative_M2_reconstruction_error
```

This is required because large `tan_beta` can make the mapping between (M^2), (m_{12}^2), and the quartics numerically delicate.

---

## 6. 2HDMC model construction

The canonical 2HDMC construction for Atlas v0 is:

```
model.set_SM(sm)

model.set_param_phys(
  mh,
  mH,
  mA,
  mHp,
  sin_beta_minus_alpha,
  lambda6,
  lambda7,
  m12_sq,
  tan_beta
)

model.set_yukawas_type(1)
```

where:

```
mh = 125.09
mHp = mA
sin_beta_minus_alpha = 1.0
lambda7 = 0.0
m12_sq = M2 * sin_beta * cos_beta
```

No scan should use `lambda1` as the primary input coordinate in this contract.

---

## 7. Theory constraints

The theory layer must evaluate, at minimum:

```
set_param_phys_ok
positivity_ok
unitarity_ok
perturbativity_ok
stability_ok
```

The canonical theory flag is:

```
theory_ok =
  set_param_phys_ok
  && positivity_ok
  && unitarity_ok
  && perturbativity_ok
  && stability_ok
```

The evaluator must store each individual flag. It is not enough to store only `theory_ok`.

If additional 2HDMC checks are used, they must be stored separately, for example:

```
check_masses_ok
oblique_available
S
T
U
V
W
X
delta_amu
```

Important: `check_masses` must not be treated as a replacement for HiggsBounds or HiggsTools unless explicitly verified and documented.

---

## 8. Decays and lifetime

For the scalar identified as `H2` in 2HDMC indexing, the evaluator must store at least:

```
width_total_H2
width_bb_H2
width_tautau_H2
width_WW_H2
width_ZZ_H2
width_gammagamma_H2
width_Zgamma_H2
width_gg_H2
width_hh_H2
br_gammagamma_H2
ctau_mm_H2
```

The lifetime conversion must be documented in code and schema.

Recommended convention:

[
c\tau[\mathrm{mm}] = \frac{\hbar c}{\Gamma}
]

with:

```
hbar_c_GeV_mm = 1.973269804e-13 GeV mm
```

Thus:

```
ctau_mm = hbar_c_GeV_mm / total_width_GeV
```

when `total_width_GeV > 0`.

If `total_width_GeV <= 0`, `ctau_mm` must be null or NaN and a status flag must explain why.

---

## 9. Experimental constraints

Experimental constraints are not part of the minimum theory evaluator.

They enter through a later enrichment stage using HiggsTools:

```
theory_atlas
  -> filter or batch theory_ok points
  -> build HiggsPredictions inputs
  -> run HiggsBounds
  -> run HiggsSignals
  -> write experimental_atlas
```

The experimental layer should eventually store:

```
higgstools_version
higgstools_dataset_hash
hb_allowed
hb_max_obsratio
hb_max_expratio
hb_selected_analysis
hb_selected_process
hb_selected_collider
hb_selected_citekey
hs_chi2
hs_nobs
hs_delta_chi2_vs_sm
```

HiggsTools is not required for the first theory-only atlas.

---

## 10. Production and signal usefulness

The final signal layer must not optimize only `BR(H2 -> gamma gamma)`.

A physically useful displaced diphoton candidate should eventually require:

```
theory_ok
experiment_ok
br_gammagamma_H2 large enough
ctau_mm in a detector-relevant range
production_cross_section non-negligible
sigma_times_br_gammagamma non-negligible
```

The final score is not defined in Atlas v0.

A later version may define:

```
signal_score =
  allowed_mask
  * f_lifetime(ctau_mm)
  * br_gammagamma_H2
  * sigma_production
```

where `allowed_mask` includes theory and experimental constraints.

---

## 11. Rejection stages

Every evaluated point must receive a status.

Allowed rejection stages for Atlas v0:

```
none
numerical_input
set_param_phys
theory
decay
oblique
experimental
production
internal_error
```

Allowed high-level statuses:

```
proposed
evaluated
theory_pass
theory_fail
experiment_pass
experiment_fail
combined_pass
combined_fail
error
```

A point must not disappear silently. Failed points are scientifically useful because they define the forbidden regions and failure mechanisms.

---

## 12. Initial exploration box

The first focused theory atlas should use a box similar to:

```
mH:
  min: 130 GeV
  max: 350 GeV
  scale: linear

mA:
  min: 200 GeV
  max: 700 GeV
  scale: linear
  relation: mHp = mA

tan_beta:
  min: 10
  max: 1.0e6
  scale: log10

abs_lambda6:
  min: 1.0e-16
  max: 12.0
  scale: log10
  sign: initially positive unless explicitly configured

M:
  min: 0 GeV
  max: 1000 GeV
  scale: linear
```

The large `lambda6` upper range is exploratory and expected to produce many theory failures. Sub-ranges should be used when needed:

```
abs_lambda6 in [1e-16, 1e-8]
abs_lambda6 in [1e-8, 1e-4]
abs_lambda6 in [1e-4, 1e-1]
abs_lambda6 in [1e-1, 12]
```

---

## 13. Sampling policy

Atlas v0 should use Latin Hypercube sampling.

Adaptive sampling and MCMC are explicitly out of scope for the first theory atlas.

Allowed initial samplers:

```
latin_hypercube
fixed_grid_for_smoke
line_scan_M_for_diagnostics
```

Future samplers:

```
sobol
boundary_refinement
MCMC
Bayesian optimization
```

---

## 14. Required smoke tests

Before large runs, the project must support:

```
1. single-point evaluation
2. tiny fixed grid
3. 1000-point Latin Hypercube
4. single-worker vs multi-worker reproducibility
5. failed-point preservation
6. CSV/Parquet schema validation
7. precision audit for M2 -> m12_sq -> M2 reconstruction
```

Minimum correctness criterion:

```
Same input point_id must produce the same physics flags and numerically equivalent outputs under workers=1 and workers=N.
```

---

## 15. Versioning and provenance

Every run must record:

```
git_commit
dirty_worktree
compiler
compiler_version
build_type
2HDMC_path
2HDMC_version_or_commit_if_available
HiggsTools_path_if_used
HiggsTools_version_or_commit_if_available
model_contract_name
atlas_schema_version
config_hash
input_hash
random_seed
sampler
n_points
n_shards
worker_count
```

Third-party source directories must not be modified by agents.

---

## 16. Out-of-scope for Atlas v0

Atlas v0 does not include:

```
MCMC
adaptive boundary refinement
full likelihood / chi-square fitting
production cross sections
SusHi integration
MadGraph simulation
detector simulation
final benchmark selection
publication-level statistical interpretation
```

Atlas v0 is successful if it produces trustworthy theory-validity maps and preserves enough metadata to enrich surviving points later.
