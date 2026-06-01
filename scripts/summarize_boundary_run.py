#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


FLAG_COLUMNS = [
    "set_param_phys_ok",
    "positivity_ok",
    "unitarity_ok",
    "perturbativity_ok",
    "stability_ok",
    "triple_ok",
    "theory_ok",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Summarize evaluate_point boundary output.")
    p.add_argument("--input", required=True, help="evaluate_point output CSV.")
    p.add_argument("--outdir", required=True, help="Directory for summary artifacts.")
    return p


def as_bool01(value: str) -> int:
    return 1 if str(value).strip() == "1" else 0


def frac(n: int, d: int) -> float:
    return float(n) / float(d) if d else 0.0


def main() -> int:
    args = build_parser().parse_args()
    input_csv = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not input_csv.exists():
        raise SystemExit(f"[DHB][FAIL] Missing input CSV: {input_csv}")

    with input_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    if total == 0:
        raise SystemExit("[DHB][FAIL] No rows found in evaluate_point output.")

    flag_counts = {}
    for col in FLAG_COLUMNS:
        if col not in rows[0]:
            raise SystemExit(f"[DHB][FAIL] Missing required flag column: {col}")
        count = sum(as_bool01(row[col]) for row in rows)
        flag_counts[col] = count

    if "rejection_stage" not in rows[0]:
        raise SystemExit("[DHB][FAIL] Missing rejection_stage column.")

    rejection_counts = Counter(row["rejection_stage"] for row in rows)

    theory_summary_csv = outdir / "theory_acceptance_summary.csv"
    with theory_summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "count", "fraction"])
        writer.writeheader()
        writer.writerow({"metric": "total_points", "count": total, "fraction": "1.0"})
        for col in FLAG_COLUMNS:
            writer.writerow(
                {
                    "metric": col,
                    "count": flag_counts[col],
                    "fraction": f"{frac(flag_counts[col], total):.17g}",
                }
            )

    rejection_csv = outdir / "rejection_counts.csv"
    with rejection_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["rejection_stage", "count", "fraction"])
        writer.writeheader()
        for stage, count in sorted(rejection_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            writer.writerow(
                {
                    "rejection_stage": stage,
                    "count": count,
                    "fraction": f"{frac(count, total):.17g}",
                }
            )

    summary_md = outdir / "summary.md"
    with summary_md.open("w", encoding="utf-8") as f:
        f.write("# Tiny boundary run summary\n\n")
        f.write(f"- Evaluated CSV: `{input_csv}`\n")
        f.write(f"- Total points: `{total}`\n\n")

        f.write("## Acceptance flags\n\n")
        f.write("| Metric | Count | Fraction |\n")
        f.write("|---|---:|---:|\n")
        for col in FLAG_COLUMNS:
            count = flag_counts[col]
            f.write(f"| `{col}` | {count} | {frac(count, total):.6f} |\n")

        f.write("\n## Rejection stages\n\n")
        f.write("| Rejection stage | Count | Fraction |\n")
        f.write("|---|---:|---:|\n")
        for stage, count in sorted(rejection_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            f.write(f"| `{stage}` | {count} | {frac(count, total):.6f} |\n")

        if flag_counts["theory_ok"] == 0:
            f.write("\n## Note\n\n")
            f.write("No `theory_ok=1` point was found in this tiny grid.\n")
            f.write("This is not a pipeline failure, but it means a valid-candidate smoke is still needed.\n")

    print(f"[DHB] Summary written: {summary_md}")
    print(f"[DHB] Rejection counts: {rejection_csv}")
    print(f"[DHB] Theory summary: {theory_summary_csv}")
    print(f"[DHB] total_points={total}")
    print(f"[DHB] theory_ok={flag_counts['theory_ok']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
