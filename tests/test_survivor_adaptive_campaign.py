import math
import csv
import json
from pathlib import Path

from dhb.survivor_adaptive_campaign import (
    _contexts, _halo_ids, _new_root_leaves, _update_leaf, priority,
    wilson95, zero_event_upper_95,
)
from dhb.survivor_adaptive_aggregate import aggregate_run
from dhb.survivor_adaptive_campaign import _load


def _cfg():
    return {
        "tan_beta_slices": [100.0, 1e4, 1e5, 1e7],
        "mesh": {"min_GeV": 130, "max_GeV": 350, "root_cells": 20},
        "physics": {"mh_GeV": 125.20, "yukawa_type": 1, "sin_beta_minus_alpha": 1, "lambda7": 0},
        "campaign_id": "fresh_12520",
        "profile": {"batch_size": 16, "zero_success_max_attempts": 64, "seed": 9,
                    "X_lambda6_times_tan_beta": {"min": 1e-5, "max": 1, "scale": "log"},
                    "lambda6_hard_envelope": {"min": 1e-12, "max": 1e-2},
                    "Delta_heavy_GeV": {"min": 150, "max": 500, "scale": "linear"}},
    }


def test_fresh_root_is_exactly_25600_12520_attempts_without_historical_rows():
    cfg, leaves = _cfg(), _new_root_leaves(_cfg())
    assert len(leaves) == 20 * 20 * 4
    assert sum(len(list(_contexts(leaf, cfg, 0))) for leaf in leaves) == 25_600
    assert {item[1]["mh_input_GeV"] for item in _contexts(leaves[0], cfg, 0)} == {125.20}
    assert {leaf["mesh_source"] for leaf in leaves} == {"calibration"}


def test_historical_hint_is_a_tie_breaker_not_a_survivor():
    leaf = _new_root_leaves(_cfg())[0]
    assert priority(leaf, set(), True) == (2, "historical_12513_hint")
    _update_leaf(leaf, [], 64)
    assert not leaf["has_survivor"]
    assert leaf["decision_state"] == "inconclusive"


def test_production_config_uses_the_historical_archive_only():
    config = Path(__file__).parents[1] / "configs" / "survivor_adaptive_12520_v1.yaml"
    _, cfg, _, _ = _load(config)
    assert "/atlas_dihiggs_archive/" in cfg["historical_hint"]["manifest"]
    assert json.loads(Path(cfg["historical_hint"]["archive_manifest"]).read_text())["convention"]["status"] == "historical_only"


def test_wilson_and_exact_zero_event_bounds():
    low, high = wilson95(0, 16)
    assert 0 <= low <= high < .2
    assert math.isclose(zero_event_upper_95(16), .17074972298248092)
    assert zero_event_upper_95(64) < .05
    low, high = wilson95(3, 16)
    assert low < 3 / 16 < high


def test_halo_and_replicates_are_deterministic_and_independent():
    cfg, leaves = _cfg(), _new_root_leaves(_cfg())
    hit = leaves[0]; hit["has_survivor"] = True
    halo = _halo_ids(leaves, 0)
    assert len(halo) == 4
    first, again, second = list(_contexts(hit, cfg, 0)), list(_contexts(hit, cfg, 0)), list(_contexts(hit, cfg, 1))
    assert first == again
    assert first[0][1]["profile_seed"] != second[0][1]["profile_seed"]
    assert {item[1]["profile_replicate"] for item in second} == {1}


def test_aggregate_renders_inconclusive_and_pending_leaves(tmp_path):
    leaves = _new_root_leaves(_cfg())[:4]
    for leaf, state in zip(leaves, ("survivor", "tested_empty_95", "inconclusive", "pending_refinement")):
        leaf["decision_state"] = leaf["coverage_state"] = state
    (tmp_path / "campaign_state.json").write_text(json.dumps({"leaves": leaves}))
    (tmp_path / "manifest.json").write_text(json.dumps({"mesh": {"min_GeV": 130, "max_GeV": 350}}))
    with (tmp_path / "raw_fresh_12520_points.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["mesh_leaf_id", "theory_ok_v1", "g_physical_hphiphi_GeV"])
        writer.writeheader(); writer.writerow({"mesh_leaf_id": leaves[0]["leaf_id"], "theory_ok_v1": "1", "g_physical_hphiphi_GeV": "12.5"})
    aggregate_run(tmp_path)
    assert (tmp_path / "aggregate" / "adaptive_pass_fraction.png").exists()
    assert (tmp_path / "aggregate" / "adaptive_max_physical_coupling.svg").exists()
