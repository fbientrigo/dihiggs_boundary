"""Attach a versioned DV+jets response to physically linked LLP observables.

Pipeline role:

    model/HBHS rows + per-point MadGraph sigma
        -> dhb.llp_signal -> llp_signal_enriched.csv

This stage does not run MadGraph or Pythia. Production normalization must already
be present on each row as a direct MadGraph result. The external calibration
contains only the Trackless response and normalization constants. One input row
always produces one output row, including when the calibration is invalid; in
that case the output is explicitly marked INVALID_CALIBRATION and the CLI
returns non-zero after writing the auditable failure artifact.
"""

import argparse
import csv
import datetime
import json
import math
import os
import sys

from . import llp_calibration, point_fields, schema
from .enrich import _format_value, _git_commit


# Schema lists live in dhb.schema so contracts, producer and consumer share one
# serialization authority.
SIGNAL_SCHEMA_VERSION = schema.LLP_SIGNAL_SCHEMA_VERSION
NORMALIZED_INPUT_COLUMNS = list(schema.LLP_SIGNAL_NORMALIZED_INPUT_COLUMNS)
SIGNAL_COLUMNS = list(schema.LLP_SIGNAL_COLUMNS)

DOMAIN_SUPPORTED = "SUPPORTED"
DOMAIN_OUTSIDE = "OUTSIDE_RECAST_CALIBRATION"
DOMAIN_MISSING = "MISSING_REQUIRED_OBSERVABLE"
DOMAIN_INVALID_CALIBRATION = "INVALID_CALIBRATION"

STATUS_COMPUTED_VALIDATED = "COMPUTED_VALIDATED"
STATUS_COMPUTED_PROVISIONAL = "COMPUTED_PROVISIONAL"
STATUS_NOT_COMPUTED = "NOT_COMPUTED"


def _blank_signal(calibration=None):
    out = {column: "" for column in SIGNAL_COLUMNS}
    out["llp_signal_schema_version"] = SIGNAL_SCHEMA_VERSION
    out["signal_domain_status"] = (
        DOMAIN_INVALID_CALIBRATION if calibration is None else DOMAIN_MISSING
    )
    out["signal_status"] = STATUS_NOT_COMPUTED
    if calibration is not None:
        out["luminosity_fb"] = calibration["luminosity_fb"]
        out["S95"] = calibration["S95"]
        out["signal_calibration_version"] = calibration["calibration_version"]
        out["signal_calibration_status"] = calibration["calibration_status"]
    return out


def _all_finite(values):
    return all(isinstance(v, float) and math.isfinite(v) for v in values)


def _nonnegative_row_float(row, key):
    text = row.get(key, "")
    if str(text).strip() == "":
        return float("nan"), "missing:%s" % key
    try:
        value = float(text)
    except (TypeError, ValueError):
        return float("nan"), "invalid:%s" % key
    if not math.isfinite(value) or value < 0.0:
        return float("nan"), "invalid:%s" % key
    return value, ""


def _resolve_production_inputs(row):
    """Read the direct MadGraph production result from one joined model row.

    Boundary intentionally accepts no coupling-based production fallback. The
    upstream production stage must join these exact fields onto the same point.
    """
    sigma, sigma_issue = _nonnegative_row_float(row, "sigma_production_fb")
    unc, unc_issue = _nonnegative_row_float(row, "sigma_production_unc_fb")
    sources = {
        "sigma_production_fb": "sigma_production_fb" if math.isfinite(sigma) else "",
        "sigma_production_unc_fb": (
            "sigma_production_unc_fb" if math.isfinite(unc) else ""
        ),
    }
    issues = [issue for issue in (sigma_issue, unc_issue) if issue]
    return sigma, unc, sources, issues


