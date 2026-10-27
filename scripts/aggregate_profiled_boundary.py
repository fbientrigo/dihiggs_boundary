#!/usr/bin/env python3
"""Aggregate canonical ``dihiggs.point.v2`` profile rows into meeting maps.

This is deliberately a consumer only: it reads the canonical coupling and
theory verdict from CSV rows; it does not construct a 2HDM point or calculate
an observable.  CSV is the required interchange format.  Parquet is written
when the already-optional pyarrow/pandas support is installed.
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError as exc:  # pragma: no cover - environment diagnostic
    raise SystemExit("[DHB][FAIL] matplotlib and numpy are required: %s" % exc)


REQUIRED = {
    "point_id", "mh_input_GeV", "mH_input_GeV", "mA_input_GeV",
    "mHp_input_GeV", "sin_beta_minus_alpha_input", "tan_beta_input",
    "M2_input_GeV2", "lambda6_input", "lambda7_input", "construction_ok",
    "numerical_ok", "theory_ok_v1", "rejection_stage", "rejection_reason",
    "g_physical_hphiphi_GeV", "g_hH2H2_GeV",
}
AGGREGATE_FIELDS = [
    "tan_beta", "m_phi_GeV", "M2_GeV2", "M_plot_GeV", "delta_M2_GeV2",
    "relative_delta_M2", "n_profile_attempts", "n_constructed", "n_theory_ok",
    "theory_pass_fraction", "exists_theory_survivor", "n_exp_ok",
    "max_abs_g_physical_hphiphi_GeV", "min_signed_g_physical_hphiphi_GeV",
    "max_signed_g_physical_hphiphi_GeV", "best_point_id", "best_X_lambda6_tan_beta",
    "best_lambda6", "best_mA_GeV", "best_mHp_GeV", "best_signed_g_physical_hphiphi_GeV",
    "best_abs_g_physical_hphiphi_GeV", "dominant_rejection_stage",
    "dominant_rejection_reason", "coverage_class",
]


def number(row, name):
    try:
        value = float(row.get(name, ""))
    except (TypeError, ValueError):
        return math.nan
    return value if math.isfinite(value) else math.nan


def flag(row, name):
    value = number(row, name)
    return math.isfinite(value) and value != 0.0


def value_text(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return "" if not math.isfinite(value) else format(value, ".17g")
    return "" if value is None else str(value)


def git_state(root):
    def command(*args):
        try:
            return subprocess.check_output(args, cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return ""
    return {"commit": command("git", "rev-parse", "HEAD"), "dirty": bool(command("git", "status", "--porcelain"))}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rows(paths):
    rows, fields = [], []
    for path in paths:
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise SystemExit("[DHB][FAIL] Empty CSV: %s" % path)
            missing = sorted(REQUIRED - set(reader.fieldnames))
            if missing:
                raise SystemExit("[DHB][FAIL] %s misses canonical fields: %s" % (path, ", ".join(missing)))
            for field in reader.fieldnames:
                if field not in fields:
                    fields.append(field)
            rows.extend(reader)
    if not rows:
        raise SystemExit("[DHB][FAIL] No raw point rows supplied")
    return rows, fields


def mode(values):
    values = [value for value in values if value]
    if not values:
        return ""
    counts = Counter(values)
    return min(counts, key=lambda item: (-counts[item], item))


def grid_values(spec):
    low, high, n = float(spec["min"]), float(spec["max"]), int(spec["n"])
    return [low + index * (high - low) / (n - 1) if n > 1 else low for index in range(n)]


def aggregate(rows, expected_attempts, expected_outer_grid=None):
    groups = defaultdict(list)
    for row in rows:
        mphi, m2, tb = (number(row, key) for key in ("mH_input_GeV", "M2_input_GeV2", "tan_beta_input"))
        if not all(math.isfinite(value) for value in (mphi, m2, tb)):
            raise SystemExit("[DHB][FAIL] Non-finite outer coordinate in point %s" % row.get("point_id", ""))
        groups[(tb, mphi, m2)].append(row)
    if expected_outer_grid:
        mphi_values = grid_values(expected_outer_grid["m_phi_GeV"])
        mplot_values = grid_values(expected_outer_grid["M_plot_GeV"])
        for tb in sorted({number(row, "tan_beta_input") for row in rows}):
            for mphi in mphi_values:
                for mplot in mplot_values:
                    groups.setdefault((tb, mphi, mplot * mplot), [])

    result = []
    for (tb, mphi, m2), members in sorted(groups.items()):
        valid = [row for row in members if flag(row, "theory_ok_v1")]
        valid_with_g = [row for row in valid if math.isfinite(number(row, "g_physical_hphiphi_GeV"))]
        if len(valid_with_g) != len(valid):
            raise SystemExit("[DHB][FAIL] theory-valid canonical row lacks g_physical_hphiphi_GeV at outer cell tb=%s mphi=%s M2=%s" % (tb, mphi, m2))
        constructed = sum(flag(row, "construction_ok") for row in members)
        gs = [number(row, "g_physical_hphiphi_GeV") for row in valid]
        gs = [value for value in gs if math.isfinite(value)]
        best = max(valid_with_g, key=lambda row: abs(number(row, "g_physical_hphiphi_GeV")), default=None)
        n_attempts = len(members)
        complete = n_attempts == expected_attempts
        coverage = "survivor_region" if valid else ("no_survivor_found" if complete else "insufficient_coverage")
        exp_columns = ("experiment_ok", "exp_ok")
        has_experiment = any(field in row for row in members for field in exp_columns)
        n_exp_ok = sum(any(flag(row, field) for field in exp_columns if field in row) for row in members) if has_experiment else math.nan
        rejected = [row for row in members if not flag(row, "theory_ok_v1")]
        row = {
            "tan_beta": tb, "m_phi_GeV": mphi, "M2_GeV2": m2,
            "M_plot_GeV": math.sqrt(m2) if m2 >= 0 else math.nan,
            "delta_M2_GeV2": m2 - mphi * mphi,
            "relative_delta_M2": (m2 - mphi * mphi) / (mphi * mphi),
            "n_profile_attempts": n_attempts, "n_constructed": constructed,
            "n_theory_ok": len(valid), "theory_pass_fraction": len(valid) / n_attempts if n_attempts else math.nan,
            "exists_theory_survivor": bool(valid), "n_exp_ok": n_exp_ok,
            "max_abs_g_physical_hphiphi_GeV": max((abs(value) for value in gs), default=math.nan),
            "min_signed_g_physical_hphiphi_GeV": min(gs, default=math.nan),
            "max_signed_g_physical_hphiphi_GeV": max(gs, default=math.nan),
            "best_point_id": best.get("point_id", "") if best else "",
            "best_X_lambda6_tan_beta": number(best, "lambda6_input") * tb if best else math.nan,
            "best_lambda6": number(best, "lambda6_input") if best else math.nan,
            "best_mA_GeV": number(best, "mA_input_GeV") if best else math.nan,
            "best_mHp_GeV": number(best, "mHp_input_GeV") if best else math.nan,
            "best_signed_g_physical_hphiphi_GeV": number(best, "g_physical_hphiphi_GeV") if best else math.nan,
            "best_abs_g_physical_hphiphi_GeV": abs(number(best, "g_physical_hphiphi_GeV")) if best else math.nan,
            "dominant_rejection_stage": mode([item.get("rejection_stage", "") for item in rejected]),
            "dominant_rejection_reason": mode([item.get("rejection_reason", "") for item in rejected]),
            "coverage_class": coverage,
        }
        result.append(row)
    return result


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: value_text(row.get(field, "")) for field in fields})


def write_parquet(csv_path, parquet_path):
    try:
        import pyarrow.csv as pv
        import pyarrow.parquet as pq
        pq.write_table(pv.read_csv(csv_path), parquet_path)
        return True, ""
    except ImportError:
        pass
    try:
        import pandas as pd
        pd.read_csv(csv_path).to_parquet(parquet_path, index=False)
        return True, ""
    except ImportError:
        return False, "pyarrow and pandas parquet support unavailable"
    except Exception as exc:
        return False, "parquet write failed: %s" % exc


def centers_to_edges(centers):
    centers = np.asarray(sorted(set(centers)), dtype=float)
    if len(centers) == 1:
        pad = max(abs(centers[0]) * 0.02, 1.0)
        return np.array([centers[0] - pad, centers[0] + pad])
    middle = (centers[1:] + centers[:-1]) / 2
    return np.r_[centers[0] - (middle[0] - centers[0]), middle, centers[-1] + (centers[-1] - middle[-1])]


def plot_grid(aggregates, tb, expected_attempts, coupling, coupling_vmax, axis):
    rows = [row for row in aggregates if row["tan_beta"] == tb]
    xs, ys = sorted({row["m_phi_GeV"] for row in rows}), sorted({row["M_plot_GeV"] for row in rows})
    lookup = {(row["m_phi_GeV"], row["M_plot_GeV"]): row for row in rows}
    xedges, yedges = centers_to_edges(xs), centers_to_edges(ys)
    state = np.zeros((len(ys), len(xs)))  # 0 incomplete, 1 complete/no survivor, 2 survivor
    value = np.full_like(state, np.nan, dtype=float)
    for yi, y in enumerate(ys):
        for xi, x in enumerate(xs):
            row = lookup.get((x, y))
            if row is None or row["n_profile_attempts"] != expected_attempts:
                continue
            if not row["exists_theory_survivor"]:
                state[yi, xi] = 1
            else:
                state[yi, xi] = 2
                value[yi, xi] = row["max_abs_g_physical_hphiphi_GeV"] if coupling else row["theory_pass_fraction"]
    axis.pcolormesh(xedges, yedges, state, cmap=matplotlib.colors.ListedColormap(["#d9d9d9", "#f4a582", "#ffffff"]), vmin=0, vmax=2, shading="flat")
    shown = np.ma.masked_invalid(value)
    mesh = axis.pcolormesh(xedges, yedges, shown, cmap="magma" if coupling else "viridis", vmin=0, vmax=coupling_vmax if coupling else 1, shading="flat")
    axis.plot([min(xedges), max(xedges)], [min(xedges), max(xedges)], "k--", lw=1, label=r"$\overline{M}=m_\phi$")
    axis.set_title(r"$\tan\beta=%s$" % format(tb, ".0e"))
    axis.set_xlabel(r"$m_\phi$ [GeV]")
    axis.set_ylabel(r"$\overline{M}=\sqrt{M^2}$ [GeV]")
    axis.set_aspect("equal", adjustable="box")
    return mesh


def make_plots(aggregates, output_dir, expected_attempts):
    tbs = sorted({row["tan_beta"] for row in aggregates})
    coupling_vmax = max((row["max_abs_g_physical_hphiphi_GeV"] for row in aggregates if math.isfinite(row["max_abs_g_physical_hphiphi_GeV"])), default=1.0)
    ncols, nrows = 2, max(1, math.ceil(len(tbs) / 2))
    shared = [
        mpatches.Patch(color="#d9d9d9", label="untested / incomplete coverage"),
        mpatches.Patch(color="#f4a582", label="tested: no theory survivor found"),
        plt.Line2D([], [], color="black", linestyle="--", label=r"$\overline{M}=m_\phi$"),
    ]
    outputs = {}
    for coupling, stem, title, label in (
        (False, "figure1_boundary_rigidity", r"Theory-valid profile coverage: rigidity of $M^2\simeq m_\phi^2$", "theory-valid proposal fraction"),
        (True, "figure2_max_physical_coupling", r"Largest physical $|g_{h\phi\phi}|$ in theory-valid cells", r"max $|g_{h\phi\phi}|$ [GeV]"),
    ):
        fig, axes = plt.subplots(nrows, ncols, figsize=(10, 4.8 * nrows), squeeze=False, constrained_layout=True)
        mesh = None
        for axis, tb in zip(axes.flat, tbs):
            mesh = plot_grid(aggregates, tb, expected_attempts, coupling, coupling_vmax, axis)
        for axis in list(axes.flat)[len(tbs):]:
            axis.remove()
        fig.suptitle(title)
        fig.legend(handles=shared, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.065))
        if mesh is not None:
            fig.colorbar(mesh, ax=[axis for axis in axes.flat if axis in fig.axes], label=label, shrink=0.88)
        for suffix, kwargs in (("png", {"dpi": 200}), ("svg", {})):
            path = output_dir / (stem + "." + suffix)
            fig.savefig(path, bbox_inches="tight", **kwargs)
            outputs[stem + "_" + suffix] = str(path)
        plt.close(fig)
    return outputs


def summary_rows(aggregates):
    fields = ["tan_beta", "maximum_abs_relative_delta_M2", "point_id", "m_phi_GeV", "M_plot_GeV", "X_lambda6_tan_beta", "lambda6", "mA_GeV", "mHp_GeV", "signed_g_physical_hphiphi_GeV", "abs_g_physical_hphiphi_GeV"]
    result = []
    for tb in sorted({row["tan_beta"] for row in aggregates}):
        candidates = [row for row in aggregates if row["tan_beta"] == tb and row["exists_theory_survivor"]]
        if not candidates:
            result.append({"tan_beta": tb})
            continue
        best = max(candidates, key=lambda row: abs(row["relative_delta_M2"]))
        result.append({
            "tan_beta": tb, "maximum_abs_relative_delta_M2": abs(best["relative_delta_M2"]),
            "point_id": best["best_point_id"], "m_phi_GeV": best["m_phi_GeV"], "M_plot_GeV": best["M_plot_GeV"],
            "X_lambda6_tan_beta": best["best_X_lambda6_tan_beta"], "lambda6": best["best_lambda6"],
            "mA_GeV": best["best_mA_GeV"], "mHp_GeV": best["best_mHp_GeV"],
            "signed_g_physical_hphiphi_GeV": best["best_signed_g_physical_hphiphi_GeV"],
            "abs_g_physical_hphiphi_GeV": best["best_abs_g_physical_hphiphi_GeV"],
        })
    return result, fields


def notes(aggregates, expected_attempts):
    total, survivors = len(aggregates), sum(row["exists_theory_survivor"] for row in aggregates)
    return """# Slide notes

