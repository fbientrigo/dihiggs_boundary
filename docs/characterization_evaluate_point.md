# evaluate_point golden characterization suite

Status: characterization only — this suite **freezes** the current behavior of
`src/evaluate_point.cpp`; it does not certify that behavior as physically
correct. It exists so that the planned selective migration (see
`SELECTIVE_MIGRATION_AUDIT.md` at the workspace root, sections 7, 8 and 10)
starts from a reproducible executable oracle instead of prose contracts.

## What is frozen

- **Files**: `tests/golden/evaluate_point_v1/`
  - `input.csv` — 6 golden points (header `point_id,mH,mA,tan_beta,lambda6,M`).
  - `expected.csv` — the full evaluator output for those points, produced by a
    clean build of the current implementation. This is a **generated oracle**,
    not a set of manually authored physics values.
  - `input_provenance.json` — where every input coordinate was copied from.
  - `manifest.json` — commit/dirty state, toolchain, dependency identity,
    SHA-256 checksums, row counts, generation commands.
- **Tests**: `tests/test_golden_evaluate_point.py` — the comparator and the
  manually authored, reviewed assertions (flags, invariants, thresholds).
- **Entry point**: `scripts/run_golden_characterization.sh` (used by the
  `evaluate-point-golden` CI job).

### Golden cases

| Case | point_id | Source | Characterized behavior |
|---|---|---|---|
| G01 | `p1` | `tests/fixtures/evaluate_point_sample.csv` (tracked) | Successful construction; all theory flags 1; positive γγ, Zγ, bb, gg and total widths |
| G02 | `p4` | same fixture | Unitarity failure (`unitarity_ok=0`, this row also fails perturbativity); rejection stage `unitarity`; row preserved |
| G03 | `p5` | same fixture | Positivity **and** stability failure (aliased, see below); rejection stage `positivity` |
| G04 | `lhs_000278` | `runs/refined_lhs_boundary/points.csv` (ignored; run manifest commit `073cd142…`, seed 12345, clean tree) | Perturbativity-only failure among the four primitive constraint flags |
| G05 | `tiny_mH300_mA300_tb10000_l61em12_M300` | `runs/tiny_boundary/input_points.csv` (ignored; run manifest commit `87803164…`, **dirty** tree — only the input coordinates were reused; the output was regenerated from a clean build) | Accepted repository-threshold characterization point; `ctau_mm_H2 ≈ 1.628e-3 mm` (= 1.628 micrometres) `≥ 1e-3 mm`, the historical repository threshold (see note below) |
| G07 | `g07_set_param_phys_fail_mH_nextafter_below_mh` | generated: G01 coordinates with `mH = nextafter(125.09, -inf)` | Deterministic construction failure (`THDM::set_param_phys` returns false when `m_h > m_H`); the row is preserved with flags 0, NaN numerics, stage `set_param_phys` |

G06 (the lambda1-target case) belongs to `main_dihiggs` and is intentionally
not part of this repository's suite.

**G05 threshold note.** G05's lifetime is
`ctau_mm_H2 ≈ 1.628e-3 mm = 1.628 micrometres`. The `≥ 1e-3 mm` assertion
characterizes a historical repository threshold and nothing more: crossing it
does **not** establish an experimentally displaced or physically long-lived
signature (1.628 micrometres is far below any detector displacement scale).
The numerical threshold assertion is retained purely as characterization of
repository behavior.