def evaluate_row(row, calibration, calibration_error=""):
    """Return normalized LLP inputs plus signal columns for one input row."""
    physical, sources, issues = point_fields.resolve_signal_inputs(row)
    sigma_prod, sigma_prod_unc, production_sources, production_issues = (
        _resolve_production_inputs(row)
    )
    sources.update(production_sources)
    issues = sorted(set(issues + production_issues))

    out = dict(physical)
    signal = _blank_signal(calibration)
    if math.isfinite(sigma_prod):
        signal["sigma_production_fb"] = sigma_prod
    if math.isfinite(sigma_prod_unc):
        signal["sigma_production_unc_fb"] = sigma_prod_unc
    signal["signal_input_sources"] = json.dumps(
        sources, sort_keys=True, separators=(",", ":")
    )

    if calibration is None:
        notes = list(issues)
        if calibration_error:
            notes.append("invalid_calibration:%s" % calibration_error)
        signal["signal_domain_status"] = DOMAIN_INVALID_CALIBRATION
        signal["signal_notes"] = ";".join(sorted(set(notes)))
        out.update(signal)
        return out

    required = [
        physical["m_H2_GeV"],
        physical["g_hH2H2_GeV"],
        physical["ctau_mm_H2"],
        physical["br_bb_H2"],
        sigma_prod,
        sigma_prod_unc,
    ]
    if not _all_finite(required):
        signal["signal_domain_status"] = DOMAIN_MISSING
        signal["signal_notes"] = ";".join(issues)
        out.update(signal)
        return out

    mass = physical["m_H2_GeV"]
    ctau = physical["ctau_mm_H2"]
    br_bb = physical["br_bb_H2"]
    mass_ok = llp_calibration.mass_supported(calibration, mass)
    ctau_ok = llp_calibration.ctau_supported(calibration, ctau)
    if not mass_ok or not ctau_ok:
        signal["signal_domain_status"] = DOMAIN_OUTSIDE
        notes = list(issues)
        if not mass_ok:
            notes.append("mass_outside_calibration")
        if not ctau_ok:
            notes.append("ctau_outside_calibration")
        signal["signal_notes"] = ";".join(sorted(set(notes)))
        out.update(signal)
        return out

    aeff, aeff_unc = llp_calibration.acceptance_response(calibration, ctau)

    # H2->bb is forced in the recast event sample. The physical BR is therefore
    # a normalization factor and is applied exactly once here as BR_bb^2.
    br2 = br_bb * br_bb
    sigma_4b = sigma_prod * br2
    sigma_visible = sigma_4b * aeff
    sigma_visible_unc = math.sqrt(
        (br2 * aeff * sigma_prod_unc) ** 2
        + (br2 * sigma_prod * aeff_unc) ** 2
    )
    luminosity = calibration["luminosity_fb"]
    n_expected = luminosity * sigma_visible
    n_unc = luminosity * sigma_visible_unc
    ratio = n_expected / calibration["S95"]

    signal.update(
        {
            "sigma_production_fb": sigma_prod,
            "sigma_production_unc_fb": sigma_prod_unc,
            "Trackless_Aeff": aeff,
            "Trackless_Aeff_unc": aeff_unc,
            "sigma_4b_fb": sigma_4b,
            "sigma_visible_fb": sigma_visible,
            "N_expected": n_expected,
            "N_expected_139fb": (
                n_expected
                if math.isclose(luminosity, 139.0, rel_tol=0.0, abs_tol=1e-12)
                else ""
            ),
            "N_expected_unc": n_unc,
            "N_over_S95": ratio,
            "threshold_class": llp_calibration.threshold_class(calibration, ratio),
            "signal_domain_status": DOMAIN_SUPPORTED,
            "signal_status": (
                STATUS_COMPUTED_VALIDATED
                if calibration["calibration_status"] == "VALIDATED"
                else STATUS_COMPUTED_PROVISIONAL
            ),
            "signal_notes": ";".join(issues),
        }
    )
    out.update(signal)
    return out


def load_calibration(path):
    import yaml

    with open(path) as fh:
        raw = yaml.safe_load(fh)
    return llp_calibration.validate_calibration(raw)


