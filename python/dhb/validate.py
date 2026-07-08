"""Validate a stage CSV against a data contract (see dhb.contracts).

Reusable at every stage boundary: check that a producer's output (or a
consumer's input) has the required columns and satisfies the declared numeric
invariants, before feeding it downstream. This turns the prose contracts into
a loud, early failure instead of silent wrong-science when a column is renamed
or an evaluator drifts.

Programmatic:

    from dhb import contracts, validate
    report = validate.validate_csv("runs/x/hbhs_enriched.csv", contracts.ENRICHED)
    if not report.ok:
        raise SystemExit(report.describe())

CLI:

    python -m dhb.validate --contract hbhs_enriched_v1 --input runs/x/hbhs_enriched.csv
"""

import argparse
import csv
import sys

from . import contracts, schema


class ValidationReport:
    def __init__(self, contract_name, path):
        self.contract_name = contract_name
        self.path = path
        self.missing_columns = []
        self.invariant_violations = []  # list of (invariant_name, count, first_example)
        self.n_rows = 0
        self.error = ""  # fatal structural problem (empty file, unreadable)

    @property
    def ok(self):
        return (
            not self.error
            and not self.missing_columns
            and not self.invariant_violations
        )

    def describe(self):
        if self.ok:
            return "[DHB][OK] %s satisfies contract %s (%d rows)" % (
                self.path,
                self.contract_name,
                self.n_rows,
            )
        lines = [
            "[DHB][FAIL] %s violates contract %s:" % (self.path, self.contract_name)
        ]
        if self.error:
            lines.append("  - %s" % self.error)
        if self.missing_columns:
            lines.append(
                "  - missing required columns: %s" % ", ".join(self.missing_columns)
            )
        for name, count, example in self.invariant_violations:
            lines.append(
                "  - invariant %r violated in %d row(s); first: %s"
                % (name, count, example)
            )
        return "\n".join(lines)


def _check_ratio_invariant(row, inv):
    """Return an error string if the row violates a ratio invariant, else ""."""
    guard = inv.get("only_when_positive")
    if guard:
        g = schema.parse_float(row, guard)
        if not (schema.is_finite(g) and g > 0):
            return ""  # invariant does not apply to this row
    denom = schema.parse_float(row, inv["denominator"])
    actual = schema.parse_float(row, inv["output"])
    if not schema.is_finite(denom) or denom == 0:
        return ""  # cannot evaluate; the column-presence check covers absence
    if not schema.is_finite(actual):
        return ""  # blank/nan output is allowed (e.g. failed points)
    expected = inv["numerator"] / denom
    rel_tol = inv.get("rel_tol", 1e-6)
    scale = max(abs(expected), abs(actual), 1e-300)
    if abs(actual - expected) / scale > rel_tol:
        return "%s=%r but %s/%s=%r" % (
            inv["output"],
            actual,
            "hbar_c",
            inv["denominator"],
            expected,
        )
    return ""


def validate_csv(path, contract, check_invariants=True):
    """Validate the CSV at ``path`` against ``contract`` (a dict from
    dhb.contracts). Never raises on validation failure: inspect the returned
    ValidationReport.ok."""
    report = ValidationReport(contract["name"], path)
    try:
        fh = open(path, newline="")
    except OSError as exc:
        report.error = "cannot open input: %s" % exc
        return report
    with fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            report.error = "empty CSV (no header)"
            return report
        report.missing_columns = schema.missing_columns(
            reader.fieldnames, contract.get("required_columns", [])
        )
        invariants = contract.get("invariants", []) if check_invariants else []
        # Only check invariants whose columns are all present.
        applicable = [
            inv
            for inv in invariants
            if inv.get("output") in reader.fieldnames
            and inv.get("denominator") in reader.fieldnames
        ]
        counts = {inv["name"]: [0, ""] for inv in applicable}
        for row in reader:
            report.n_rows += 1
            for inv in applicable:
                problem = _check_ratio_invariant(row, inv)
                if problem:
                    entry = counts[inv["name"]]
                    entry[0] += 1
                    if not entry[1]:
                        entry[1] = "row %d: %s" % (report.n_rows, problem)
        report.invariant_violations = [
            (name, c[0], c[1]) for name, c in counts.items() if c[0] > 0
        ]
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate a stage CSV against a dihiggs_boundary data contract."
    )
    parser.add_argument(
        "--contract",
        required=True,
        choices=sorted(contracts.CONTRACTS),
        help="contract name to validate against",
    )
    parser.add_argument("--input", required=True, help="CSV file to validate")
    parser.add_argument(
        "--no-invariants",
        action="store_true",
        help="check only column presence, skip numeric invariants",
    )
    args = parser.parse_args(argv)
    contract = contracts.CONTRACTS[args.contract]
    report = validate_csv(
        args.input, contract, check_invariants=not args.no_invariants
    )
    print(report.describe(), file=sys.stderr if not report.ok else sys.stdout)
    return 0 if report.ok else 2


if __name__ == "__main__":
    sys.exit(main())
