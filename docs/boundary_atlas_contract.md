# Boundary Atlas Contract — `boundary_atlas_v0`

## 1. Purpose

`boundary_atlas` is a small derived layer on top of the existing
`hbhs_enriched.csv` output of `dhb.enrich`. It does not evaluate physics
and does not run HiggsBounds/HiggsSignals — it only reads the already
enriched table and adds an explicit, auditable verdict per point so a
human (or a downstream script) can filter the parameter space without
re-deriving the same if/elif chain every time.

It combines three things that are often conflated:

```
theory validity   -> is this point even a consistent 2HDM point?
experimental validity -> does HiggsBounds/HiggsSignals allow it?
signal usefulness -> is it interesting for a specific search topology?
```

These are kept as separate columns (`is_theory_ok`, `is_exp_ok`, the
`tag_*` columns) rather than collapsed into one boolean, because a point
can be theory-valid but experimentally excluded, experimentally allowed
but numerically uninteresting, or allowed and tagged for one search
channel but not another. Collapsing these into a single flag would hide
exactly the information this layer exists to make visible.

## 2. Input / output

```
input:  <run_dir>/hbhs_enriched.csv        (schema hbhs_enriched_v1)
output: <run_dir>/boundary_atlas.csv
        <run_dir>/boundary_atlas.parquet   (best-effort, may be absent)
        <run_dir>/boundary_atlas_summary.json
        <run_dir>/boundary_atlas_manifest.json
```

Run with:

```
python -m dhb.atlas \
  --input runs/<run>/hbhs_enriched.csv \
  --output-dir runs/<run> \
  --config configs/boundary_atlas_v0.yaml
```

or via `scripts/make_boundary_atlas.sh <run_dir|hbhs_enriched.csv>`.

Every input row produces exactly one output row, unchanged, with the
columns of `ATLAS_APPENDED_COLUMNS` (see §4) appended. Rows are never
dropped; the CLI verifies the output row count equals the input row count
before it commits the CSV. Parquet is written only if `pyarrow` or
`pandas` (with a working parquet engine) is importable; if neither is
available the step is skipped and the reason is recorded in
`boundary_atlas_manifest.json` (`parquet_written: false`,
`parquet_skipped_reason: "..."`) rather than failing or silently omitting
the file.

## 3. Derived branching ratios

`br_hh_H2`, `br_bb_H2`, `br_gg_H2` are not always present in
`hbhs_enriched.csv`. When a BR column is missing but its partial width
(`width_hh_H2`, `width_bb_H2`, `width_gg_H2`) and `total_width_H2` are
both present, it is derived as:

```
br_x = width_x / total_width_H2
```

and blank (not computed) when `total_width_H2` is non-finite or `<= 0`.
Which columns were derived, and which BR columns could not be derived,
are both recorded in `boundary_atlas_summary.json` (`derived_columns`)
and `boundary_atlas_manifest.json` (`derived_columns`,
`not_derivable_columns`). BR columns that are already present in the
input are never re-derived.

## 4. `region_class`

Every row gets exactly one `region_class`, decided by explicit priority
order (first match wins):

```
invalid_input        theory_ok is not a valid 0/1 flag
theory_fail           theory_ok == 0
hbhs_not_run          enrich_status != "ok"
hb_excluded           hb_allowed != 1
hs_tension            hs_delta_chi2 > hs_delta_chi2_max
exp_fail              exp_ok != 1
allowed_low_signal    none of the above — theory- and experimentally-valid
```

`is_theory_ok`, `is_exp_ok`, and `is_allowed` are boolean summaries of the
same underlying flags:

```
is_theory_ok = theory_ok == 1
is_exp_ok    = exp_ok == 1
is_allowed   = is_theory_ok and is_exp_ok and enrich_status == "ok"
```

`region_class == "allowed_low_signal"` and `is_allowed == true` describe
the same set of rows; `region_class` additionally tells you *why* a row
is not allowed when it isn't.

## 5. Candidate tags

```
tag_hh_candidate        is_allowed and br_hh_H2 > br_hh_min
tag_diphoton_candidate  is_allowed and br_gammagamma_H2 > br_gammagamma_min
tag_displaced_candidate is_allowed and ctau_displaced_min_mm <= ctau_mm_H2 <= ctau_displaced_max_mm
tag_prompt_candidate    is_allowed and ctau_mm_H2 < ctau_prompt_max_mm
```

Thresholds come from `configs/boundary_atlas_v0.yaml` (`signal_tags`
block) and are recorded verbatim in `boundary_atlas_manifest.json`
(`settings`). A tag is `false` (never an error) when the underlying signal
column is missing or non-finite; `atlas_notes` records
`missing_signal_columns_for_tags` for an otherwise-allowed row where
neither `br_gammagamma_H2` nor `ctau_mm_H2` could be evaluated.

**Warning: these tags are not exclusions and not paper-level recasts.**
They are boring, threshold-based finder-aids for narrowing down which
rows are worth a closer look for a given search topology (di-Higgs,
diphoton, displaced, prompt). A point without a tag is not thereby
"excluded" from that topology, and a tagged point is not thereby "allowed"
by any real experimental analysis — it has not been through a detector
simulation, a production cross-section, or a recast of any kind. Treat
tags exactly like `region_class`: a reproducible summary of what this
repository's inputs say, nothing more.

## 6. `atlas_schema_version`

Every output row and every manifest/summary carries
`atlas_schema_version = "boundary_atlas_v0"` so downstream consumers can
detect a schema change without guessing from column presence.
