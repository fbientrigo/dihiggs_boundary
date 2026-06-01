#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_PAIRS = [
    ("mH", "mA"),
    ("mH", "tan_beta"),
    ("mH", "lambda6_input"),
    ("mH", "M"),
    ("tan_beta", "lambda6_input"),
    ("tan_beta", "M"),
    ("lambda6_input", "M"),
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Plot simple 2D boundary scatter plots.")
    p.add_argument("--input", required=True, help="evaluate_point output CSV.")
    p.add_argument("--outdir", required=True, help="Directory for PNG plots.")
    p.add_argument(
        "--pairs",
        default="",
        help="Optional comma-separated pairs like mH:mA,tan_beta:lambda6_input.",
    )
    return p


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_pairs(text: str) -> list[tuple[str, str]]:
    if not text.strip():
        return DEFAULT_PAIRS
    pairs = []
    for item in text.split(","):
        if ":" not in item:
            raise SystemExit(f"[DHB][FAIL] Invalid pair: {item}")
        x, y = item.split(":", 1)
        pairs.append((x.strip(), y.strip()))
    return pairs


def to_float(value: str) -> float:
    return float(value)


def safe_name(name: str) -> str:
    return name.replace("/", "_").replace("\\", "_").replace(" ", "_")


def main() -> int:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise SystemExit(
            "[DHB][FAIL] matplotlib is required for plotting. "
            "Install it or skip this optional plotting step. "
            f"Original error: {exc}"
        )

    args = build_parser().parse_args()
    input_csv = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows = read_rows(input_csv)
    if not rows:
        raise SystemExit("[DHB][FAIL] No rows found.")

    pairs = parse_pairs(args.pairs)

    required = {"theory_ok", "rejection_stage"}
    for x, y in pairs:
        required.add(x)
        required.add(y)

    missing = [c for c in sorted(required) if c not in rows[0]]
    if missing:
        raise SystemExit(f"[DHB][FAIL] Missing columns: {missing}")

    stages = sorted({row["rejection_stage"] for row in rows})

    for x, y in pairs:
        fig, ax = plt.subplots(figsize=(7, 5))

        for stage in stages:
            subset = [r for r in rows if r["rejection_stage"] == stage]
            if not subset:
                continue
            xs = [to_float(r[x]) for r in subset]
            ys = [to_float(r[y]) for r in subset]
            ax.scatter(xs, ys, label=stage, alpha=0.75, s=35)

        ax.set_xlabel(x)
        ax.set_ylabel(y)
        ax.set_title(f"Boundary scatter: {x} vs {y}")

        if x in {"tan_beta", "lambda6_input"}:
            ax.set_xscale("log")
        if y in {"tan_beta", "lambda6_input"}:
            ax.set_yscale("log")

        ax.legend(loc="best", fontsize="small")
        fig.tight_layout()

        output = outdir / f"boundary_{safe_name(x)}_vs_{safe_name(y)}.png"
        fig.savefig(output, dpi=160)
        plt.close(fig)
        print(f"[DHB] Wrote plot: {output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
