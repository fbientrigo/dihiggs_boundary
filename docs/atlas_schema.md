# Atlas Schema — `dihiggsbounds`

## 1. Purpose

This document defines the canonical data schema for the first `dihiggsbounds` theory and experimental atlases.

The atlas must preserve enough information to:

1. reproduce every point,
2. explain why every point passed or failed,
3. aggregate high-dimensional scans into 2D maps,
4. enrich theory-valid points with HiggsTools later,
5. support future MCMC or optimization without rerunning the full theory scan.

---

## 2. Schema versions

Initial versions:

```
model_contract_version: type1_lambda6_alignment_v0
atlas_schema_version: atlas_schema_v0
theory_schema_version: theory_schema_v0
experimental_schema_version: experimental_schema_v0
```

Each run must store these values in its manifest and each output table.

---

## 3. Table layout

Recommended final storage:

```
atlas_theory.parquet
atlas_experiment.parquet
atlas_combined.parquet
run_manifest.json
shard_manifests/*.json
atlas.duckdb
```

Recommended transient storage:

```
output_shards/theory_000.csv
output_shards/theory_001.csv
output_shards/experiment_000.csv
```

The C++ evaluator may write CSV shards. Python ingest converts them to Parquet and DuckDB.

---

## 4. Primary table: `atlas_theory`

Each row corresponds to one proposed model point.

A failed point must still produce one row.

Primary key:

```
point_id
```

Recommended `point_id` format:

```
run_id + shard_id + local_index
```

Example:

```
theory_v0_000001_shard000042_row000017
```

---

## 5. Required column groups

Column groups:

```
provenance
input_parameters
derived_parameters
numerical_diagnostics
theory_flags
oblique_observables
decay_observables
status
candidate_tags
```

---

## 6. Provenance columns

Required:

```
run_id: string
point_id: string
shard_id: string
local_index: int64
model_contract_version: string
atlas_schema_version: string
sampler_name: string
sampler_seed: int64
generated_at_utc: string
evaluated_at_utc: string
evaluator_name: string
evaluator_version: string
twohdmc_path: string
twohdmc_version: string nullable
git_commit: string nullable
git_dirty: bool nullable
config_hash: string
input_hash: string nullable
```

Notes:

```
- `twohdmc_version` may be null if not discoverable.
- `git_dirty` must be true if the working tree was modified at run time.
- `config_hash` must change when the scan config changes.
```

---

## 7. Input parameter columns

Required:

```
mh_GeV: float64
mH_GeV: float64
mA_GeV: float64
mHp_GeV: float64
sin_beta_minus_alpha: float64
tan_beta: float64
lambda6_input: float64
lambda7_input: float64
M_GeV: float64
M2_GeV2_input: float64
```

Fixed by model contract in Atlas v0:

```
mh_GeV = 125.09
mHp_GeV = mA_GeV
sin_beta_minus_alpha = 1.0
lambda7_input = 0.0
M2_GeV2_input = M_GeV * M_GeV
```

Allowed derived convenience columns:

```
log10_tan_beta: float64
abs_lambda6_input: float64
log10_abs_lambda6_input: float64 nullable
lambda6_sign: int8
mHp_minus_mA_GeV: float64
```

If `lambda6_input == 0`, `log10_abs_lambda6_input` must be null or NaN.

---

## 8. Derived parameter columns

Required after attempting model construction:

```
beta_rad: float64 nullable
sin_beta: float64 nullable
cos_beta: float64 nullable
m12_sq_GeV2_used: float64 nullable
M2_GeV2_recomputed: float64 nullable
relative_M2_reconstruction_error: float64 nullable
```

2HDMC returned general-basis parameters:

```
lambda1_gen: float64 nullable
lambda2_gen: float64 nullable
lambda3_gen: float64 nullable
lambda4_gen: float64 nullable
lambda5_gen: float64 nullable
lambda6_gen: float64 nullable
lambda7_gen: float64 nullable
m12_sq_GeV2_gen: float64 nullable
tan_beta_gen: float64 nullable
```

Recommended diagnostics:

```
max_abs_lambda_gen: float64 nullable
max_abs_lambda12345_gen: float64 nullable
lambda6_input_minus_gen: float64 nullable
lambda7_input_minus_gen: float64 nullable
m12_sq_used_minus_gen: float64 nullable
tan_beta_input_minus_gen: float64 nullable
```

Nullability:

```
These columns may be null when `set_param_phys_ok == false`.
```

---

## 9. Numerical diagnostics

Required:

```
finite_input_ok: bool
finite_derived_ok: bool
finite_output_ok: bool
no_nan_output_ok: bool
no_inf_output_ok: bool
precision_warning: bool
numerical_warning_code: string nullable
numerical_warning_message: string nullable
```

Recommended:

```
large_tan_beta_warning: bool
small_cos_beta_warning: bool
small_m12_sq_warning: bool
M2_reconstruction_ok: bool nullable
```

