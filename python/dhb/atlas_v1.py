"""Boundary Atlas v1: classify theory, HB/HS and LLP signal states.

This stage consumes numbers already present in ``llp_signal_enriched.csv``. It
does not execute 2HDMC, HiggsTools, MadGraph, Pythia or recast code.
"""

import argparse
import collections
import csv
import datetime
import json
import math
import os
import sys

from . import schema
from .atlas import write_parquet
from .enrich import _format_value, _git_commit, _git_dirty, _sha256_file
from .llp_signal import (
    DOMAIN_INVALID_CALIBRATION,
    DOMAIN_MISSING,
    DOMAIN_OUTSIDE,
    DOMAIN_SUPPORTED,
    SIGNAL_SCHEMA_VERSION,
    STATUS_COMPUTED_PROVISIONAL,
    STATUS_COMPUTED_VALIDATED,
)


ATLAS_SCHEMA_VERSION = schema.BOUNDARY_ATLAS_V1_SCHEMA_VERSION

REQUIRED_COLUMNS = [
    "theory_ok",
    "hb_allowed",
    "hs_delta_chi2",
    "exp_ok",
    "enrich_status",
] + list(schema.LLP_SIGNAL_NORMALIZED_INPUT_COLUMNS) + list(schema.LLP_SIGNAL_COLUMNS)

APPENDED_COLUMNS = [
    "atlas_schema_version",
    "region_class",
    "is_theory_ok",
    "is_exp_ok",
    "is_allowed",
    "is_signal_domain_supported",
    "is_signal_calibration_validated",
    "is_signal_at_or_above_S95",
    "atlas_notes",
]

REGION_CLASSES = [
    "invalid_input",
    "theory_fail",
    "hbhs_not_run",
    "hb_excluded",
    "hs_tension",
    "exp_fail",
    "allowed_no_signal_calibration",
    "allowed_outside_recast_domain",
    "allowed_signal_below",
    "allowed_signal_near_threshold",
    "allowed_signal_above",
]


def _finite(row, key):
    value = schema.parse_float(row, key)
    return value if schema.is_finite(value) else float("nan")


def _supported_signal_state_is_consistent(row, calibration_status, ratio, threshold):
    """Check the redundant LLP handoff fields before assigning a signal class.

    Atlas is intentionally a classifier, but it is also the final boundary for
    a serialized LLP artifact.  A stale or tampered row must not become a
    scientific signal category merely because it contains plausible text.
    """
    expected_status = {
        "VALIDATED": STATUS_COMPUTED_VALIDATED,
        "PROVISIONAL": STATUS_COMPUTED_PROVISIONAL,
    }.get(calibration_status)
    if (
        row.get("llp_signal_schema_version", "") != SIGNAL_SCHEMA_VERSION
        or row.get("signal_status", "") != expected_status
    ):
        return False

    expected = _finite(row, "N_expected")
    s95 = _finite(row, "S95")
    aeff = _finite(row, "Trackless_Aeff")
    visible = _finite(row, "sigma_visible_fb")
    if not (
        math.isfinite(ratio)
        and math.isfinite(expected)
        and expected >= 0.0
        and math.isfinite(s95)
        and s95 > 0.0
        and math.isfinite(aeff)
        and 0.0 <= aeff <= 1.0
        and math.isfinite(visible)
        and visible >= 0.0
    ):
        return False
    if not math.isclose(ratio, expected / s95, rel_tol=1e-9, abs_tol=1e-12):
        return False
    # The precise near band belongs to the calibration, but its ordering gives
    # these two invariant checks without importing a second threshold model.
    if threshold == "BELOW":
        return ratio < 1.0
    if threshold == "ABOVE":
        return ratio > 1.0
    return threshold == "NEAR"


def classify_row(row):
    notes = []
    theory_raw = row.get("theory_ok", "").strip()
    if theory_raw not in ("0", "1"):
        return {
            "atlas_schema_version": ATLAS_SCHEMA_VERSION,
            "region_class": "invalid_input",
            "is_theory_ok": False,
            "is_exp_ok": False,
            "is_allowed": False,
            "is_signal_domain_supported": False,
            "is_signal_calibration_validated": False,
            "is_signal_at_or_above_S95": False,
            "atlas_notes": "theory_ok_not_0_or_1",
        }

    is_theory_ok = theory_raw == "1"
    enrich_status = row.get("enrich_status", "")
    hb_allowed = schema.parse_flag(row, "hb_allowed")
    is_exp_ok = schema.parse_flag(row, "exp_ok")
    hs_delta_chi2 = _finite(row, "hs_delta_chi2")
    is_allowed = bool(
        is_theory_ok
        and hb_allowed
        and is_exp_ok
        and enrich_status == schema.ENRICH_STATUS_OK
    )

    domain = row.get("signal_domain_status", "")
    calibration_status = row.get("signal_calibration_status", "")
    threshold = row.get("threshold_class", "")
    ratio = _finite(row, "N_over_S95")
    domain_supported = domain == DOMAIN_SUPPORTED
    if domain_supported and not _supported_signal_state_is_consistent(
        row, calibration_status, ratio, threshold
    ):
        domain_supported = False
        notes.append("inconsistent_supported_signal_state")
    calibration_validated = domain_supported and calibration_status == "VALIDATED"
    signal_at_or_above = bool(
        domain_supported and math.isfinite(ratio) and ratio >= 1.0
    )

    if not is_theory_ok:
        region = "theory_fail"
    elif enrich_status != schema.ENRICH_STATUS_OK:
        region = "hbhs_not_run"
    elif not hb_allowed:
        region = "hb_excluded"
    elif math.isfinite(hs_delta_chi2) and not is_exp_ok:
        region = "hs_tension"
    elif not is_exp_ok:
        region = "exp_fail"
    elif domain in (DOMAIN_MISSING, DOMAIN_INVALID_CALIBRATION, ""):
        region = "allowed_no_signal_calibration"
    elif domain == DOMAIN_OUTSIDE:
        region = "allowed_outside_recast_domain"
    elif domain_supported:
        if threshold == "BELOW":
            region = "allowed_signal_below"
        elif threshold == "NEAR":
            region = "allowed_signal_near_threshold"
        elif threshold == "ABOVE":
            region = "allowed_signal_above"
        else:
            region = "allowed_no_signal_calibration"
            notes.append("supported_domain_without_threshold_class")
    else:
        region = "allowed_no_signal_calibration"
        notes.append("unknown_signal_domain_status:%s" % domain)

    if domain_supported and not calibration_validated:
        notes.append("signal_calibration_not_validated")
    if domain_supported and not math.isfinite(ratio):
        notes.append("supported_domain_missing_N_over_S95")

    return {
        "atlas_schema_version": ATLAS_SCHEMA_VERSION,
        "region_class": region,
        "is_theory_ok": is_theory_ok,
        "is_exp_ok": is_exp_ok,
        "is_allowed": is_allowed,
        "is_signal_domain_supported": domain_supported,
        "is_signal_calibration_validated": calibration_validated,
        "is_signal_at_or_above_S95": signal_at_or_above,
        "atlas_notes": ";".join(notes),
    }