## Figure 1 — How rigid is M² ≈ m_phi²?

Question: At fixed tan(beta), which profiled outer cells contain at least one theory-valid canonical 2HDM point away from the diagonal?

Result: %d of %d outer cells have a theory-valid survivor in this bounded deterministic profile scan.

Caveat: A grey cell has fewer than %d attempts and an orange cell means no survivor was found in this finite proposal set; neither is an exclusion claim.

## Figure 2 — Largest physical h-phi-phi coupling reachable in the valid region

Question: What is the largest canonical signed physical-coupling magnitude found among theory-valid profiles at each outer cell?

Result: Colour shows the maximum of abs(g_physical_hphiphi_GeV) over theory-valid canonical rows only.

Caveat: The map is a finite sampled profile surface, not a continuous optimum; sign remains in aggregate_profiled_boundary.csv and the summary table.
""" % (survivors, total, expected_attempts)


def captions(expected_attempts):
    return """# Figure captions

**Figure 1 — How rigid is M² ≈ m_phi²?** Canonical theory-valid existence and profile pass fraction in the (m_phi, M-bar) plane, with M-bar = sqrt(M²) derived only for plotting. Grey denotes untested/incomplete coverage; orange denotes a fully tested cell with no theory survivor found among %d deterministic nuisance proposals.

