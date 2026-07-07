"""CLI: build the boundary_atlas derived layer from an hbhs_enriched CSV.

Usage:
    python -m dhb.atlas --input runs/<run>/hbhs_enriched.csv \
        --output-dir runs/<run> \
        [--config configs/boundary_atlas_v0.yaml]

Every input row is passed through unchanged and extended with a
region_class verdict and a handful of non-authoritative candidate tags
(schema boundary_atlas_v0). Rows are never dropped. Outputs are written
atomically (.tmp -> rename): boundary_atlas.csv, boundary_atlas.parquet
(best-effort), boundary_atlas_summary.json, boundary_atlas_manifest.json.
"""

import argparse
import collections
import csv
import datetime
import json
import os
import sys

from . import contracts, schema

# enrich.py already has boring, tested CSV-value formatting and git-commit
# helpers; reuse them instead of re-implementing.
from .enrich import _format_value, _git_commit

ATLAS_SCHEMA_VERSION = "boundary_atlas_v0"

# The columns this stage must find in its input come from the enriched
# contract (dhb.contracts.ENRICHED), the single source of truth, rather than
# being redeclared here. The split into theory vs HBHS below is kept for the
# error message that tells the user which half is missing.
REQUIRED_THEORY_COLUMNS = [
    "set_param_phys_ok",
    "positivity_ok",
    "unitarity_ok",
    "perturbativity_ok",
    "stability_ok",
    "theory_ok",
    "rejection_stage",
    "rejection_reason",
]

# Required per the task; reuse the shared HB/HS enrichment column list
# rather than redeclaring it.
REQUIRED_HBHS_COLUMNS = list(schema.ENRICHMENT_COLUMNS)

# Guard: the ad-hoc lists above must stay equal to the enriched contract's
# required set (order-independent). This keeps atlas and dhb.contracts in sync.
assert set(REQUIRED_THEORY_COLUMNS + REQUIRED_HBHS_COLUMNS) == set(
    contracts.ENRICHED["required_columns"]
)

# "If present" columns: never required, only tracked in the manifest/summary.
OPTIONAL_COORDINATE_COLUMNS = [
    "point_id",
    "mh",
    "mH",
    "mA",
    "mHp",
    "tan_beta",
    "lambda6",
    "lambda7",
    "M",
    "M2",
    "m12_sq",
]

OPTIONAL_SIGNAL_COLUMNS = [
    "total_width_H2",
    "ctau_mm_H2",
    "br_gammagamma_H2",
    "br_hh_H2",
    "br_bb_H2",
    "br_gg_H2",
    "width_hh_H2",
    "width_bb_H2",
    "width_gg_H2",
]

# BR column -> partial-width column it can be derived from (both divided by
# total_width_H2). Order matches OPTIONAL_SIGNAL_COLUMNS.
DERIVABLE_BRS = {
    "br_hh_H2": "width_hh_H2",
    "br_bb_H2": "width_bb_H2",
    "br_gg_H2": "width_gg_H2",
}

ATLAS_APPENDED_COLUMNS = [
    "atlas_schema_version",
    "region_class",
    "is_theory_ok",
    "is_exp_ok",
    "is_allowed",
    "tag_hh_candidate",
    "tag_diphoton_candidate",
    "tag_displaced_candidate",
    "tag_prompt_candidate",
    "atlas_notes",
]

REGION_CLASSES = [
    "invalid_input",
    "theory_fail",
    "hbhs_not_run",
    "hb_excluded",
    "hs_tension",
    "exp_fail",
    "allowed_low_signal",
]

DEFAULT_SETTINGS = {
    "hs_delta_chi2_max": 6.18,
    "br_hh_min": 0.0,
    "br_gammagamma_min": 0.0,
    "br_bb_min": 0.0,
    "ctau_prompt_max_mm": 1.0e-3,
    "ctau_displaced_min_mm": 1.0e-3,
    "ctau_displaced_max_mm": 1.0e4,
    "max_width_rel_diff": 0.5,
    "require_enrich_status_ok_for_exp": True,
}