Suggested thresholds for warnings:

```
large_tan_beta_warning:
  true if tan_beta >= 1.0e5

small_cos_beta_warning:
  true if abs(cos_beta) < 1.0e-5

M2_reconstruction_ok:
  true if relative_M2_reconstruction_error < 1.0e-10
```

Thresholds are advisory and may be changed after empirical testing.

---

## 10. Theory flag columns

Required:

```
set_param_phys_ok: bool
positivity_ok: bool nullable
unitarity_ok: bool nullable
perturbativity_ok: bool nullable
stability_ok: bool nullable
theory_ok: bool
```

Definition:

```
theory_ok =
  set_param_phys_ok
  && positivity_ok
  && unitarity_ok
  && perturbativity_ok
  && stability_ok
```

If `set_param_phys_ok == false`, downstream flags may be null.

Optional 2HDMC checks:

```
check_masses_ok: bool nullable
delta_amu_available: bool
oblique_available: bool
```

Important:

```
`check_masses_ok` must not be interpreted as a modern replacement for HiggsBounds or HiggsTools.
```

---

## 11. Oblique observable columns

Optional but recommended if available from 2HDMC:

```
S: float64 nullable
T: float64 nullable
U: float64 nullable
V: float64 nullable
W: float64 nullable
X: float64 nullable
stu_status: string nullable
```

Allowed `stu_status` values:

```
not_computed
computed
failed
unavailable
```

Atlas v0 may store oblique parameters without applying an acceptance threshold.

---

## 12. Decay observable columns

For the scalar treated as `H2`:

```
width_total_H2_GeV: float64 nullable
width_bb_H2_GeV: float64 nullable
width_tautau_H2_GeV: float64 nullable
width_WW_H2_GeV: float64 nullable
width_ZZ_H2_GeV: float64 nullable
width_gammagamma_H2_GeV: float64 nullable
width_Zgamma_H2_GeV: float64 nullable
width_gg_H2_GeV: float64 nullable
width_hh_H2_GeV: float64 nullable
br_gammagamma_H2: float64 nullable
ctau_mm_H2: float64 nullable
dominant_decay_H2: string nullable
```

Lifetime convention:

```
ctau_mm_H2 = hbar_c_GeV_mm / width_total_H2_GeV
```

where:

```
hbar_c_GeV_mm = 1.973269804e-13
```

If `width_total_H2_GeV <= 0`, then:

```
ctau_mm_H2 = null
decay_status = invalid_total_width
```

Additional recommended:

```
decay_status: string
br_sum_known_H2: float64 nullable
```

Allowed `decay_status` values:

```
not_computed
computed
invalid_total_width
failed
unavailable
```

---

## 13. Status columns

Required:

```
status: string
accepted_theory: bool
rejection_stage: string
rejection_reason: string nullable
error_code: string nullable
error_message: string nullable
```

Allowed `status` values:

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

Allowed `rejection_stage` values:

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

Allowed `rejection_reason` examples:

```
null
nonfinite_input
set_param_phys_failed
positivity_failed
unitarity_failed
perturbativity_failed
stability_failed
invalid_total_width
nonfinite_output
internal_exception
```

The first failing stage should be stored as `rejection_stage`.

For detailed analysis, additional per-constraint flags are always preferred over compressing everything into `rejection_reason`.

---

## 14. Candidate tag columns

These are not final paper-level selections. They are practical tags for finding interesting regions.

Recommended:

```
br_gammagamma_high_tag: bool nullable
displaced_ctau_tag: bool nullable
prompt_ctau_tag: bool nullable
long_lived_escape_tag: bool nullable
candidate_theory_only: bool
```

Example provisional definitions:

```
br_gammagamma_high_tag:
  br_gammagamma_H2 >= 0.5

displaced_ctau_tag:
  1.0 <= ctau_mm_H2 <= 1000.0

prompt_ctau_tag:
  ctau_mm_H2 < 1.0

long_lived_escape_tag:
  ctau_mm_H2 > 1000.0
```

These thresholds are exploratory and not final analysis criteria.

---

## 15. Experimental table: `atlas_experiment`

This table is created by enriching theory-valid points with HiggsTools.

Primary key:

```
point_id
```

Required provenance:

```
run_id: string
point_id: string
experiment_enrichment_id: string
higgstools_path: string
higgstools_version: string nullable
higgstools_dataset_hash: string nullable
higgstools_config_hash: string
enriched_at_utc: string
```

HiggsBounds columns:

```
hb_computed: bool
hb_allowed: bool nullable
hb_max_obsratio: float64 nullable
hb_max_expratio: float64 nullable
hb_selected_particle: string nullable
hb_selected_analysis: string nullable
hb_selected_process: string nullable
hb_selected_collider: string nullable
hb_selected_luminosity: float64 nullable
hb_selected_citekey: string nullable
hb_status: string
```

Allowed `hb_status` values:

```
not_computed
computed
failed
unavailable
```

HiggsSignals columns:

```
hs_computed: bool
hs_chi2: float64 nullable
hs_nobs: int64 nullable
hs_ndof: int64 nullable
hs_pvalue: float64 nullable
hs_delta_chi2_vs_sm: float64 nullable
hs_largest_contribution: string nullable
hs_status: string
```

Allowed `hs_status` values:

```
not_computed
computed
failed
unavailable
```

Experimental acceptance columns:

```
experiment_ok: bool nullable
experiment_rejection_reason: string nullable
```

Initial definition may be:

```
experiment_ok =
  hb_allowed == true
  && hs_chi2 is finite
```

A paper-level definition requires a later statistics contract.

---

## 16. Combined table: `atlas_combined`

The combined table joins:

```
atlas_theory
atlas_experiment
future production table
```

Minimum columns:

```
point_id
theory_ok
experiment_ok
combined_ok
br_gammagamma_H2
ctau_mm_H2
sigma_production_pb nullable
sigma_times_br_gammagamma_pb nullable
combined_score nullable
```

Initial definition:

```
combined_ok =
  theory_ok && experiment_ok
```

Signal optimization is out of scope for Atlas v0.

---

## 17. Aggregation schema for 2D maps

Every 2D map should be built from aggregate tables, not directly from raw rows.

Recommended aggregate columns:

```
map_id: string
x_variable: string
y_variable: string
x_bin: int64
y_bin: int64
x_min: float64
x_max: float64
y_min: float64
y_max: float64
n_total: int64
n_theory_ok: int64
n_experiment_ok: int64 nullable
theory_pass_fraction: float64
experiment_pass_fraction: float64 nullable
best_br_gammagamma_H2: float64 nullable
best_ctau_mm_H2: float64 nullable
dominant_rejection_reason: string nullable
coverage_class: string
```

Allowed `coverage_class` values:

```
insufficient_coverage
no_survivor_found
thin_survival_region
survivor_region
```

Suggested classification:

```
if n_total < min_coverage:
  insufficient_coverage

else if n_theory_ok == 0:
  no_survivor_found

else if n_theory_ok / n_total < 0.01:
  thin_survival_region

else:
  survivor_region
```

The map title or metadata must state which variables were hidden/profiled.

---

## 18. Required map metadata

Each plot or aggregate must store:

```
x_variable
y_variable
hidden_variables
aggregation_method
constraints_applied
min_coverage
run_ids
schema_version
created_at_utc
```

Examples of aggregation methods:

```
pass_fraction
exists_any_survivor
max_br_gammagamma
max_ctau
dominant_rejection_reason
min_hs_chi2
max_hb_obsratio
```

No plot should label a region as excluded unless coverage and applied constraints are explicit.

---

## 19. CSV output precision

C++ CSV output must use scientific notation with 17 significant digits for all floating values.

Required:

```
std::scientific
std::setprecision(17)
```

This applies to:

```
input parameters
derived parameters
lambdas
widths
BRs
oblique parameters
ctau
reconstruction diagnostics
```

---

## 20. Null and NaN policy

Preferred final Parquet/DuckDB representation:

```
missing numeric value -> null
failed bool downstream -> null if not evaluated
explicit false -> evaluated and failed
```

CSV transient representation may use:

```
empty field for null numeric
0/1 for booleans
string status fields for failure reason
```

Do not encode failed downstream checks as false if they were not evaluated.

Example:

```
set_param_phys_ok = false
positivity_ok = null
unitarity_ok = null
perturbativity_ok = null
stability_ok = null
```

This is different from:

```
set_param_phys_ok = true
positivity_ok = false
```

---

## 21. Minimal Theory Atlas v0 acceptance

A theory atlas run is accepted if:

```
1. every input point has exactly one output row,
2. required columns exist,
3. floating values are written with 17-digit precision,
4. failed points are preserved,
5. `stability_ok` is present,
6. `M`, `M2`, and `m12_sq` are present,
7. `relative_M2_reconstruction_error` is present,
8. `theory_ok` is computed from individual flags,
9. output can be ingested into Parquet,
10. at least one 2D aggregate map can be produced.
```

---

## 22. Minimal Experimental Atlas v0 acceptance

An experimental atlas run is accepted if:

```
1. only theory-valid or explicitly selected theory points are enriched,
2. every enriched input point has exactly one experimental row,
3. HiggsTools version/path/dataset metadata is recorded,
4. HiggsBounds allowed/obsRatio information is stored,
5. HiggsSignals chi2 information is stored if available,
6. failures are preserved with status and message,
7. combined maps can distinguish theory failure from experimental failure.
```

---

## 23. Out-of-scope columns for Atlas v0

Do not block Atlas v0 on:

```
production cross sections
sigma times branching ratio
detector efficiency
full likelihood
final chi-square model
MCMC weights
posterior probabilities
benchmark ranking
```

These belong to later schemas.
