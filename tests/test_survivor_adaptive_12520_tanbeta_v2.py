import math
from pathlib import Path

import pytest
import yaml

from dhb.survivor_adaptive_campaign import _history_score, _load, _new_root_leaves, slice_batch_quotas


CONFIG = Path(__file__).parents[1] / "campaigns" / "survivor_adaptive_12520_tanbeta_v2" / "campaign.yaml"


def test_v2_slices_and_quotas_are_exact_and_deterministic():
    _, cfg, _, _ = _load(CONFIG)
    expected = [10 ** (2 + 5 * i / 7) for i in range(8)]
    assert all(math.isclose(got, want) for got, want in zip(cfg["tan_beta_slices"], expected))
    quotas = slice_batch_quotas(cfg)
    assert list(quotas.values()) == [782, 782, 781, 781, 781, 781, 781, 781]
    assert sum(quotas.values()) == 6_250
    assert sum(quotas.values()) * cfg["profile"]["batch_size"] == cfg["mesh"]["new_evaluation_cap"] == 100_000


def test_v2_root_and_cap_are_fresh_and_hard_bounded():
    _, cfg, _, _ = _load(CONFIG)
    leaves = _new_root_leaves(cfg)
    assert len(leaves) == 8 * 20 * 20
    assert all(leaf["attempts"] == 0 and leaf["mesh_source"] == "calibration" for leaf in leaves)
    assert all(quota >= 20 * 20 for quota in slice_batch_quotas(cfg).values())


def test_v2_rejects_any_cap_that_is_not_exactly_100k(tmp_path):
    bad = yaml.safe_load(CONFIG.read_text())
    bad["dihiggs_root"] = str(Path(__file__).parents[2] / "dihiggs")
    bad["mesh"]["new_evaluation_cap"] = 99_999
    path = tmp_path / "bad.yaml"; path.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="exact per-slice batch quotas"):
        _load(path)


def test_log_tanbeta_hint_interpolation_is_deterministic_and_geometry_only():
    leaf = _new_root_leaves({**{"tan_beta_slices": [1e3]}, "mesh": {"min_GeV": 130, "max_GeV": 350, "root_cells": 1}})[0]
    history = [(1e2, 130, 350, 130, 350), (1e4, 0, 1, 0, 1)]
    score, provenance = _history_score(leaf, history)
    again, _ = _history_score(leaf, history)
    assert math.isclose(score, .5) and score == again
    assert provenance.startswith("historical_12513_log_interpolation:")
