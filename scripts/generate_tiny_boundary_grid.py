#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from itertools import product
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate a small deterministic boundary grid for evaluate_point."
    )
    p.add_argument("--output", required=True, help="Output CSV path.")
    return p


def fmt_tag(x: float) -> str:
    s = f"{x:.12g}"
    return (
        s.replace("-", "m")
         .replace("+", "")
         .replace(".", "p")
         .replace("e", "e")
    )


def main() -> int:
    args = build_parser().parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Small deterministic grid. Positive lambda6 only for the first MVP.
    mH_values = [130.0, 200.0, 300.0]
    mA_values = [300.0, 500.0]
    tan_beta_values = [10.0, 100.0, 1000.0, 10000.0]
    lambda6_values = [1e-12, 1e-6, 1e-3, 1e-1]
    M_values = [0.0, 100.0, 300.0]

    rows = []
    for mH, mA, tan_beta, lambda6, M in product(
        mH_values,
        mA_values,
        tan_beta_values,
        lambda6_values,
        M_values,
    ):
        point_id = (
            f"tiny"
            f"_mH{fmt_tag(mH)}"
            f"_mA{fmt_tag(mA)}"
            f"_tb{fmt_tag(tan_beta)}"
            f"_l6{fmt_tag(lambda6)}"
            f"_M{fmt_tag(M)}"
        )
        rows.append(
            {
                "point_id": point_id,
                "mH": f"{mH:.17g}",
                "mA": f"{mA:.17g}",
                "tan_beta": f"{tan_beta:.17g}",
                "lambda6": f"{lambda6:.17g}",
                "M": f"{M:.17g}",
            }
        )

    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["point_id", "mH", "mA", "tan_beta", "lambda6", "M"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"[DHB] Wrote tiny grid: {output}")
    print(f"[DHB] Rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
