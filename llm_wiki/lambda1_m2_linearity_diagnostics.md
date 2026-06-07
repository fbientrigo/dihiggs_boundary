---
tags:
  - 2hdm
  - boundary-atlas
  - lambda1
  - diagnostics
---

# Lambda1 and M2 Linearity Diagnostics

Related:
- [[project_bootstrap]]
- Script: `scripts/plot_lambda1_relations.py`
- Campaign: `campaigns/refined_lhs_v1`
- Outputs: `campaigns/refined_lhs_v1/plots/lambda1_relations/`

## Question

We tested whether `lambda1` is approximately one-to-one with:

- `M2`, the input coordinate `M*M`
- `M2_recomputed`, reconstructed from derived 2HDMC quantities
- `M`, the input coordinate

We also checked whether the relation changes when restricting to `theory_ok` points.

## Main Result

For the `refined_lhs_v1` scan, `lambda1` is not one-to-one with `M2` globally.

Evidence:

- Total rows read: `245400`
- Theory-ok rows: `299`
- Pearson correlation with `lambda1`, all points:
  - `M`: `-0.326901`
  - `M2`: `-0.328585`
  - `M2_recomputed`: `-0.328585`
  - `mH`: `0.143302`
  - `mA`: `0.00113834`
  - `log10(tan_beta)`: `-0.199746`
  - `log10(lambda6_input)`: `-0.00212239`
- Pearson correlation with `lambda1`, theory-ok points:
  - `M`: `0.0341694`
  - `M2`: `0.0364262`
  - `M2_recomputed`: `0.0364262`
  - `mH`: `0.0515752`
  - `mA`: `0.0199773`
  - `log10(tan_beta)`: `0.045453`
  - `log10(lambda6_input)`: `0.00774517`

The binned spread diagnostic is stronger than correlation alone. Within narrow `M2` bins, `lambda1` still spans a large range:

- All points:
  - Overall `lambda1` range: `3.74973e+08`
  - Median within-bin range: `1.15184e+08`
  - 90th percentile within-bin range: `1.98082e+08`
- Theory-ok points:
  - Overall `lambda1` range: `4.20048`
  - Median within-bin range: `1.88502`
  - 90th percentile within-bin range: `3.45196`

Conclusion: in this scan, `lambda1` depends strongly enough on other coordinates that `M2` alone does not determine it.

## Coordinate Interpretation

Weak correlation does not, by itself, prove that one variable can never be used as a degree of freedom in place of another.

The correct distinction is:

- `M` and `M2` are effectively interchangeable coordinates if the scan only uses nonnegative `M`, because `M2 = M*M` is then invertible via `M = sqrt(M2)`.
- `lambda1` and `M2` are not globally interchangeable in this campaign, because many different `lambda1` values occur at similar `M2`.
- A conditional substitution may still be possible on a restricted slice or manifold, for example after fixing `mH`, `mA`, `tan_beta`, and `lambda6_input`, if the local mapping between `M2` and `lambda1` is monotonic with a nonzero Jacobian.

Therefore the present diagnostic rules out a simple global replacement `M2 <-> lambda1` across the full scan. It does not rule out using `lambda1` as an alternate coordinate in a more constrained parametrization, but that requires a separate local or conditional invertibility test.

## OLS Diagnostic

Exploratory standardized OLS results:

- All points:
  - `lambda1 ~ M2`: `R2 = 0.107968`
  - `lambda1 ~ M2 + mH + mA + log10(tan_beta) + log10(lambda6_input)`: `R2 = 0.168478`
- Theory-ok points:
  - `lambda1 ~ M2`: `R2 = 0.00132687`
  - `lambda1 ~ M2 + mH + mA + log10(tan_beta) + log10(lambda6_input)`: `R2 = 0.0919213`

These fits are exploratory diagnostics only. They are not a physics proof.

## Next Check

To test whether `lambda1` can replace `M2` as a coordinate in a restricted setup, run conditional diagnostics:

1. Bin or slice by `mH`, `mA`, `tan_beta`, and `lambda6_input`.
2. Within each slice, plot `M2` vs `lambda1`.
3. Check monotonicity and within-slice spread.
4. Estimate local sensitivity `d(lambda1)/d(M2)` or the relevant Jacobian.
5. Repeat separately for all generated points and `theory_ok` points.

