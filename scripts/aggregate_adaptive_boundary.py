#!/usr/bin/env python3
"""Aggregate and plot the irregular leaves of an adaptive M2 boundary mesh."""

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

from dhb.adaptive_m2_mesh import LEAF_FIELDS, MESH_COLUMNS, _number, _sha256, _theory_ok, _write_rows, write_parquet


AGGREGATE_FIELDS = LEAF_FIELDS + [
    "theory_pass_fraction", "max_abs_g_physical_hphiphi_GeV",
    "min_signed_g_physical_hphiphi_GeV", "max_signed_g_physical_hphiphi_GeV",
    "best_signed_g_physical_hphiphi_GeV", "best_abs_g_physical_hphiphi_GeV",
    "best_X_lambda6_tan_beta", "best_lambda6", "best_Delta_heavy_GeV",
]


def _read(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle)), csv.DictReader


def _mode(rows, name):
    values = [row.get(name, "") for row in rows if row.get(name, "")]
    return min(Counter(values), key=lambda value: (-Counter(values)[value], value)) if values else ""


def aggregate(leaves, rows):
    grouped = defaultdict(list)
    for row in rows: grouped[row.get("mesh_leaf_id", "")].append(row)
    result = []
    for leaf in sorted((leaf for leaf in leaves if leaf["active"]), key=lambda leaf: (leaf["tan_beta"], leaf["leaf_id"])):
        members, valid = grouped[leaf["leaf_id"]], []
        for row in members:
            if _theory_ok(row): valid.append(row)
        finite = [row for row in valid if math.isfinite(_number(row, "g_physical_hphiphi_GeV"))]
        best = max(finite, key=lambda row: abs(_number(row, "g_physical_hphiphi_GeV")), default=None)
        gs = [_number(row, "g_physical_hphiphi_GeV") for row in finite]
        item = dict(leaf)
        item.update({"profile_count": len(members), "valid_count": len(valid),
                     "theory_pass_fraction": len(valid) / len(members) if members else math.nan,
                     "max_abs_g_physical_hphiphi_GeV": max((abs(value) for value in gs), default=math.nan),
                     "min_signed_g_physical_hphiphi_GeV": min(gs, default=math.nan),
                     "max_signed_g_physical_hphiphi_GeV": max(gs, default=math.nan),
                     "best_point_id": best.get("point_id", "") if best else "",
                     "best_signed_g_physical_hphiphi_GeV": _number(best, "g_physical_hphiphi_GeV") if best else math.nan,
                     "best_abs_g_physical_hphiphi_GeV": abs(_number(best, "g_physical_hphiphi_GeV")) if best else math.nan,
                     "best_X_lambda6_tan_beta": _number(best, "X_lambda6_times_tan_beta") if best else math.nan,
                     "best_lambda6": _number(best, "lambda6_from_X") if best else math.nan,
                     "best_Delta_heavy_GeV": _number(best, "Delta_heavy_GeV") if best else math.nan,
                     "dominant_rejection_stage": _mode([row for row in members if not _theory_ok(row)], "rejection_stage"),
                     "dominant_rejection_reason": _mode([row for row in members if not _theory_ok(row)], "rejection_reason")})
        result.append(item)
    return result


def _draw(axis, rows, coupling, vmax, low, high):
    cmap = plt.get_cmap("magma" if coupling else "viridis")
    norm = Normalize(0, vmax if coupling else 1)
    for row in rows:
        state = row["coverage_state"]
        if state in {"seed_incomplete", "new_incomplete", "pending_refinement"}: color = "#bdbdbd"
        elif not row["has_survivor"]: color = "#f4a582"
        else:
            value = row["max_abs_g_physical_hphiphi_GeV"] if coupling else row["theory_pass_fraction"]
            color = cmap(norm(value))
        axis.add_patch(patches.Rectangle((row["mphi_min_GeV"], row["Mbar_min_GeV"]), row["mphi_max_GeV"] - row["mphi_min_GeV"], row["Mbar_max_GeV"] - row["Mbar_min_GeV"], facecolor=color, edgecolor="white", linewidth=.15))
    axis.plot([low, high], [low, high], "k--", lw=1)
    axis.set(xlim=(low, high), ylim=(low, high), aspect="equal", xlabel=r"$m_\phi$ [GeV]", ylabel=r"$\overline{M}$ [GeV]")
    return ScalarMappable(norm=norm, cmap=cmap)


