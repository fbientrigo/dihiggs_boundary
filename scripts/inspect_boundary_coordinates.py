#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


COORDINATES = ["mH", "mA", "tan_beta", "lambda6_input", "M"]
FLAGS = [
    "set_param_phys_ok",
    "positivity_ok",
    "unitarity_ok",
    "perturbativity_ok",
    "stability_ok",
    "triple_ok",
    "theory_ok",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Inspect boundary output by coordinate.")
    p.add_argument("--input", required=True, help="evaluate_point output CSV.")
    p.add_argument("--outdir", required=True, help="Output directory for inspection artifacts.")
    p.add_argument(
        "--flag-column",
        default="theory_ok",
        help="0/1 acceptance column to aggregate (e.g. exp_ok on an hbhs_enriched CSV).",
    )
    return p


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_one(value: str) -> bool:
    return str(value).strip() == "1"


def as_float_key(value: str) -> tuple[float, str]:
    try:
        return (float(value), value)
    except ValueError:
        return (float("inf"), value)


def frac(n: int, d: int) -> float:
    return float(n) / float(d) if d else 0.0


def require_columns(rows: list[dict[str, str]], columns: list[str]) -> None:
    if not rows:
        raise SystemExit("[DHB][FAIL] Input CSV has no rows.")
    missing = [c for c in columns if c not in rows[0]]
    if missing:
        raise SystemExit(f"[DHB][FAIL] Missing columns: {missing}")


def write_theory_ok_points(rows: list[dict[str, str]], outdir: Path, flag: str) -> int:
    theory_rows = [r for r in rows if is_one(r[flag])]
    output = outdir / f"{flag}_points.csv"

    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(theory_rows)

    return len(theory_rows)


def write_coordinate_acceptance(rows: list[dict[str, str]], outdir: Path, flags: list[str]) -> None:
    output = outdir / "coordinate_acceptance.csv"

    with output.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "coordinate",
            "value",
            "total",
            *[f"{flag}_count" for flag in flags],
            *[f"{flag}_fraction" for flag in flags],
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for coord in COORDINATES:
            values = sorted({r[coord] for r in rows}, key=as_float_key)
            for value in values:
                subset = [r for r in rows if r[coord] == value]
                total = len(subset)

                record: dict[str, str | int] = {
                    "coordinate": coord,
                    "value": value,
                    "total": total,
                }

                for flag in flags:
                    count = sum(is_one(r[flag]) for r in subset)
                    record[f"{flag}_count"] = count
                for flag in flags:
                    count = int(record[f"{flag}_count"])
                    record[f"{flag}_fraction"] = f"{frac(count, total):.17g}"

                writer.writerow(record)


def write_rejection_by_coordinate(rows: list[dict[str, str]], outdir: Path) -> None:
    output = outdir / "rejection_by_coordinate.csv"

    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "coordinate",
                "value",
                "rejection_stage",
                "count",
                "fraction_within_coordinate_value",
            ],
        )
        writer.writeheader()

        for coord in COORDINATES:
            values = sorted({r[coord] for r in rows}, key=as_float_key)
            for value in values:
                subset = [r for r in rows if r[coord] == value]
                total = len(subset)
                counts = Counter(r["rejection_stage"] for r in subset)

                for stage, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                    writer.writerow(
                        {
                            "coordinate": coord,
                            "value": value,
                            "rejection_stage": stage,
                            "count": count,
                            "fraction_within_coordinate_value": f"{frac(count, total):.17g}",
                        }
                    )


def write_pair_acceptance(rows: list[dict[str, str]], outdir: Path, flag: str) -> None:
    output = outdir / "pair_acceptance.csv"

    pairs = [
        ("mH", "mA"),
        ("mH", "tan_beta"),
        ("mH", "lambda6_input"),
        ("mH", "M"),
        ("mA", "tan_beta"),
        ("mA", "lambda6_input"),
        ("mA", "M"),
        ("tan_beta", "lambda6_input"),
        ("tan_beta", "M"),
        ("lambda6_input", "M"),
    ]

    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "x",
                "y",
                "x_value",
                "y_value",
                "total",
                f"{flag}_count",
                f"{flag}_fraction",
                "dominant_rejection_stage",
                "dominant_rejection_count",
            ],
        )
        writer.writeheader()

        for x, y in pairs:
            grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
            for row in rows:
                grouped[(row[x], row[y])].append(row)

            for (xv, yv), subset in sorted(
                grouped.items(),
                key=lambda item: (as_float_key(item[0][0])[0], as_float_key(item[0][1])[0]),
            ):
                total = len(subset)
                flag_count = sum(is_one(r[flag]) for r in subset)
                rejection_counts = Counter(r["rejection_stage"] for r in subset)
                dominant_stage, dominant_count = sorted(
                    rejection_counts.items(),
                    key=lambda kv: (-kv[1], kv[0]),
                )[0]

                writer.writerow(
                    {
                        "x": x,
                        "y": y,
                        "x_value": xv,
                        "y_value": yv,
                        "total": total,
                        f"{flag}_count": flag_count,
                        f"{flag}_fraction": f"{frac(flag_count, total):.17g}",
                        "dominant_rejection_stage": dominant_stage,
                        "dominant_rejection_count": dominant_count,
                    }
                )


def write_markdown_summary(
    rows: list[dict[str, str]], outdir: Path, theory_ok_count: int, flag: str
) -> None:
    output = outdir / "coordinate_summary.md"
    total = len(rows)

    global_rejections = Counter(r["rejection_stage"] for r in rows)

    with output.open("w", encoding="utf-8") as f:
        f.write("# Boundary coordinate inspection\n\n")
        f.write(f"- Total points: `{total}`\n")
        f.write(f"- {flag} points: `{theory_ok_count}`\n")
        f.write(f"- {flag} fraction: `{frac(theory_ok_count, total):.6f}`\n\n")

        f.write("## Global rejection stages\n\n")
        f.write("| Rejection stage | Count | Fraction |\n")
        f.write("|---|---:|---:|\n")
        for stage, count in sorted(global_rejections.items(), key=lambda kv: (-kv[1], kv[0])):
            f.write(f"| `{stage}` | {count} | {frac(count, total):.6f} |\n")

        f.write(f"\n## {flag} by coordinate\n\n")
        for coord in COORDINATES:
            f.write(f"### `{coord}`\n\n")
            f.write(f"| Value | Total | {flag} | Fraction |\n")
            f.write("|---:|---:|---:|---:|\n")
            values = sorted({r[coord] for r in rows}, key=as_float_key)
            for value in values:
                subset = [r for r in rows if r[coord] == value]
                n = len(subset)
                ok = sum(is_one(r[flag]) for r in subset)
                f.write(f"| `{value}` | {n} | {ok} | {frac(ok, n):.6f} |\n")
            f.write("\n")


def main() -> int:
    args = build_parser().parse_args()
    input_csv = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    flag = args.flag_column
    flags = FLAGS if flag in FLAGS else FLAGS + [flag]

    rows = read_rows(input_csv)
    require_columns(rows, COORDINATES + flags + ["rejection_stage"])

    flag_count = write_theory_ok_points(rows, outdir, flag)
    write_coordinate_acceptance(rows, outdir, flags)
    write_rejection_by_coordinate(rows, outdir)
    write_pair_acceptance(rows, outdir, flag)
    write_markdown_summary(rows, outdir, flag_count, flag)

    print(f"[DHB] Coordinate inspection written to: {outdir}")
    print(f"[DHB] {flag}_points={flag_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