def load_atlas_config(config_path):
    """Read configs/boundary_atlas_v0.yaml. Missing file/module is not an
    error: DEFAULT_SETTINGS applies."""
    settings = dict(DEFAULT_SETTINGS)
    if not config_path:
        return settings
    try:
        import yaml
    except ImportError:
        return settings
    try:
        with open(config_path) as fh:
            config = yaml.safe_load(fh) or {}
    except OSError:
        return settings
    experiment = config.get("experiment") or {}
    if "hs_delta_chi2_max" in experiment:
        settings["hs_delta_chi2_max"] = float(experiment["hs_delta_chi2_max"])
    signal_tags = config.get("signal_tags") or {}
    for key in (
        "br_hh_min",
        "br_gammagamma_min",
        "br_bb_min",
        "ctau_prompt_max_mm",
        "ctau_displaced_min_mm",
        "ctau_displaced_max_mm",
    ):
        if key in signal_tags:
            settings[key] = float(signal_tags[key])
    quality = config.get("quality") or {}
    if "max_width_rel_diff" in quality:
        settings["max_width_rel_diff"] = float(quality["max_width_rel_diff"])
    if "require_enrich_status_ok_for_exp" in quality:
        settings["require_enrich_status_ok_for_exp"] = bool(
            quality["require_enrich_status_ok_for_exp"]
        )
    return settings


def plan_derived_signal_columns(fieldnames):
    """Decide once (from the header) which BR columns are missing but
    derivable from a partial width + total_width_H2, and which are missing
    and cannot be derived. Returns (derived, not_derivable)."""
    present = set(fieldnames or [])
    derived = []
    not_derivable = []
    for br_column, width_column in DERIVABLE_BRS.items():
        if br_column in present:
            continue
        if width_column in present and "total_width_H2" in present:
            derived.append(br_column)
        else:
            not_derivable.append(br_column)
    derived.sort()
    not_derivable.sort()
    return derived, not_derivable


def derive_row_brs(row, derived_columns):
    """Compute br_x = width_x / total_width_H2 for each column in
    derived_columns. Blank ("") when the inputs are missing/non-finite or
    total_width_H2 <= 0, matching the repo's CSV null convention."""
    result = {}
    total_width = schema.parse_float(row, "total_width_H2")
    for br_column in derived_columns:
        width_column = DERIVABLE_BRS[br_column]
        width = schema.parse_float(row, width_column)
        if schema.is_finite(total_width) and total_width > 0 and schema.is_finite(width):
            result[br_column] = width / total_width
        else:
            result[br_column] = ""
    return result


def classify_row(row, settings):
    """Boring, explicit classification of a single enriched row. Returns a
    dict with exactly the ATLAS_APPENDED_COLUMNS keys (booleans as Python
    bool; formatted to CSV strings only at write time)."""
    notes = []

    theory_ok_raw = row.get("theory_ok", "").strip()
    if theory_ok_raw not in ("0", "1"):
        region_class = "invalid_input"
        notes.append("theory_ok_not_0_or_1")
        is_theory_ok = False
        is_exp_ok = False
        is_allowed = False
    else:
        is_theory_ok = theory_ok_raw == "1"
        enrich_status = row.get("enrich_status", "")
        hb_allowed = schema.parse_flag(row, "hb_allowed")
        is_exp_ok = schema.parse_flag(row, "exp_ok")
        hs_delta_chi2 = schema.parse_float(row, "hs_delta_chi2")

        is_allowed = bool(
            is_theory_ok and is_exp_ok and enrich_status == schema.ENRICH_STATUS_OK
        )

        if not is_theory_ok:
            region_class = "theory_fail"
        elif enrich_status != schema.ENRICH_STATUS_OK:
            region_class = "hbhs_not_run"
        elif not hb_allowed:
            region_class = "hb_excluded"
        elif schema.is_finite(hs_delta_chi2) and hs_delta_chi2 > settings["hs_delta_chi2_max"]:
            region_class = "hs_tension"
        elif not is_exp_ok:
            region_class = "exp_fail"
        else:
            region_class = "allowed_low_signal"

        width_rel_diff_max = schema.parse_float(row, "width_rel_diff_max")
        if schema.is_finite(width_rel_diff_max) and width_rel_diff_max > settings[
            "max_width_rel_diff"
        ]:
            notes.append("width_rel_diff_max_exceeds_quality_threshold")

    br_hh = schema.parse_float(row, "br_hh_H2")
    br_gammagamma = schema.parse_float(row, "br_gammagamma_H2")
    ctau_mm = schema.parse_float(row, "ctau_mm_H2")

    tag_hh_candidate = bool(
        is_allowed and schema.is_finite(br_hh) and br_hh > settings["br_hh_min"]
    )
    tag_diphoton_candidate = bool(
        is_allowed
        and schema.is_finite(br_gammagamma)
        and br_gammagamma > settings["br_gammagamma_min"]
    )
    tag_displaced_candidate = bool(
        is_allowed
        and schema.is_finite(ctau_mm)
        and settings["ctau_displaced_min_mm"] <= ctau_mm <= settings["ctau_displaced_max_mm"]
    )
    tag_prompt_candidate = bool(
        is_allowed and schema.is_finite(ctau_mm) and ctau_mm < settings["ctau_prompt_max_mm"]
    )

    if is_allowed and not schema.is_finite(ctau_mm) and not schema.is_finite(br_gammagamma):
        notes.append("missing_signal_columns_for_tags")

    return {
        "atlas_schema_version": ATLAS_SCHEMA_VERSION,
        "region_class": region_class,
        "is_theory_ok": is_theory_ok,
        "is_exp_ok": is_exp_ok,
        "is_allowed": is_allowed,
        "tag_hh_candidate": tag_hh_candidate,
        "tag_diphoton_candidate": tag_diphoton_candidate,
        "tag_displaced_candidate": tag_displaced_candidate,
        "tag_prompt_candidate": tag_prompt_candidate,
        "atlas_notes": ";".join(notes),
    }