**G02 coverage limitation (known, non-blocking).** G02 fails **both**
unitarity and perturbativity; its full flag vector is intentionally frozen
as-is. No readily available fixture or run point that fails unitarity alone
was found among the accessible sources, so unitarity is not isolated from
perturbativity by any golden point. This is a known coverage limitation of
the suite. No synthetic point is fabricated or presented as physical evidence
to fill the gap (the only synthetic artifacts are the clearly labeled
boolean-logic check and G07's `nextafter` construction-failure input).

Inputs were extracted **mechanically** by
`scripts/extract_golden_evaluate_point_inputs.py` (verbatim source strings, no
hand transcription, no float round-trip). The only generated coordinate is
G07's `mH`, produced by the documented `nextafter` rule and serialized with
round-trip-exact precision.

## How to regenerate the golden output

Regeneration is a deliberate, reviewed act — never a way to make a red test
green. It requires a machine that still holds the ignored `runs/` sources for
G04/G05.

```bash
scripts/build_2hdmc.sh
scripts/build_evaluate_point.sh
python3 scripts/generate_golden_evaluate_point.py
```

The generator re-extracts the inputs, runs the binary **twice** and refuses to
freeze output that is not byte-identical across the two runs, then rewrites
`expected.csv` and `manifest.json`. Review the diff of all four golden files
and record why the behavior legitimately changed.

To run the suite (CI-equivalent):

```bash
bash scripts/run_golden_characterization.sh
# or, if already built:
DHB_REQUIRE_EVALUATE_POINT=1 python3 -m pytest tests/test_golden_evaluate_point.py
```

Without `DHB_REQUIRE_EVALUATE_POINT=1` the binary-dependent tests skip when
`build/bin/evaluate_point` is absent (so the plain python CI job still runs
all static golden tests).

## Provenance of the committed oracle

Authoritative record: `tests/golden/evaluate_point_v1/manifest.json`. At
generation time:

- boundary commit `ae9bb132dd0b042b9718b744fef8e3db3439beba`. No production
  source or vendored physics source was modified. The one tracked
  modification present during generation was limited to the characterization
  CI workflow (`.github/workflows/ci.yml`, recorded as
  `tracked_files_modified: true` in the manifest); the characterization files
  themselves (tests, scripts, docs, golden data) were otherwise untracked
  pending review, and are listed in the manifest's `git_status_short`,
- `g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`, flags
  `-std=c++11 -Wall -Wextra -O2` (`scripts/build_evaluate_point.sh`),
- GSL 2.7.1,
- vendored **stock** 2HDMC 1.8 at `lib/2HDMC-1.8.0` (git tree hash in the
  manifest; `external_tools.lock.yaml` records no local patches).

## Numerical comparison policy

Discrete data (point ids, the seven flags, `soft_z2_only`, `hbhs_block_ok`,
`yukawa_assignment`, `scalar_z2_status`, `rejection_stage`,
`rejection_reason`) is compared **exactly**. NaN/finite masks must match
exactly. Repeated runs of the same binary must be **byte-identical** — the
tolerances below are not slack for nondeterminism; they only define what
counts as "the same behavior" when the suite is rebuilt with a different but
sane toolchain (different libm/GSL rounding), so that real drift fails with a
per-field diagnostic.

| Group | Columns | rel | abs | Rationale |
|---|---|---|---|---|
| exact | `mh mH mA mHp tan_beta sin_ba lambda6_input lambda7_input lambda6_derived lambda7_derived M M2` | 0 | 0 | Pass-through inputs / compile-time constants; copied unmodified. `lambda6_derived`/`lambda7_derived` are stored-and-returned by the vendored 2HDMC, and executable evidence confirms the serialized expected and regenerated values round-trip to the same Float64 — a broad absolute floor (the former 1e-11) is invalid for magnitudes like G05's `lambda6 = 1e-12`, and would let `0.0` pass against `1e-12` |
| tight | `beta m12_sq_input` | 1e-15 | 0 | One libm call (atan, sin·cos) from inputs; ≤ few ULP |
| recon | `lambda1..lambda5 m12_sq_derived tan_beta_derived M2_recomputed` | 1e-12 | 1e-11 | 2HDMC parameter reconstruction; absolute floor covers cancellation noise (e.g. `lambda4 ≈ -1e-8` on G01 is itself a cancellation residual with noise ≈ ulp(m²·tanβ)/v² ~ 1e-13) |
| resid | `relative_M2_reconstruction_error` | 0 | 1e-11 | A pure residual (~1e-14); relative comparison is meaningless |
| loop | all widths, BRs, `ctau_mm_H2` and the entire HBHS block | 1e-10 | 1e-24 | Loop-level numerics via GSL/libm; absolute floor covers cancellation residuals of exactly-zero couplings (`width_hh_H2 ~ 6e-32` at `sin(β−α)=1`) |

One broad tolerance is deliberately **not** used: it would hide drift in O(1)
couplings behind headroom needed by 1e-30-scale residuals.

If a future toolchain legitimately breaks bit-identity on
`lambda6_derived`/`lambda7_derived`, the reviewed fallback policy is a
relative tolerance ≤ 5e-15 with **no** absolute floor, and an expected zero
must still require an actual zero — `0.0` and `1e-12` must always remain
distinguishable.

Non-finite comparison order: NaN and ±infinity are classified **before** any
tolerance arithmetic. NaN matches only NaN (the expected NaN-mask contract);
an infinity matches only an infinity of the same sign; infinity vs finite
fails in both directions. Row shape is also guarded explicitly: every
expected and actual row must have exactly as many fields as the header before
any field-by-field comparison (truncated or overlong rows fail loudly instead
of being silently absorbed by `zip`).

Executable invariants checked on every applicable row:

- input rows == output rows, identical `point_id` order (failed construction
  rows must not disappear);
- `triple_ok == positivity_ok && unitarity_ok && perturbativity_ok`;
- `lambda6_derived == lambda6_input` and `lambda7_derived == lambda7_input`
  **exactly** on every constructed row (pass-through; an expected zero
  requires an actual zero), NaN on failed construction;
- `theory_ok == set_param_phys_ok && triple_ok && stability_ok && width_ok`
  with `width_ok := total_width_H2 finite and > 0`;
- `M2_recomputed == m12_sq_derived / (sin β · cos β)` (rel ≤ 1e-13 against a
  Python recomputation; the evaluator's own
  `relative_M2_reconstruction_error < 1e-9`);
- `ctau_mm_H2 == 1.973269804e-13 GeV·mm / total_width_H2[GeV]` (lifetime in
  **millimetres**; the constant is `kHbarCGeVmm` in `src/evaluate_point.cpp`,
  mirrored by `dhb.contracts.HBAR_C_GEV_MM` and
  `conventions/physics_conventions.yaml`);
- all partial widths finite and nonnegative on `theory_ok` rows;
- serial vs two-shard (`split_point_csv.py` → binary → `merge_shard_outputs.py`)
  scientific rows identical.

## Known positivity/stability alias

In the exact vendored source being built, `Constraints::check_positivity()`
and `Constraints::check_stability()` **both** `return model.check_stability();`
(`lib/2HDMC-1.8.0/src/Constraints.cpp`, lines 568–575; the header even
documents `check_positivity` as doing "the exact same" as `check_stability`).
Consequently `positivity_ok == stability_ok` on every constructed row, and the
`stability_ok` term in `theory_ok` is currently redundant even though it is
present in the expression.

The suite makes this visible in two ways —
`test_positivity_stability_alias_in_vendored_source` (source-level) and
`test_positivity_stability_alias_in_data` (data-level) — and does **not**
rename, repair or reinterpret it. No physical golden point with
`triple_ok=1, stability_ok=0` can exist under this dependency; that
combination is exercised only by a clearly labeled synthetic
boolean-logic test (`test_synthetic_theory_ok_boolean_logic`). Whether
positivity and stability are intended synonyms or require genuinely distinct
checks is a scientific-contract decision deferred to the core-v2 work
(audit section 9, blocker 5).

## What this suite does not establish

- It does **not** validate the physics: the oracle is the current
  implementation's output, not independently verified theory values.
- It does not test HiggsBounds/HiggsSignals enrichment, datasets, campaigns,
  the atlas stage, or any downstream consumer.
- It does not establish an independent stability veto (see the alias above).
- It does not characterize the `main_dihiggs` lambda1-target path (that is
  migration PR 2) and says nothing about `mh=125.0` vs `125.09` deltas.
- Six points cannot certify the whole parameter space; they pin the discrete
  decision structure and representative numerics of each rejection class.
- No golden point isolates a unitarity-only failure (see the G02 coverage
  limitation above) — a known, non-blocking gap.
