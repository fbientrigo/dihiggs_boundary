# STU Boundary Contract

This document defines how the Electroweak Precision Observables (EWPO), specifically the oblique parameters $S, T, U$, are integrated into the `evaluate_point` workflow of the `dihiggs_boundary` project.

## STU Semantics
The existing boundary checks test `positivity`, `unitarity`, `perturbativity`, and `stability`. The theoretical constraints and the electroweak precision bounds have been explicitly separated.

- `theory_ok`: Indicates the point satisfies the fundamental theoretical constraints.
  `theory_ok = positivity_ok && unitarity_ok && perturbativity_ok`
  
- `stu_ok`: The $S, T, U$ electroweak precision gate. This `stu_ok` check is a provisional rectangular cut. It is not covariance-aware and is not a replacement for a global electroweak precision fit. Future implementations should use configurable central values, uncertainties, and covariance/chi2 metrics. In our current implementation, a point passes if:
  `|stu_S| < 0.3` AND `|stu_T| < 0.3` AND `|stu_U| < 0.3`

- `physics_ok`: The combined logical gate representing that a parameter point is physically valid. It is defined exactly as:
  `physics_ok = set_param_phys_ok && theory_ok && stability_ok && stu_ok`

Boundary constraints are empirical existence evidence, not proof that the entire bin passes. Bins are flagged as:
- `exists_theory_ok`: at least one observed point in the bin has `theory_ok`.
- `exists_physics_ok`: at least one observed point in the bin has `physics_ok`.

## Output Columns
The STU parameters and the flags are written to the output CSV in the following order:
- `theory_ok`
- `stu_ok`
- `physics_ok`
- ...
- `stu_S`
- `stu_T`
- `stu_U`

The validation script `scripts/check_evaluate_point_output.sh` checks for the presence of these exact columns and asserts that `stu_ok` and `physics_ok` are strictly `0` or `1`.
