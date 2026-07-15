#!/usr/bin/env python3
"""Regenerate the golden expected output and manifest for evaluate_point.

Maintainer/regeneration tool, not a CI step: CI consumes the committed
tests/golden/evaluate_point_v1/{input.csv,expected.csv,manifest.json} via
tests/test_golden_evaluate_point.py.

Steps:
  1. Re-extract input.csv from the cited sources
     (scripts/extract_golden_evaluate_point_inputs.py). Requires the ignored
     runs/ sources, so this only works on a machine holding those runs.
  2. Run the already-built build/bin/evaluate_point on input.csv, twice, and
     require byte-identical output before accepting it as the oracle.
  3. Write manifest.json recording source commit/dirty state, toolchain,
     vendored-2HDMC identity, checksums, row counts, and the exact commands.

Build first:
  scripts/build_2hdmc.sh && scripts/build_evaluate_point.sh

The expected.csv produced here is a GENERATED ORACLE: it freezes what the
current implementation computes. It is not a set of manually authored,
independently verified physics values.
"""

import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(REPO_ROOT, "tests", "golden", "evaluate_point_v1")
BINARY = os.path.join(REPO_ROOT, "build", "bin", "evaluate_point")

GOLDEN_SCHEMA = "evaluate_point_v1"
GOLDEN_SUITE_VERSION = 1


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, **kwargs):
    return subprocess.run(
        cmd, check=True, capture_output=True, text=True, cwd=REPO_ROOT, **kwargs
    )


def cmd_output(cmd):
    return run(cmd).stdout.strip()


def csv_data_rows(path):
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        return sum(1 for _ in reader)


def main():
    if not os.path.exists(BINARY):
        raise SystemExit(
            "[DHB][FAIL] missing %s -- run scripts/build_2hdmc.sh && "
            "scripts/build_evaluate_point.sh first" % BINARY
        )

    extract_cmd = [
        sys.executable,
        os.path.join(REPO_ROOT, "scripts", "extract_golden_evaluate_point_inputs.py"),
    ]
    run(extract_cmd)

    input_csv = os.path.join(GOLDEN_DIR, "input.csv")
    expected_csv = os.path.join(GOLDEN_DIR, "expected.csv")
    repeat_csv = os.path.join(GOLDEN_DIR, "expected.repeat_check.tmp.csv")

    eval_cmd = [BINARY, input_csv, expected_csv]
    run(eval_cmd)
    run([BINARY, input_csv, repeat_csv])

    try:
        with open(expected_csv, "rb") as a, open(repeat_csv, "rb") as b:
            if a.read() != b.read():
                raise SystemExit(
                    "[DHB][FAIL] two consecutive evaluate_point runs on the "
                    "golden input are not byte-identical; refusing to freeze "
                    "a nondeterministic oracle"
                )
    finally:
        os.remove(repeat_csv)

    with open(os.path.join(GOLDEN_DIR, "input_provenance.json"), "r") as f:
        input_provenance = json.load(f)

    manifest = {
        "golden_suite": GOLDEN_SCHEMA,
        "golden_suite_version": GOLDEN_SUITE_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "oracle_kind": (
            "generated characterization oracle (output of the current "
            "implementation), not manually authored physics assertions"
        ),
        "generation_commands": [
            " ".join(["python3", "scripts/extract_golden_evaluate_point_inputs.py"]),
            " ".join(
                [
                    "build/bin/evaluate_point",
                    "tests/golden/evaluate_point_v1/input.csv",
                    "tests/golden/evaluate_point_v1/expected.csv",
                ]
            ),
            " ".join(["python3", "scripts/generate_golden_evaluate_point.py"]),
        ],
        "source": {
            "repo": "dihiggs_boundary",
            "git_commit": cmd_output(["git", "rev-parse", "HEAD"]),
            "git_status_short": run(
                ["git", "status", "--short"]
            ).stdout.splitlines(),
            "tracked_files_modified": bool(
                cmd_output(["git", "diff", "--name-only", "HEAD"])
            ),
            "evaluator_source": "src/evaluate_point.cpp",
        },
        "dependencies": {
            "2HDMC": {
                "version": "1.8 (stock)",
                "vendored_path": "lib/2HDMC-1.8.0",
                "git_tree_hash": cmd_output(
                    ["git", "rev-parse", "HEAD:lib/2HDMC-1.8.0"]
                ),
                "positivity_stability_alias": (
                    "Constraints::check_positivity() and "
                    "Constraints::check_stability() both return "
                    "model.check_stability() in this vendored tree"
                ),
            },
            "gsl": cmd_output(["gsl-config", "--version"]),
        },
        "toolchain": {
            "compiler": cmd_output(["g++", "--version"]).splitlines()[0],
            "compile_flags": "-std=c++11 -Wall -Wextra -O2 (scripts/build_evaluate_point.sh)",
            "build_commands": [
                "scripts/build_2hdmc.sh",
                "scripts/build_evaluate_point.sh",
            ],
            "uname": cmd_output(["uname", "-srm"]),
        },
        "files": {
            "input.csv": {
                "sha256": sha256_file(input_csv),
                "data_rows": csv_data_rows(input_csv),
            },
            "expected.csv": {
                "sha256": sha256_file(expected_csv),
                "data_rows": csv_data_rows(expected_csv),
            },
        },
        "repeat_run_byte_identical": True,
        "golden_cases": {
            case: {
                "point_id": info["point_id"],
                "source": (
                    input_provenance["g07_generation_rule"]
                    if case == "G07"
                    else {
                        "G01": input_provenance["sources"]["fixture"],
                        "G02": input_provenance["sources"]["fixture"],
                        "G03": input_provenance["sources"]["fixture"],
                        "G04": input_provenance["sources"]["g04_run"],
                        "G05": input_provenance["sources"]["g05_run"],
                    }[case]
                ),
            }
            for case, info in input_provenance["cases"].items()
        },
    }

    manifest_path = os.path.join(GOLDEN_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print("[DHB] wrote %s" % expected_csv)
    print("[DHB] wrote %s" % manifest_path)
    print(
        "[DHB] rows: input=%d expected=%d"
        % (
            manifest["files"]["input.csv"]["data_rows"],
            manifest["files"]["expected.csv"]["data_rows"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