def make_plots(aggregates, output, low, high):
    tbs = sorted({row["tan_beta"] for row in aggregates})
    vmax = max((row["max_abs_g_physical_hphiphi_GeV"] for row in aggregates if math.isfinite(row["max_abs_g_physical_hphiphi_GeV"])), default=1.0)
    outputs = {}
    for coupling, stem, title, label in (
        (False, "figure1_adaptive_pass_fraction", "Adaptive theory-valid profile coverage", "theory-valid proposal fraction"),
        (True, "figure2_adaptive_max_physical_coupling", "Adaptive maximum physical coupling", r"max $|g_{h\phi\phi}|$ [GeV]"),
    ):
        fig, axes = plt.subplots(2, 2, figsize=(10, 9), constrained_layout=True); mesh, used = None, []
        for axis, tb in zip(axes.flat, tbs):
            mesh = _draw(axis, [row for row in aggregates if row["tan_beta"] == tb], coupling, vmax, low, high)
            axis.set_title(r"$\tan\beta=%s$" % format(tb, ".0e"))
            used.append(axis)
        for axis in axes.flat[len(tbs):]: axis.remove()
        fig.suptitle(title)
        fig.legend(handles=[patches.Patch(color="#f4a582", label="tested: no survivor found"), patches.Patch(color="#bdbdbd", label="seed incomplete / budget pending"), plt.Line2D([], [], color="black", linestyle="--", label=r"$\overline{M}=m_\phi$")], loc="lower center", ncol=3)
        if mesh: fig.colorbar(mesh, ax=used, label=label, shrink=.82)
        for suffix, options in (("png", {"dpi": 200}), ("svg", {})):
            path = output / (stem + "." + suffix); fig.savefig(path, bbox_inches="tight", **options); outputs[stem + "_" + suffix] = str(path)
        plt.close(fig)
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="adaptive runner campaign directory")
    parser.add_argument("--output-dir", default="", help="defaults to <run-dir>/aggregate")
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir).resolve(); output = Path(args.output_dir).resolve() if args.output_dir else run_dir / "aggregate"; output.mkdir(parents=True, exist_ok=True)
    state = json.loads((run_dir / "mesh_state.json").read_text()); manifest = json.loads((run_dir / "manifest.json").read_text())
    seed, _ = _read(run_dir / "seed_profiled_points.csv"); new, _ = _read(run_dir / "raw_adaptive_points.csv"); rows = seed + new
    fields = list(dict.fromkeys([field for row in rows for field in row])); _write_rows(output / "raw_points.csv", rows, fields)
    aggregates = aggregate(state["leaves"], rows); _write_rows(output / "aggregate_adaptive_boundary.csv", aggregates, AGGREGATE_FIELDS)
    raw_ok, raw_reason = write_parquet(str(output / "raw_points.csv"), str(output / "raw_points.parquet")); agg_ok, agg_reason = write_parquet(str(output / "aggregate_adaptive_boundary.csv"), str(output / "aggregate_adaptive_boundary.parquet"))
    low, high = float(manifest["mesh"]["min_GeV"]), float(manifest["mesh"]["max_GeV"]); plots = make_plots(aggregates, output, low, high)
    caption = """# Figure captions

These adaptive maps show bounded deterministic profile evidence. Rectangle size encodes evidence-driven mesh resolution, not a confidence interval. Orange means no survivor was found in the tested finite proposals; grey means seed coverage was incomplete or a budget-pending refinement was not evaluated.\n"""
    notes = """# Slide notes

Each coloured rectangle contains a theory-valid canonical point. Figure 1 colours survivor leaves by pass fraction; Figure 2 by their maximum canonical physical coupling magnitude. The diagonal is $\\overline M=m_\\phi$. Different rectangle sizes show where the mesh spent resolution; they are not uncertainty estimates.\n"""
    (output / "captions.md").write_text(caption); (output / "slide_notes.md").write_text(notes)
    out_manifest = {"schema": "dhb.adaptive_m2_mesh.aggregate.v1", "run_manifest_sha256": _sha256(run_dir / "manifest.json"), "inputs": {"seed": _sha256(run_dir / "seed_profiled_points.csv"), "new": _sha256(run_dir / "raw_adaptive_points.csv"), "state": _sha256(run_dir / "mesh_state.json")}, "row_counts": {"raw": len(rows), "active_leaves": len(aggregates), "survivor_leaves": sum(row["has_survivor"] for row in aggregates)}, "parquet": {"raw_written": raw_ok, "raw_reason": raw_reason, "aggregate_written": agg_ok, "aggregate_reason": agg_reason}, "outputs": plots}
    (output / "manifest.json").write_text(json.dumps(out_manifest, indent=2, sort_keys=True) + "\n")
    print("[DHB] adaptive aggregate: raw=%d leaves=%d" % (len(rows), len(aggregates)))
    return 0


if __name__ == "__main__": raise SystemExit(main())
