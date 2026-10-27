"""A v2 run seeded with `lake explored --export` skips what is already explored for its exact regime."""
import csv
import json

from dhb import survivor_adaptive_campaign as sac
from dhb.adaptive_m2_mesh import _mesh_row, _write_rows


def _cfg(tmp_path, lambda7=0.0):
    state = tmp_path / "history.json"; state.write_text(json.dumps({"leaves": []}))
    return {"campaign_id": "seedtest", "schema_version": "dhb.survivor_adaptive_12520_tanbeta.v2", "tan_beta_slices": [1e5],
            "slice_batch_quotas": [8], "historical_hint": {"state": str(state)}, "runtime": {"max_workers": 1},
            "mesh": {"min_GeV": 130.0, "max_GeV": 350.0, "root_cells": 2, "max_depth": 1, "max_cells_per_axis": 4, "new_evaluation_cap": 32},
            "physics": {"mh_GeV": 125.2, "yukawa_type": 1, "sin_beta_minus_alpha": 1.0, "lambda7": lambda7},
            "profile": {"batch_size": 4, "zero_success_max_attempts": 8, "seed": 1,
                        "X_lambda6_times_tan_beta": {"min": 1e-5, "max": 1, "scale": "log"},
                        "lambda6_hard_envelope": {"min": 1e-12, "max": 1e-2}, "Delta_heavy_GeV": {"min": 150, "max": 500}}}


def _run(tmp_path, monkeypatch, name, cfg, explored=None):
    calls = []
    def fake(job):  # valid only in the left root column: deterministic survivors, so refinement happens
        shard, leaf, context = job[:3]; calls.append(context["run_id"])
        row = {**context, **_mesh_row(leaf, "adaptive"), "point_id": context["run_id"], "tan_beta_input": context["tan_beta"], "theory_ok_v1": int(leaf["mphi_min_GeV"] == 130.0),
               "g_physical_hphiphi_GeV": 1.0}
        _write_rows(shard, [row], list(row))
    monkeypatch.setattr(sac, "_run_profile", fake)
    monkeypatch.setattr(sac, "_canonical_api", lambda root: None)
    exe = tmp_path / "exe"; exe.write_text("x")
    config = tmp_path / "c.yaml"; config.write_text("x")
    manifest = sac._run_v2(config, json.loads(json.dumps(cfg)), tmp_path, exe, tmp_path / name, False,
                           {"convention_id": "mh_125p20_active_2026"}, {"checked": []}, None, explored)
    return calls, manifest, json.loads((tmp_path / name / cfg["campaign_id"] / "campaign_state.json").read_text())["leaves"]


def _export(rows_csv, path, convention_id=""):
    """What `lake explored --export` writes: one row per leaf (columns as in lake.py EXPLORED)."""
    leaves = {}
    for row in csv.DictReader(open(rows_csv)):
        leaves.setdefault(row["mesh_leaf_id"], []).append(row)
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["lambda7", "mh_GeV", "tan_beta", "mphi_min_GeV", "mphi_max_GeV", "Mbar_min_GeV", "Mbar_max_GeV", "leaf_id",
                         "n_points", "n_valid", "best_point_id", "convention_id"])
        for leaf_id, rows in leaves.items():
            r = rows[0]; valid = [x for x in rows if x["theory_ok_v1"] == "1"]
            writer.writerow([r["lambda7_input"], r["mh_input_GeV"], r["tan_beta_input"], r["mphi_min_GeV"], r["mphi_max_GeV"], r["Mbar_min_GeV"],
                             r["Mbar_max_GeV"], leaf_id, len(rows), len(valid), valid[0]["point_id"] if valid else "", convention_id])


def test_second_run_skips_explored_leaves_and_other_regimes_are_not_blocked(tmp_path, monkeypatch):
    import dhb.survivor_adaptive_aggregate as agg
    monkeypatch.setattr(agg, "aggregate_run", lambda out: None)
    first, manifest, leaves = _run(tmp_path, monkeypatch, "run1", _cfg(tmp_path))
    assert len(first) == 32 and manifest["status"] == "COMPLETE"
    explored = tmp_path / "explored.csv"
    _export(tmp_path / "run1" / "seedtest" / "raw_fresh_12520_tanbeta_v2_points.csv", explored)

    second, manifest, again = _run(tmp_path, monkeypatch, "run2", _cfg(tmp_path), explored)
    assert second == [] and manifest["status"] == "COMPLETE"  # every leaf already explored: nothing re-run
    assert manifest["explored_seed"]["seeded_attempts"] == 32 and manifest["budget"]["remaining"] == 0
    assert {(l["leaf_id"], l["attempts"], l["successes"], l["decision_state"]) for l in again} == \
           {(l["leaf_id"], l["attempts"], l["successes"], l["decision_state"]) for l in leaves}

    nonzero, _, _ = _run(tmp_path, monkeypatch, "run3", _cfg(tmp_path, lambda7=0.01), explored)
    assert len(nonzero) == 32  # lambda7 = 0 coverage never blocks a lambda7 != 0 run

    other = tmp_path / "other_convention.csv"
    _export(tmp_path / "run1" / "seedtest" / "raw_fresh_12520_tanbeta_v2_points.csv", other, "mh_125p13_historical")
    assert sac.load_explored(other, _cfg(tmp_path), "mh_125p20_active_2026") == {}


def test_partial_prior_leaf_continues_with_fresh_replicates(tmp_path):
    cfg = _cfg(tmp_path); leaf = sac._new_v2_leaf(sac._new_root_leaves(cfg)[0], [])
    sac._seed(leaf, {sac._geometry(leaf): (4, 0, "")}, 8)
    assert leaf["attempts"] == 4 and leaf["decision_state"] == "inconclusive"
    assert {c["profile_replicate"] for _, c in sac._contexts(leaf, cfg, -(-leaf["attempts"] // 4))} == {1}
    sac._update_leaf(leaf, [{"theory_ok_v1": "0"}] * 4, 8)  # 4 prior + 4 fresh = 8 -> tested empty
    assert leaf["attempts"] == 8 and leaf["decision_state"] == "tested_empty_95"