def run(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Combine per-point MadGraph production with a versioned Trackless "
            "LLP response."
        )
    )
    parser.add_argument(
        "--input", required=True, help="input CSV with model/HBHS + MadGraph sigma"
    )
    parser.add_argument(
        "--output", required=True, help="llp_signal_enriched.csv to write"
    )
    parser.add_argument(
        "--calibration", required=True, help="versioned Trackless response YAML"
    )
    args = parser.parse_args(argv)

    calibration = None
    calibration_error = ""
    try:
        calibration = load_calibration(args.calibration)
    except (OSError, llp_calibration.CalibrationError, ValueError) as exc:
        calibration_error = str(exc).replace("\n", " ").replace(",", ";")
        print(
            "[DHB][FAIL] invalid LLP calibration; writing failure-marked rows: %s"
            % calibration_error,
            file=sys.stderr,
        )

    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tmp_output = args.output + ".tmp"
    counts = {
        "total": 0,
        DOMAIN_SUPPORTED: 0,
        DOMAIN_OUTSIDE: 0,
        DOMAIN_MISSING: 0,
        DOMAIN_INVALID_CALIBRATION: 0,
    }

    try:
        infile = open(args.input, newline="")
    except OSError as exc:
        print("[DHB][FAIL] cannot open input CSV: %s" % exc, file=sys.stderr)
        return 2

    with infile:
        reader = csv.DictReader(infile)
        if reader.fieldnames is None:
            print("[DHB][FAIL] Empty input CSV: %s" % args.input, file=sys.stderr)
            return 2
        input_columns = list(reader.fieldnames)
        appended_normalized = [
            c for c in NORMALIZED_INPUT_COLUMNS if c not in input_columns
        ]
        appended_signal = [c for c in SIGNAL_COLUMNS if c not in input_columns]
        output_columns = input_columns + appended_normalized + appended_signal

        with open(tmp_output, "w", newline="") as outfile:
            writer = csv.DictWriter(
                outfile, fieldnames=output_columns, lineterminator="\n"
            )
            writer.writeheader()
            for row in reader:
                enriched = evaluate_row(row, calibration, calibration_error)
                merged = dict(row)
                merged.update(enriched)
                writer.writerow(
                    {k: _format_value(merged.get(k, "")) for k in output_columns}
                )
                counts["total"] += 1
                counts[enriched["signal_domain_status"]] += 1

    os.replace(tmp_output, args.output)

    manifest = {
        "stage": "llp_signal_enrichment",
        "schema_version": SIGNAL_SCHEMA_VERSION,
        "production_policy": "MADGRAPH_PER_PHYSICAL_POINT_REQUIRED",
        "input": os.path.abspath(args.input),
        "output": os.path.abspath(args.output),
        "calibration": os.path.abspath(args.calibration),
        "calibration_valid": calibration is not None,
        "calibration_error": calibration_error,
        "calibration_version": (
            calibration["calibration_version"] if calibration is not None else ""
        ),
        "calibration_status": (
            calibration["calibration_status"] if calibration is not None else ""
        ),
        "calibration_schema_version": (
            calibration["schema_version"] if calibration is not None else ""
        ),
        "counts": counts,
        "row_counts": {"input": counts["total"], "output": counts["total"]},
        "dhb_version": __import__("dhb").__version__,
        "git_commit": _git_commit(os.path.dirname(os.path.abspath(__file__))),
        "started_at_utc": started_at,
        "finished_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    manifest_path = os.path.join(
        os.path.dirname(os.path.abspath(args.output)), "llp_signal_manifest.json"
    )
    tmp_manifest = manifest_path + ".tmp"
    with open(tmp_manifest, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_manifest, manifest_path)

    print(
        "[DHB] llp_signal completed: total=%d supported=%d outside=%d "
        "missing=%d invalid_calibration=%d"
        % (
            counts["total"],
            counts[DOMAIN_SUPPORTED],
            counts[DOMAIN_OUTSIDE],
            counts[DOMAIN_MISSING],
            counts[DOMAIN_INVALID_CALIBRATION],
        )
    )
    print("[DHB] output: %s" % args.output)
    print("[DHB] manifest: %s" % manifest_path)
    return 0 if calibration is not None else 2


if __name__ == "__main__":
    sys.exit(run())