def write_parquet(csv_path, parquet_path):
    """Best-effort CSV -> Parquet conversion. Returns (written, reason).
    reason is "" on success, otherwise why parquet was skipped."""
    try:
        import pyarrow.csv as pv
        import pyarrow.parquet as pq
    except ImportError:
        pass
    else:
        try:
            table = pv.read_csv(csv_path)
            pq.write_table(table, parquet_path)
            return True, ""
        except Exception as exc:
            return False, "pyarrow failed to write parquet: %s" % exc
    try:
        import pandas as pd
    except ImportError:
        return False, "pyarrow and pandas are both unavailable; parquet skipped"
    try:
        df = pd.read_csv(csv_path)
        df.to_parquet(parquet_path)
        return True, ""
    except ImportError as exc:
        return False, "pandas has no parquet engine installed: %s" % exc
    except Exception as exc:
        return False, "pandas failed to write parquet: %s" % exc


def run(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the boundary_atlas derived layer from an "
        "hbhs_enriched CSV."
    )
    parser.add_argument("--input", required=True, help="hbhs_enriched CSV")
    parser.add_argument(
        "--output-dir", required=True, help="directory to write atlas outputs to"
    )
    parser.add_argument(
        "--config",
        default="",
        help="boundary_atlas config yaml (default: built-in thresholds)",
    )
    args = parser.parse_args(argv)

    settings = load_atlas_config(args.config)
    os.makedirs(args.output_dir, exist_ok=True)

    csv_path = os.path.join(args.output_dir, "boundary_atlas.csv")
    parquet_path = os.path.join(args.output_dir, "boundary_atlas.parquet")
    summary_path = os.path.join(args.output_dir, "boundary_atlas_summary.json")
    manifest_path = os.path.join(args.output_dir, "boundary_atlas_manifest.json")

    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with open(args.input, newline="") as infile:
        reader = csv.DictReader(infile)
        if reader.fieldnames is None:
            print("[DHB][FAIL] Empty input CSV: %s" % args.input, file=sys.stderr)
            return 2
        input_columns = list(reader.fieldnames)
        missing = schema.missing_columns(
            input_columns, REQUIRED_THEORY_COLUMNS + REQUIRED_HBHS_COLUMNS
        )
        if missing:
            print(
                "[DHB][FAIL] Input is missing required theory/HB-HS columns "
                "(is this really an hbhs_enriched.csv?): %s" % ",".join(missing),
                file=sys.stderr,
            )
            return 2

        derived_columns, not_derivable = plan_derived_signal_columns(input_columns)
        missing_optional = sorted(
            set(
                c
                for c in OPTIONAL_COORDINATE_COLUMNS + OPTIONAL_SIGNAL_COLUMNS
                if c not in input_columns
            )
            - set(derived_columns)
        )

        output_columns = input_columns + derived_columns + ATLAS_APPENDED_COLUMNS

        region_counts = collections.OrderedDict((r, 0) for r in REGION_CLASSES)
        n_total = 0
        n_theory_ok = 0
        n_exp_ok = 0
        n_allowed = 0
        n_hh_candidate = 0
        n_diphoton_candidate = 0
        n_displaced_candidate = 0
        n_prompt_candidate = 0

        tmp_csv_path = csv_path + ".tmp"
        with open(tmp_csv_path, "w", newline="") as outfile:
            writer = csv.DictWriter(
                outfile, fieldnames=output_columns, lineterminator="\n"
            )
            writer.writeheader()
            for row in reader:
                merged = dict(row)
                merged.update(derive_row_brs(row, derived_columns))
                verdict = classify_row(merged, settings)
                merged.update(verdict)
                writer.writerow({k: _format_value(v) for k, v in merged.items()})

                n_total += 1
                region_counts[verdict["region_class"]] += 1
                if verdict["is_theory_ok"]:
                    n_theory_ok += 1
                if verdict["is_exp_ok"]:
                    n_exp_ok += 1
                if verdict["is_allowed"]:
                    n_allowed += 1
                if verdict["tag_hh_candidate"]:
                    n_hh_candidate += 1
                if verdict["tag_diphoton_candidate"]:
                    n_diphoton_candidate += 1
                if verdict["tag_displaced_candidate"]:
                    n_displaced_candidate += 1
                if verdict["tag_prompt_candidate"]:
                    n_prompt_candidate += 1

    os.replace(tmp_csv_path, csv_path)

    parquet_written, parquet_skip_reason = write_parquet(csv_path, parquet_path)

    summary = {
        "atlas_schema_version": ATLAS_SCHEMA_VERSION,
        "n_total": n_total,
        "n_theory_ok": n_theory_ok,
        "n_exp_ok": n_exp_ok,
        "n_allowed": n_allowed,
        "n_by_region_class": dict(region_counts),
        "n_hh_candidate": n_hh_candidate,
        "n_diphoton_candidate": n_diphoton_candidate,
        "n_displaced_candidate": n_displaced_candidate,
        "n_prompt_candidate": n_prompt_candidate,
        "input_columns": input_columns,
        "output_columns": output_columns,
        "derived_columns": derived_columns,
        "missing_optional_columns": missing_optional,
    }
    tmp_summary_path = summary_path + ".tmp"
    with open(tmp_summary_path, "w") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_summary_path, summary_path)

    manifest = {
        "stage": "boundary_atlas",
        "atlas_schema_version": ATLAS_SCHEMA_VERSION,
        "input": os.path.abspath(args.input),
        "output_csv": os.path.abspath(csv_path),
        "output_parquet": os.path.abspath(parquet_path) if parquet_written else "",
        "output_summary": os.path.abspath(summary_path),
        "output_manifest": os.path.abspath(manifest_path),
        "config": os.path.abspath(args.config) if args.config else "",
        "settings": settings,
        # One output row per input row, always: the loop above never
        # filters or skips, so these are the same count by construction.
        "row_counts": {"input": n_total, "output": n_total},
        "derived_columns": derived_columns,
        "not_derivable_columns": not_derivable,
        "missing_optional_columns": missing_optional,
        "parquet_written": parquet_written,
        "parquet_skipped_reason": parquet_skip_reason,
        "dhb_version": __import__("dhb").__version__,
        "git_commit": _git_commit(os.path.dirname(os.path.abspath(__file__))),
        "started_at_utc": started_at,
        "finished_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    tmp_manifest_path = manifest_path + ".tmp"
    with open(tmp_manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_manifest_path, manifest_path)

    print(
        "[DHB] boundary_atlas completed: total=%d allowed=%d theory_ok=%d "
        "exp_ok=%d" % (n_total, n_allowed, n_theory_ok, n_exp_ok)
    )
    print("[DHB] output: %s" % csv_path)
    if parquet_written:
        print("[DHB] output: %s" % parquet_path)
    else:
        print("[DHB] parquet skipped: %s" % parquet_skip_reason)
    print("[DHB] summary: %s" % summary_path)
    print("[DHB] manifest: %s" % manifest_path)
    return 0


if __name__ == "__main__":
    sys.exit(run())
