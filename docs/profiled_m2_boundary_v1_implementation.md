# Profiled M² boundary v1 — implementation note

This bounded scan consumes `dihiggs.point.v2` rows from the canonical
`DihiggsPointV2Evaluator` through its `M2Engine` adapter. Boundary does not
construct a 2HDM point or recalculate the trilinear.

The outer coordinates are `m_phi=mH_input_GeV` and a derived plotting-only
`M_plot_GeV=sqrt(M2_input_GeV2)`. Linear M-bar nodes are squared and sent as
individual canonical M² inputs, preserving the requested 20 by 20 geometry.
Each cell profiles 16 seeded LHS proposals in `X=lambda6*tan(beta)` and
`Delta_heavy`, with `mA=mHp=mphi+Delta_heavy`; all failures remain raw rows.

New production uses the canonical v3 `mh_125p13_pdg_2026` convention. HB/HS is
not run: point-v2 does not export Boundary's required effective-coupling block,
and recreating it downstream would violate model ownership.