**Figure 2 — Largest physical h-phi-phi coupling reachable in the valid region.** For each theory-valid outer cell, colour is the largest canonical abs(g_physical_hphiphi_GeV) among its profile survivors; the colour scale is shared across tan(beta) panels. Empty/failed coverage uses the same grey/orange encoding as Figure 1.
""" % expected_attempts


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="canonical dihiggs.point.v2 CSV; repeat for shards")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--expected-attempts", type=int, required=True, help="16 for full production, 4 for smoke")
    parser.add_argument("--run-manifest", default="", help="optional scan manifest copied by reference into this manifest")
    args = parser.parse_args(argv)
    if args.expected_attempts < 1:
        raise SystemExit("[DHB][FAIL] --expected-attempts must be positive")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = [str(Path(path).resolve()) for path in args.input]
    rows, raw_fields = load_rows(inputs)
    run_manifest = {}
    if args.run_manifest:
        with open(args.run_manifest, encoding="utf-8") as handle:
            run_manifest = json.load(handle)
    outer_grid = run_manifest.get("outer_grid")
    if outer_grid and not {"m_phi_GeV", "M_plot_GeV"} <= set(outer_grid):
        raise SystemExit("[DHB][FAIL] scan manifest outer_grid lacks m_phi_GeV/M_plot_GeV")
    aggregates = aggregate(rows, args.expected_attempts, outer_grid)
    raw_csv, aggregate_csv = output_dir / "raw_points.csv", output_dir / "aggregate_profiled_boundary.csv"
    write_csv(raw_csv, rows, raw_fields)
    write_csv(aggregate_csv, aggregates, AGGREGATE_FIELDS)
    raw_parquet_ok, raw_parquet_reason = write_parquet(raw_csv, output_dir / "raw_points.parquet")
    aggregate_parquet_ok, aggregate_parquet_reason = write_parquet(aggregate_csv, output_dir / "aggregate_profiled_boundary.parquet")
    summary, summary_fields = summary_rows(aggregates)
    write_csv(output_dir / "boundary_summary.csv", summary, summary_fields)
    plot_outputs = make_plots(aggregates, output_dir, args.expected_attempts)
    metadata = {
        "schema": "dihiggs_boundary.profiled_boundary_aggregate.v1",
        "source_schema_required": "dihiggs.point.v2", "x_variable": "m_phi_GeV = mH_input_GeV",
        "y_variable": "M_plot_GeV = sqrt(M2_input_GeV2)",
        "M2_authoritative_field": "M2_input_GeV2", "hidden_variables": ["mA_input_GeV=mHp_input_GeV", "lambda6_input", "X=lambda6_input*tan_beta_input"],
        "aggregation_method": "existence/pass fraction and max abs canonical g_physical_hphiphi_GeV among theory_ok_v1 rows",
        "constraints_applied": "canonical theory_ok_v1 only; experiment status retained separately when present",
        "expected_profile_attempts": args.expected_attempts, "coverage_rule": "complete only when n_profile_attempts equals expected_profile_attempts",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "plot_outputs": plot_outputs,
    }
    (output_dir / "plotting_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "slide_notes.md").write_text(notes(aggregates, args.expected_attempts), encoding="utf-8")
    (output_dir / "captions.md").write_text(captions(args.expected_attempts), encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    manifest = {
        "stage": "profiled_boundary_aggregation", "aggregate_schema": metadata["schema"],
        "inputs": [{"path": path, "sha256": sha256(path)} for path in inputs], "scan_manifest": run_manifest,
        "row_counts": {"raw": len(rows), "aggregate_outer_cells": len(aggregates), "theory_survivor_cells": sum(row["exists_theory_survivor"] for row in aggregates)},
        "expected_profile_attempts": args.expected_attempts,
        "parquet": {"raw_written": raw_parquet_ok, "raw_reason": raw_parquet_reason, "aggregate_written": aggregate_parquet_ok, "aggregate_reason": aggregate_parquet_reason},
        "outputs": {"raw_csv": str(raw_csv), "aggregate_csv": str(aggregate_csv), "summary_csv": str(output_dir / "boundary_summary.csv"), "captions": str(output_dir / "captions.md"), "slide_notes": str(output_dir / "slide_notes.md"), **plot_outputs},
        "boundary_git": git_state(root), "created_at_utc": metadata["created_at_utc"],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("[DHB] aggregated raw=%d cells=%d survivor_cells=%d" % (len(rows), len(aggregates), manifest["row_counts"]["theory_survivor_cells"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
