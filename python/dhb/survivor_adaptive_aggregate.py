"""Rectangular-leaf outputs for the fresh survivor adaptive campaign."""

import csv
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

from .adaptive_m2_mesh import _number, _write_rows, write_parquet
from .profiled_m2_scan import _theory_ok


def _read(path):
    with open(path, newline="", encoding="utf-8") as handle: return list(csv.DictReader(handle))


def _draw(axis, rows, coupling, vmax, low, high):
    cmap, norm = plt.get_cmap("magma" if coupling else "viridis"), Normalize(0, vmax if coupling else 1)
    for row in rows:
        state = row["decision_state"]
        if state in {"inconclusive", "pending_refinement"}: color = "#bdbdbd"
        elif state == "tested_empty_95": color = "#f4a582"
        else: color = cmap(norm(_number(row, "max_abs_g_physical_hphiphi_GeV") if coupling else _number(row, "theory_pass_fraction")))
        axis.add_patch(patches.Rectangle((_number(row, "mphi_min_GeV"), _number(row, "Mbar_min_GeV")), _number(row, "mphi_max_GeV") - _number(row, "mphi_min_GeV"), _number(row, "Mbar_max_GeV") - _number(row, "Mbar_min_GeV"), facecolor=color, edgecolor="white", linewidth=.15))
    axis.plot([low, high], [low, high], "k--", lw=1); axis.set(xlim=(low, high), ylim=(low, high), aspect="equal", xlabel=r"$m_\phi$ [GeV]", ylabel=r"$\overline{M}$ [GeV]")
    return plt.cm.ScalarMappable(norm=norm, cmap=cmap)


def aggregate_run(run_dir):
    run_dir, output = Path(run_dir), Path(run_dir) / "aggregate"; output.mkdir(exist_ok=True)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    state, rows = json.loads((run_dir / "campaign_state.json").read_text()), _read(manifest.get("raw_csv", run_dir / "raw_fresh_12520_points.csv"))
    by_leaf = {}
    for row in rows: by_leaf.setdefault(row["mesh_leaf_id"], []).append(row)
    active = []
    for leaf in state["leaves"]:
        if not leaf["active"]: continue
        item, members = dict(leaf), by_leaf.get(leaf["leaf_id"], [])
        valid = [row for row in members if _theory_ok(row)]
        gs = [_number(row, "g_physical_hphiphi_GeV") for row in valid]
        item.update(theory_pass_fraction=len(valid) / len(members) if members else math.nan, max_abs_g_physical_hphiphi_GeV=max((abs(value) for value in gs if math.isfinite(value)), default=math.nan))
        active.append(item)
    fields = list(dict.fromkeys(key for row in active for key in row)); _write_rows(output / "rectangular_leaf_aggregate.csv", active, fields)
    ok, reason = write_parquet(str(output / "rectangular_leaf_aggregate.csv"), str(output / "rectangular_leaf_aggregate.parquet"))
    low, high = map(float, (manifest["mesh"]["min_GeV"], manifest["mesh"]["max_GeV"]))
    vmax, tbs = max((_number(row, "max_abs_g_physical_hphiphi_GeV") for row in active if math.isfinite(_number(row, "max_abs_g_physical_hphiphi_GeV"))), default=1), sorted({_number(row, "tan_beta") for row in active})
    outputs = {}
    for coupling, stem, title, label in ((False, "adaptive_pass_fraction", "Fresh 125.20 GeV theory-valid proposal fraction", "theory-valid proposal fraction"), (True, "adaptive_max_physical_coupling", "Fresh 125.20 GeV maximum physical coupling", r"max $|g_{h\phi\phi}|$ [GeV]")):
        columns, rows_n = min(4, max(1, len(tbs))), math.ceil(len(tbs) / min(4, max(1, len(tbs))))
        fig, axes = plt.subplots(rows_n, columns, figsize=(5 * columns, 4.5 * rows_n), constrained_layout=True); used, mesh = [], None
        axes = list(getattr(axes, "flat", [axes]))
        for axis, tb in zip(axes, tbs): mesh = _draw(axis, [row for row in active if _number(row, "tan_beta") == tb], coupling, vmax, low, high); axis.set_title(r"$\tan\beta=%s$" % format(tb, ".0e")); used.append(axis)
        for axis in axes[len(tbs):]: axis.remove()
        fig.suptitle(title); fig.legend(handles=[patches.Patch(color="#f4a582", label="tested empty at 95%"), patches.Patch(color="#bdbdbd", label="inconclusive / pending"), plt.Line2D([], [], color="black", linestyle="--", label=r"$\overline{M}=m_\phi$")], loc="lower center", ncol=3)
        if mesh: fig.colorbar(mesh, ax=used, label=label, shrink=.82)
        for suffix, kwargs in (("png", {"dpi": 200}), ("svg", {})):
            path = output / (stem + "." + suffix); fig.savefig(path, bbox_inches="tight", **kwargs); outputs[stem + "_" + suffix] = str(path)
        plt.close(fig)
    (output / "manifest.json").write_text(json.dumps({"schema": "dhb.survivor_adaptive_12520.aggregate.v1", "active_leaves": len(active), "raw_rows": len(rows), "parquet_written": ok, "parquet_skipped_reason": reason, "outputs": outputs, "rectangle_size_note": "Rectangle size is an adaptive resolution indicator, never a confidence interval."}, indent=2, sort_keys=True) + "\n")
    (output / "captions.md").write_text("Rectangle size shows adaptive resolution, never a confidence interval. Grey leaves are inconclusive or pending; orange leaves are tested empty at 95%.\n")
    return active