def run(argv=None):
    parser = argparse.ArgumentParser(
        description="Build boundary_atlas_v1 from llp_signal_enriched.csv."
    )
    parser.add_argument("--input", required=True, help="llp_signal_enriched CSV")
    parser.add_argument("--output-dir", required=True, help="output directory")
    args = parser.parse_args(argv)

    os.makedirs(args.output_dir, exist_ok=True)
    csv_path = os.path.join(args.output_dir, "boundary_atlas_v1.csv")
    parquet_path = os.path.join(args.output_dir, "boundary_atlas_v1.parquet")
    summary_path = os.path.join(args.output_dir, "boundary_atlas_v1_summary.json")
    manifest_path = os.path.join(args.output_dir, "boundary_atlas_v1_manifest.json")
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with open(args.input, newline="") as infile:
        reader = csv.DictReader(infile)
        if reader.fieldnames is None:
            print("[DHB][FAIL] Empty input CSV: %s" % args.input, file=sys.stderr)
            return 2
        missing = schema.missing_columns(reader.fieldnames, REQUIRED_COLUMNS)
        if missing:
            print(
                "[DHB][FAIL] llp_signal input is missing required columns: %s"
                % ",".join(missing[:8]),
                file=sys.stderr,
            )
            return 2

        input_columns = list(reader.fieldnames)
        output_columns = input_columns + [
            c for c in APPENDED_COLUMNS if c not in input_columns
        ]
        counts = collections.OrderedDict((name, 0) for name in REGION_CLASSES)
        n_total = n_allowed = n_supported = n_validated = n_at_or_above = 0
        tmp_csv = csv_path + ".tmp"
        with open(tmp_csv, "w", newline="") as outfile:
            writer = csv.DictWriter(
                outfile, fieldnames=output_columns, lineterminator="\n"
            )
            writer.writeheader()
            for row in reader:
                verdict = classify_row(row)
                merged = dict(row)
                merged.update(verdict)
                writer.writerow(
                    {k: _format_value(merged.get(k, "")) for k in output_columns}
                )
                n_total += 1
                counts[verdict["region_class"]] += 1
                n_allowed += int(verdict["is_allowed"])
                n_supported += int(verdict["is_signal_domain_supported"])
                n_validated += int(verdict["is_signal_calibration_validated"])
                n_at_or_above += int(verdict["is_signal_at_or_above_S95"])
    os.replace(tmp_csv, csv_path)

    parquet_written, parquet_reason = write_parquet(csv_path, parquet_path)
    summary = {
        "atlas_schema_version": ATLAS_SCHEMA_VERSION,
        "n_total": n_total,
        "n_allowed": n_allowed,
        "n_signal_domain_supported": n_supported,
        "n_signal_calibration_validated": n_validated,
        "n_signal_at_or_above_S95": n_at_or_above,
        "n_by_region_class": dict(counts),
    }
    tmp_summary = summary_path + ".tmp"
    with open(tmp_summary, "w") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_summary, summary_path)

    manifest = {
        "stage": "boundary_atlas_v1",
        "atlas_schema_version": ATLAS_SCHEMA_VERSION,
        "input": os.path.abspath(args.input),
        "input_sha256": _sha256_file(args.input),
        "output_csv": os.path.abspath(csv_path),
        "output_parquet": os.path.abspath(parquet_path) if parquet_written else "",
        "output_summary": os.path.abspath(summary_path),
        "row_counts": {"input": n_total, "output": n_total},
        "parquet_written": parquet_written,
        "parquet_skipped_reason": parquet_reason,
        "dhb_version": __import__("dhb").__version__,
        "git_commit": _git_commit(os.path.dirname(os.path.abspath(__file__))),
        "git_dirty": _git_dirty(os.path.dirname(os.path.abspath(__file__))),
        "started_at_utc": started_at,
        "finished_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    tmp_manifest = manifest_path + ".tmp"
    with open(tmp_manifest, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_manifest, manifest_path)

    print(
        "[DHB] boundary_atlas_v1 completed: total=%d allowed=%d supported=%d"
        % (n_total, n_allowed, n_supported)
    )
    print("[DHB] output: %s" % csv_path)
    print("[DHB] summary: %s" % summary_path)
    print("[DHB] manifest: %s" % manifest_path)
    return 0


if __name__ == "__main__":
    sys.exit(run())
