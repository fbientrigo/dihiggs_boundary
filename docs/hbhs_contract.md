# HB/HS enrichment stage contract (`dhb.enrich`)

## Purpose

The enrichment stage applies the experimental constraints from HiggsBounds
(HB) and HiggsSignals (HS) to the theory atlas, using HiggsTools v1.2 with
`dataset/hbdataset-v1.7` and `dataset/hsdataset-v1.1`.

It is a separate stage from `evaluate_point` by design:

- `evaluate_point` (C++, 2HDMC only) exports everything HB/HS need as extra
  CSV columns (the "HBHS input block") but never links HiggsTools.
- `dhb.enrich` (python, HiggsTools only) consumes those columns and never
  needs 2HDMC. Re-running with updated datasets or thresholds does not
  require re-running the theory scan.

Note: 2HDMC 1.8's own `HBHS.cpp` interface targets the legacy Fortran
HiggsBounds-5/HiggsSignals-2, not HiggsTools. Its effective-coupling and
branching-ratio recipe is authoritative, so the exporter in
`src/evaluate_point.cpp` (`compute_hbhs_block`) ports that recipe verbatim
and the python adapter maps it onto the HiggsTools API.

## Pipeline position

```
points.csv
  -> evaluate_point (theory flags + HBHS input block)   [C++ / 2HDMC]
  -> dhb.enrich     (hb_*, hs_*, exp_ok columns)        [python / HiggsTools]
  -> inspect/plot with --flag-column exp_ok
```

## Particle naming

| id  | state | CP    | notes                        |
|-----|-------|-------|------------------------------|
| h1  | h     | even  | SM-like, `mh = 125.09`       |
| h2  | H     | even  | heavy CP-even                |
| h3  | A     | odd   | CP-odd                       |
| hc  | H+    | —     | charged, `mHp = mA`          |

## HBHS input block (written by evaluate_point, schema `evaluate_point_v1`)

Computed only when `theory_ok = 1` (NaN otherwise); `hbhs_block_ok` records
whether the block is valid. Conventions ported from
`lib/2HDMC-1.8.0/src/HBHS.cpp`:

- `eff_<hk>_<ff>_s` / `eff_<hk>_<ff>_p` for `ff` in
  `ss, cc, bb, tt, mumu, tautau`: SM-normalized CP-even (`cs.imag/cs_sm.imag`)
  and CP-odd (`-cp.real/cs_sm.imag`) Yukawa couplings, against a SM-like
  Higgs of the same mass (`THDM::set_param_sm`).
- `eff_<hk>_WW`, `eff_<hk>_ZZ`: tree-level coupling ratios.
- `eff_<hk>_gaga`, `eff_<hk>_Zga`, `eff_<hk>_gg`: `sqrt(Gamma/Gamma_SM)`
  from the 2HDMC `DecayTable` loop widths (charged-Higgs loop included in
  `gaga`); `Zga` is zeroed when NaN.
- `eff_<hk>_<hi>Z`: `g(hk hi Z) / (g / 2 cos(theta_w))`.
- `br_<hk>_<hjhi>` (unordered pairs), `br_<hk>_<hi>Z`, `br_<hk>_hcW`:
  branching ratios into BSM final states.
- `total_width_h1`, `total_width_h3`, `total_width_hc`
  (`total_width_H2` already existed).
- Charged sector: `br_t_hcb`, `br_hc_{cs,cb,tb,taunu}`, `br_hc_<hi>W`,
  and the effective H+tb quark couplings `hc_kappa_t`, `hc_kappa_b`
  (MSbar running masses at `mHp`, as in `HBHS::charged_input`).

LFV and invisible BRs are identically zero in this model (Type-I,
non-inert) and are not exported.

## Adapter mapping (python/dhb/adapter.py)

- Neutral states use `Higgs.predictions.effectiveCouplingInput` with
  `calcggH=False, calcHgamgam=False`: ggH and the gamgam width are rescaled
  with the 2HDMC loop-accurate kappas instead of being recomputed from
  tt/bb (which would drop the charged-Higgs contribution).
- First-generation couplings reuse the second generation (`uu:=cc`,
  `dd:=ss`, `ee:=mumu`; exact for Type-I generation universality).
- `kappa_lambda`: 1 for h1 (exact alignment), 0 for h2/h3.
- BSM decays are added as partial widths `BR * Gamma_total(2HDMC)` on top
  of the SM channels; the residual between the reconstructed and the 2HDMC
  total width is reported per point as `width_rel_diff_max` (expected at
  the few-percent level from the effective-coupling approximation).
- Charged Higgs: BRs set directly; production via
  `EffectiveCouplingCxns.ppHpmtb` (LHC13) and the `brtHpb` channel.
- Known limitation: LEP `e+e- -> H+H-` / `hA` pair-production cross
  sections are not set. Irrelevant for the current scan box
  (`mHp = mA >= 280 GeV`), revisit before scanning light masses.

## Enrichment columns (schema `hbhs_enriched_v1`)

Appended after all input columns; input rows pass through unchanged.

| column                | meaning                                          |
|-----------------------|--------------------------------------------------|
| hb_allowed            | 1 if HiggsBounds allows the point                |
| hb_max_obsratio       | largest observed ratio over selected limits      |
| hb_limiting_particle  | particle carrying that limit                     |
| hb_limiting_process   | process description (commas replaced by `;`)     |
| hs_chi2               | HiggsSignals total chi2                          |
| hs_nobs               | number of HS observables                         |
| hs_chi2_sm_ref        | chi2 of a pure SM Higgs at 125.09 (once per run) |
| hs_delta_chi2         | hs_chi2 - hs_chi2_sm_ref                         |
| exp_ok                | hb_allowed and hs_delta_chi2 <= cut              |
| width_rel_diff_max    | width-reconstruction diagnostic (see above)      |
| enrich_status         | ok / skipped_theory_fail / adapter_error:...     |

The cut is `evaluation.experiment_higgstools.hs_delta_chi2_max` in
`configs/theory_atlas_v0.yaml` (default 6.18, 95% CL for 2 dof).

Non-enriched rows keep empty flag fields and NaN numeric fields, so no
point is dropped (same preservation policy as the theory stage).

A `hbhs_manifest.json` is written next to the output with dataset paths,
HiggsTools/dhb versions, the SM reference chi2, row counts, git commit,
and timestamps.

## Combined acceptance definition

```
allowed(point) = theory_ok AND hb_allowed AND (hs_delta_chi2 <= hs_delta_chi2_max)
               = theory_ok AND exp_ok
```

## Entry points

- `scripts/build_higgstools.sh` — pip-installs `lib/higgstools-v1.2` (and
  creates `build/venv` when no virtualenv is active).
- `python -m dhb.enrich --input ... --output ...` — the stage itself.
- `scripts/run_hbhs_enrichment.sh <run_dir|campaign_dir|csv>` — glue that
  locates `evaluate_point.csv` or `index/all_evaluate_point.csv`.
- `scripts/smoke_enrich_hbhs.sh` — end-to-end smoke on
  `configs/smoke_points_hbhs.csv` (3 theory-ok + 2 theory-fail points).

## Tests

- `pytest -m "not integration"` — schema/adapter/CLI unit tests, no
  HiggsTools required.
- `pytest -m integration` — requires `import Higgs` plus
  `DHB_HB_DATASET_ROOT`/`DHB_HS_DATASET_ROOT` (source
  `scripts/setup_env.sh`). Includes: SM-like h is allowed with
  delta_chi2 ~ 0; a decoupled heavy scalar changes nothing; a 400 GeV
  SM-coupled scalar is excluded; fixture points flow end to end.
