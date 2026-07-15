#!/usr/bin/env python3
"""Mechanically extract the golden characterization inputs for evaluate_point.

Writes tests/golden/evaluate_point_v1/input.csv and input_provenance.json.

Every physical input coordinate is copied *verbatim* (as the exact source
string, no float round-trip) from a cited, reviewed source row; nothing is
transcribed by hand. The one exception is G07, whose mH is *generated* by an
explicit deterministic rule (nextafter(125.09, -inf)) because no committed
construction-failure fixture exists; see SELECTIVE_MIGRATION_AUDIT.md section
7 (workspace root).

Golden case -> source:
  G01  tests/fixtures/evaluate_point_sample.csv        row p1   (tracked)
  G02  tests/fixtures/evaluate_point_sample.csv        row p4   (tracked)
  G03  tests/fixtures/evaluate_point_sample.csv        row p5   (tracked)
  G04  runs/refined_lhs_boundary/points.csv row lhs_000278 (ignored, run
       manifest: commit 073cd142e571b3a29ff4c0b64b4bbe5d482d4c2e, seed 12345,
       clean status)
  G05  runs/tiny_boundary/input_points.csv row
       tiny_mH300_mA300_tb10000_l61em12_M300 (ignored, run manifest: commit
       87803164fa0d9601ea5391151b68a8ca50308df7, dirty tree; only the INPUT
       coordinates are reused -- the expected output is regenerated cleanly)
  G07  generated: G01 coordinates with mH = nextafter(125.09, -inf), which
       makes stock THDM::set_param_phys return false (m_h > m_H branch,
       lib/2HDMC-1.8.0/src/THDM.cpp).

The ignored runs/ sources exist only on machines that produced those runs, so
this script is a *regeneration* tool, not a CI step; CI consumes the committed
input.csv. If a source is missing the script fails loudly.
"""

import csv
import hashlib
import json
import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(REPO_ROOT, "tests", "golden", "evaluate_point_v1")

INPUT_HEADER = ["point_id", "mH", "mA", "tan_beta", "lambda6", "M"]

FIXTURE = os.path.join(REPO_ROOT, "tests", "fixtures", "evaluate_point_sample.csv")
G04_SOURCE = os.path.join(REPO_ROOT, "runs", "refined_lhs_boundary", "points.csv")
G05_SOURCE = os.path.join(REPO_ROOT, "runs", "tiny_boundary", "input_points.csv")

# The fixture is an evaluate_point *output* CSV; these are the output columns
# holding the (unmodified, 17-digit serialized) input coordinates.
FIXTURE_INPUT_COLUMNS = ["mH", "mA", "tan_beta", "lambda6_input", "M"]

KMH = 125.09  # must match kMh in src/evaluate_point.cpp


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_rows_verbatim(path, wanted_ids, columns):
    """Return {point_id: [verbatim field strings]} for the wanted rows."""
    found = {}
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row["point_id"]
            if pid in wanted_ids:
                found[pid] = [row[c] for c in columns]
    missing = [pid for pid in wanted_ids if pid not in found]
    if missing:
        raise SystemExit(
            "[DHB][FAIL] rows %s not found in %s" % (missing, path)
        )
    return found


def main():
    for path in (FIXTURE, G04_SOURCE, G05_SOURCE):
        if not os.path.exists(path):
            raise SystemExit("[DHB][FAIL] missing golden source: %s" % path)

    fixture_rows = read_rows_verbatim(
        FIXTURE, ["p1", "p4", "p5"], FIXTURE_INPUT_COLUMNS
    )
    g04_rows = read_rows_verbatim(
        G04_SOURCE, ["lhs_000278"], ["mH", "mA", "tan_beta", "lambda6", "M"]
    )
    g05_rows = read_rows_verbatim(
        G05_SOURCE,
        ["tiny_mH300_mA300_tb10000_l61em12_M300"],
        ["mH", "mA", "tan_beta", "lambda6", "M"],
    )

    # G07: deterministic construction failure. Generated, not sourced.
    g07_mh = math.nextafter(KMH, -math.inf)
    assert g07_mh < KMH
    g07_mh_text = "%.17g" % g07_mh
    # The serialization must round-trip to the exact generated double.
    assert float(g07_mh_text) == g07_mh
    g07_id = "g07_set_param_phys_fail_mH_nextafter_below_mh"
    g07_fields = [g07_mh_text] + fixture_rows["p1"][1:]

    golden = [
        ("G01", ["p1"] + fixture_rows["p1"]),
        ("G02", ["p4"] + fixture_rows["p4"]),
        ("G03", ["p5"] + fixture_rows["p5"]),
        ("G04", ["lhs_000278"] + g04_rows["lhs_000278"]),
        (
            "G05",
            ["tiny_mH300_mA300_tb10000_l61em12_M300"]
            + g05_rows["tiny_mH300_mA300_tb10000_l61em12_M300"],
        ),
        ("G07", [g07_id] + g07_fields),
    ]

    os.makedirs(GOLDEN_DIR, exist_ok=True)
    input_csv = os.path.join(GOLDEN_DIR, "input.csv")
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(INPUT_HEADER)
        for _, fields in golden:
            writer.writerow(fields)

    provenance = {
        "description": (
            "Extraction provenance for the golden evaluate_point inputs. "
            "All fields are verbatim source strings except G07.mH, which is "
            "generated by the documented rule."
        ),
        "extraction_script": "scripts/extract_golden_evaluate_point_inputs.py",
        "input_csv_sha256": sha256_file(input_csv),
        "sources": {
            "fixture": {
                "path": "tests/fixtures/evaluate_point_sample.csv",
                "sha256": sha256_file(FIXTURE),
                "tracked": True,
            },
            "g04_run": {
                "path": "runs/refined_lhs_boundary/points.csv",
                "sha256": sha256_file(G04_SOURCE),
                "tracked": False,
                "run_manifest_commit": "073cd142e571b3a29ff4c0b64b4bbe5d482d4c2e",
                "run_seed": 12345,
                "run_git_status": "clean",
            },
            "g05_run": {
                "path": "runs/tiny_boundary/input_points.csv",
                "sha256": sha256_file(G05_SOURCE),
                "tracked": False,
                "run_manifest_commit": "87803164fa0d9601ea5391151b68a8ca50308df7",
                "run_git_status": "dirty",
                "note": (
                    "input coordinates only; expected output is regenerated "
                    "from a clean build, never copied from this dirty run"
                ),
            },
        },
        "cases": {
            case: {"point_id": fields[0], "input_fields": fields[1:]}
            for case, fields in golden
        },
        "g07_generation_rule": {
            "rule": "mH = nextafter(125.09, -inf); other coordinates copied from G01/p1",
            "mH_decimal": g07_mh_text,
            "mH_hex": g07_mh.hex(),
            "expected_failure": (
                "stock THDM::set_param_phys returns false when m_h > m_H "
                "(lib/2HDMC-1.8.0/src/THDM.cpp)"
            ),
        },
    }

    provenance_path = os.path.join(GOLDEN_DIR, "input_provenance.json")
    with open(provenance_path, "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2, sort_keys=False)
        f.write("\n")

    print("[DHB] wrote %s (%d golden rows)" % (input_csv, len(golden)))
    print("[DHB] wrote %s" % provenance_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
