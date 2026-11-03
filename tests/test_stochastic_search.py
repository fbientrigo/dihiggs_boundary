"""MH/PSO stochastic search on a toy indicator (a 2D disk standing in for theory_ok); the evaluator is never run."""
from pathlib import Path

import numpy as np
import pytest
import yaml

from dhb import stochastic_search as ss

CAMPAIGNS = Path(__file__).resolve().parents[1] / "campaigns"


def _disk(radius=0.35):
    def inside(points):
        return np.linalg.norm(np.asarray(points)[:, :2] - 0.5, axis=1) < radius
    return inside


def _run(sampler, seed, cap, **kwargs):
    inside, points = _disk(), []
    def evaluate(batch, metas):
        points.extend(map(tuple, batch))
        return inside(batch).tolist()
    rng = np.random.default_rng(seed)
    trace = sampler(evaluate, rng, rng.random((16, 2)), cap, **kwargs)
    return np.array(points), trace


def test_mh_lives_in_the_survivor_set_and_is_seed_deterministic():
    points, trace = _run(ss.mh, 1, 3200, eps=0.05)
    assert len(points) == len(trace) == 3200
    state, kept = {}, []  # the chain state after each step (a rejected proposal repeats the current state)
    for p, m in zip(points, trace):
        state[m["chain_id"]] = p if m["accepted"] else state[m["chain_id"]]
        kept += [] if m["burn_in"] else [state[m["chain_id"]]]
    assert _disk()(kept).mean() > 0.8
    assert {m["step_size"] for m in trace if not m["burn_in"]} == {trace[-1]["step_size"]}  # frozen after adaptation
    assert np.array_equal(_run(ss.mh, 1, 200)[0], _run(ss.mh, 1, 200)[0])
    assert not np.array_equal(_run(ss.mh, 1, 200)[0], _run(ss.mh, 2, 200)[0])


def _covering_distance(points):
    """Mean distance from a fine grid of the disk to the nearest evaluated point inside it (lower = better coverage)."""
    grid = np.stack(np.meshgrid(*[np.linspace(0, 1, 60)] * 2), -1).reshape(-1, 2)
    grid, hits = grid[_disk()(grid)], points[_disk()(points)]
    return np.linalg.norm(grid[:, None] - hits[None], axis=2).min(axis=1).mean()


def test_pso_covers_the_survivor_set_better_than_uniform_random():
    cap = 256
    swarm = np.mean([_covering_distance(_run(ss.pso, seed, cap)[0]) for seed in range(3)])
    uniform = np.mean([_covering_distance(np.random.default_rng(seed).random((cap, 2))) for seed in range(3)])
    assert swarm < uniform


def test_cli_rejects_a_physics_override():
    with pytest.raises(SystemExit):
        ss.main(["--config", "c.yaml", "--output-dir", "o", "--tan-beta", "100", "--sampler", "mh", "--seed", "1", "--lambda7", "0.5"])


def test_campaign_matches_survivor_v2_physics_and_ranges():
    stochastic = yaml.safe_load((CAMPAIGNS / "stochastic_12520_v1" / "campaign.yaml").read_text())
    survivor = yaml.safe_load((CAMPAIGNS / "survivor_adaptive_12520_tanbeta_v2" / "campaign.yaml").read_text())
    for key in ("physics", "tan_beta_slices", "runtime", "dihiggs_root", "evaluator"):
        assert stochastic[key] == survivor[key]
    for key in ("batch_size", "X_lambda6_times_tan_beta", "lambda6_hard_envelope", "Delta_heavy_GeV"):
        assert stochastic["profile"][key] == survivor["profile"][key]
    for key in ("min_GeV", "max_GeV", "root_cells"):
        assert stochastic["mesh"][key] == survivor["mesh"][key]


def test_stochastic_leaves_never_seed_survivor_v2(tmp_path):
    """A namespaced mh:/pso: row with a survivor leaf's exact rectangle must not count as that leaf's attempts."""
    from dhb import survivor_adaptive_campaign as sac
    from dhb.adaptive_m2_mesh import _new_leaf
    leaf = _new_leaf(100.0, 0, 0, 0, 130.0, 350.0, 20, source="calibration")
    explored = tmp_path / "explored.csv"
    explored.write_text("lambda7,mh_GeV,tan_beta,mphi_min_GeV,mphi_max_GeV,Mbar_min_GeV,Mbar_max_GeV,leaf_id,n_points,n_valid,best_point_id\n"
                        "0.01,125.2,100.0,%r,%r,%r,%r,mh:%s,64,0,\n" % (leaf["mphi_min_GeV"], leaf["mphi_max_GeV"], leaf["Mbar_min_GeV"],
                                                                    leaf["Mbar_max_GeV"], leaf["leaf_id"]))
    cfg = {"physics": {"lambda7": 0.01, "mh_GeV": 125.2}}
    prior = sac.load_explored(explored, cfg, "c")
    assert len(prior) == 1 and sac._seed(dict(leaf), prior, 64).get("prior_attempts") is None
    assert ss._explored_leaves(explored, cfg, "c", 100.0)[0][4] == leaf["leaf_id"]  # the stochastic prior still reads it
