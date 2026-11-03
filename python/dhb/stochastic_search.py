"""Stochastic boundary search over one tan(beta) slice: `--sampler mh` (Metropolis-Hastings) or `--sampler pso`.

Same canonical evaluator path, physics, mesh bounds and profile ranges as survivor_v2 (dhb.survivor_adaptive_campaign);
only the choice of points differs. Every evaluation is a fresh continuous point, so a repeated action never returns 0 rows.

Search space, a unit cube (tan_beta fixed by the action): mphi and Mbar in [mesh.min_GeV, mesh.max_GeV]; X = lambda6 *
tan_beta (log, the survivor_v2 range clipped to lambda6_hard_envelope * tan_beta, as `_contexts` does); Delta_heavy_GeV.

MH: C chains of random-walk Metropolis-Hastings, symmetric Gaussian proposal with reflecting bounds, target
pi(x) ∝ eps + 1[theory_ok(x)]. That target is an indicator: the accepted states are draws from the (eps-smoothed) survivor
set, NOT a physics posterior (no likelihood, no parameter prior). The step size adapts toward acceptance 0.234 during the
first 20% of steps and is then frozen; those rows carry burn_in = 1.
PSO: w = 0.7, c1 = c2 = 1.5, |v| <= 0.2 per axis; fitness theory_ok(x) * d_min(x), d_min the unit-cube distance to the
nearest already-evaluated point (this run's, plus explored leaf centers in (mphi, Mbar), where survivor_v2 evaluates):
a space-filling search over survivors that never rewards a repeat.

`--explored` (output of `lake explored --export`) gives p = (n_valid+1)/(n_points+2) of the finest regime-matched leaf
containing (mphi, Mbar), 0.5 outside known leaves. It only places chain starts and particles; it is never a verdict.

Lake leaf namespace: a row's mesh_leaf_id is "<sampler>:<id of the finest leaf containing it>" (the mesh root cell when no
explored leaf does), with that leaf's rectangle; mesh_parent_id is the plain leaf id. `lake explored` lists these as their
own leaves, and survivor_v2's load_explored keys on the leaf id, so a stochastic row never makes survivor_v2 skip a leaf.
"""

import argparse
import hashlib
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import yaml

from .adaptive_m2_mesh import (
    CANONICAL_COLUMNS, MESH_COLUMNS, _canonical_api, _git, _new_leaf, _now, _run_profile, _tag, _write_json,
    _write_rows, root_index, write_parquet,
)
from .profiled_m2_scan import _mass_convention, _theory_ok
from .survivor_adaptive_campaign import _sha256, load_explored

SCHEMA = "dhb.stochastic_12520.v1"
SAMPLER_COLUMNS = ["sampler", "sampler_seed", "eval_index", "chain_id", "step", "accepted", "log_target", "step_size",
                   "burn_in", "particle_id", "iteration", "fitness", "velocity_norm"]
PROFILE_COLUMNS = ["profile_index", "profile_replicate", "profile_seed", "X_lambda6_times_tan_beta", "lambda6_from_X",
                   "lambda6_clipped", "Delta_heavy_GeV", "mA_minus_mphi_GeV", "profile_status"]


def _reflect(u):
    u = np.abs(u) % 2.0
    return np.where(u > 1.0, 2.0 - u, u)


def _starts(rng, k, dim, prior, oversample=64):
    """k points ∝ p(x): importance resampling of uniform candidates (ponytail: approximate; exact leaf-area sampling if needed)."""
    candidates = rng.random((oversample * k, dim))
    weights = np.array([prior(u) for u in candidates])
    return candidates[rng.choice(len(candidates), size=k, replace=False, p=weights / weights.sum())]


def mh(evaluate, rng, starts, cap, eps=0.05, step0=0.1, target=0.234, adapt_fraction=0.2):
    """Random-walk MH chains; evaluate(points, metas) -> theory_ok list. Returns one meta per evaluation, in order."""
    chains, dim = min(len(starts), cap), starts.shape[1]
    if not chains:
        return []
    x, s = starts[:chains].copy(), step0
    steps = math.ceil(cap / chains)
    adapt = int(adapt_fraction * steps)
    trace = [{"chain_id": c, "step": 0, "step_size": s} for c in range(chains)]
    logp = np.log(eps + np.asarray(evaluate(x, trace), dtype=float))
    for c, meta in enumerate(trace):  # step 0 evaluates the starts: the chain is there by construction
        meta.update(accepted=1, log_target=float(logp[c]), burn_in=int(adapt > 0))
    for step in range(1, steps):
        n = min(chains, cap - len(trace))
        proposal = _reflect(x[:n] + s * rng.standard_normal((n, dim)))
        metas = [{"chain_id": c, "step": step, "step_size": s} for c in range(n)]
        new = np.log(eps + np.asarray(evaluate(proposal, metas), dtype=float))
        accept = np.log(rng.random(n)) < new - logp[:n]
        x[:n][accept], logp[:n][accept] = proposal[accept], new[accept]
        burn = step <= adapt
        for c, meta in enumerate(metas):
            meta.update(accepted=int(accept[c]), log_target=float(new[c]), burn_in=int(burn))
        if burn:
            s = float(np.clip(s * math.exp(accept.mean() - target), 1e-3, 1.0))
        trace += metas
    return trace


def _dmin(points, anchors, p, skip_self=False):
    """Unit-cube distance from p to the nearest evaluated point (4D) or anchor (2D: mphi, Mbar), capped at the diagonal."""
    d = [math.sqrt(len(p))]
    if len(points):
        dist = np.linalg.norm(points - p, axis=1)
        dist = dist[dist > 0] if skip_self else dist
        d += [dist.min()] if len(dist) else []
    if len(anchors):
        d.append(np.linalg.norm(anchors - p[:2], axis=1).min())
    return float(min(d))


def pso(evaluate, rng, starts, cap, anchors=np.empty((0, 2)), w=0.7, c1=1.5, c2=1.5, vmax=0.2):
    """Particle swarm on theory_ok * d_min. Bests are re-scored each iteration (d_min shrinks as the swarm fills in)."""
    size, dim = min(len(starts), cap), starts.shape[1]
    if not size:
        return []
    x, v = starts[:size].copy(), rng.uniform(-vmax / 2, vmax / 2, (size, dim))
    seen, trace, iteration = np.empty((cap, dim)), [], 0
    best, best_ok = x.copy(), np.zeros(size)
    while len(trace) < cap:
        n = min(size, cap - len(trace))
        metas = [{"particle_id": p, "iteration": iteration, "velocity_norm": float(np.linalg.norm(v[p]))} for p in range(n)]
        ok = np.asarray(evaluate(x[:n], metas), dtype=float)
        for p, meta in enumerate(metas):
            meta["fitness"] = ok[p] * _dmin(seen[:len(trace)], anchors, x[p])
            seen[len(trace)] = x[p]
            trace.append(meta)
        current = seen[:len(trace)]
        best_fit = np.array([best_ok[p] * _dmin(current, anchors, best[p], skip_self=True) for p in range(size)])
        for p in range(n):
            fit = ok[p] * _dmin(current, anchors, x[p], skip_self=True)
            if fit > best_fit[p] or iteration == 0:
                best[p], best_ok[p], best_fit[p] = x[p], ok[p], fit
        g = best[int(best_fit.argmax())]
        r1, r2 = rng.random((size, dim)), rng.random((size, dim))
        v = np.clip(w * v + c1 * r1 * (best - x) + c2 * r2 * (g - x), -vmax, vmax)
        moved = x + v
        v = np.where((moved < 0) | (moved > 1), -v, v)
        x, iteration = _reflect(moved), iteration + 1
    return trace


def _space(cfg, tb):
    """(low, high, log) per unit-cube axis: mphi, Mbar, X = lambda6 * tan_beta, Delta_heavy_GeV."""
    mesh, profile = cfg["mesh"], cfg["profile"]
    envelope, spec, delta = profile["lambda6_hard_envelope"], profile["X_lambda6_times_tan_beta"], profile["Delta_heavy_GeV"]
    x_low, x_high = max(float(spec["min"]), float(envelope["min"]) * tb), min(float(spec["max"]), float(envelope["max"]) * tb)
    axis = lambda lo, hi, s: (math.log10(lo), math.log10(hi), True) if s.get("scale") == "log" else (float(lo), float(hi), False)
    mass = (float(mesh["min_GeV"]), float(mesh["max_GeV"]), False)
    return [mass, mass, axis(x_low, x_high, spec), axis(float(delta["min"]), float(delta["max"]), delta)]


def _physical(u, space):
    return [10 ** (lo + (hi - lo) * v) if log else lo + (hi - lo) * v for v, (lo, hi, log) in zip(u, space)]


def _explored_leaves(explored, cfg, convention_id, tb):
    """Regime-matched explored leaves of this slice, finest first: (x0, x1, y0, y1, plain leaf id, n_points, n_valid)."""
    prior = load_explored(explored, cfg, convention_id) if explored else {}
    leaves = [(x1 - x0, -n, x0, x1, y0, y1, leaf_id.split(":")[-1], n, k)
              for (leaf_id, ltb, x0, x1, y0, y1), (n, k, _) in prior.items() if math.isclose(ltb, tb, rel_tol=1e-9)]
    return [leaf[2:] for leaf in sorted(leaves)]


def _containing(leaves, mphi, mbar):
    return next((leaf for leaf in leaves if leaf[0] <= mphi <= leaf[1] and leaf[2] <= mbar <= leaf[3]), None)


def _leaf(leaves, mphi, mbar, cfg, tb, sampler):
    mesh = cfg["mesh"]
    hit = _containing(leaves, mphi, mbar)
    if hit is None:
        low, high, n = float(mesh["min_GeV"]), float(mesh["max_GeV"]), int(mesh["root_cells"])
        leaf = _new_leaf(tb, 0, root_index(mphi, low, high, n), root_index(mbar, low, high, n), low, high, n, source=sampler)
    else:
        x0, x1, y0, y1, plain = hit[:5]
        leaf = {"leaf_id": plain, "depth": plain.count("/"), "mphi_min_GeV": x0, "mphi_max_GeV": x1, "Mbar_min_GeV": y0,
                "Mbar_max_GeV": y1, "mphi_center_GeV": (x0 + x1) / 2, "Mbar_center_GeV": (y0 + y1) / 2}
    return {**leaf, "parent_id": leaf["leaf_id"], "leaf_id": "%s:%s" % (sampler, leaf["leaf_id"])}


def _context(cfg, tb, sampler, seed, index, point, leaf):
    mphi, mbar, x, delta = point
    physics, envelope = cfg["physics"], cfg["profile"]["lambda6_hard_envelope"]
    unclipped = x / tb
    lam6 = min(max(unclipped, float(envelope["min"])), float(envelope["max"]))
    return {"campaign_id": cfg["campaign_id"], "run_id": "%s_tb%s_s%d_e%05d" % (sampler, _tag(tb), seed, index),
            "profile_index": index, "profile_replicate": 0, "profile_seed": "%s:%d" % (sampler, seed), "tan_beta": tb,
            "yukawa_type": int(physics["yukawa_type"]), "mh_input_GeV": float(physics["mh_GeV"]),
            "mH_input_GeV": mphi, "M2_input_GeV2": mbar ** 2, "mA_input_GeV": mphi + delta, "mHp_input_GeV": mphi + delta,
            "sin_beta_minus_alpha_input": float(physics["sin_beta_minus_alpha"]), "lambda7_input": float(physics["lambda7"]),
            "X_lambda6_times_tan_beta": x, "lambda6_from_X": lam6, "lambda6_clipped": int(lam6 != unclipped),
            "Delta_heavy_GeV": delta, "mA_minus_mphi_GeV": delta, "mesh_leaf_id": leaf["leaf_id"],
            "mesh_parent_id": leaf["parent_id"], "mesh_depth": leaf["depth"], "mesh_source": sampler}


def run(config_path, output_dir, tan_beta, sampler, seed, explored=None, smoke=False):
    started, config_path = time.monotonic(), Path(config_path).resolve()
    cfg = yaml.safe_load(config_path.read_text())
    if not isinstance(cfg, dict) or cfg.get("schema_version") != SCHEMA:
        raise ValueError("unsupported stochastic search config")
    root = (config_path.parent / cfg["dihiggs_root"]).resolve()
    executable = (root / cfg["evaluator"]).resolve()
    if not executable.is_file():
        raise ValueError("canonical evaluator missing: %s" % executable)
    tb = float(tan_beta)
    if tb not in map(float, cfg["tan_beta_slices"]):
        raise ValueError("requested tan(beta) is not in config")
    if smoke:
        cfg["stochastic"]["evaluation_cap"], cfg["campaign_id"] = 64, cfg["campaign_id"] + "_smoke"
    cap, eps, batch = int(cfg["stochastic"]["evaluation_cap"]), float(cfg["stochastic"]["epsilon"]), int(cfg["profile"]["batch_size"])
    # fail before any row if the canonical evaluator disagrees with the claimed active mass convention
    convention = _mass_convention(root, float(cfg["physics"]["mh_GeV"]))
    leaves = _explored_leaves(explored, cfg, convention["convention_id"], tb)
    space, api, rng = _space(cfg, tb), _canonical_api(root), np.random.default_rng(seed)
    effective = hashlib.sha256(json.dumps([cfg, sampler, seed, _sha256(explored) if explored else None], sort_keys=True).encode()).hexdigest()
    out = Path(output_dir).resolve() / cfg["campaign_id"]
    shards = out / ("tanbeta_" + _tag(tb)) / "raw_shards" / ("%s_%s" % (sampler, effective[:12]))  # a cached shard is only ever this run's
    shards.mkdir(parents=True, exist_ok=True)
    records = []

    def evaluate(points, metas):
        jobs = []
        for u, meta in zip(points, metas):
            index, point = len(records) + len(jobs), _physical(u, space)
            leaf = _leaf(leaves, point[0], point[1], cfg, tb, sampler)
            meta.update(sampler=sampler, sampler_seed=seed, eval_index=index)
            jobs.append((shards / ("eval_%05d.csv" % index), leaf, _context(cfg, tb, sampler, seed, index, point, leaf), cfg, executable, root, api))
        with ThreadPoolExecutor(max_workers=int(cfg["runtime"]["max_workers"])) as pool:
            rows = list(pool.map(_run_profile, jobs))
        records.extend(zip(rows, metas))
        print("\r[DHB] stochastic %s: %d/%d rows, %.1fs" % (sampler, len(records), cap, time.monotonic() - started), end="", flush=True)
        return [_theory_ok(row) for row in rows]

    def prior(u):
        leaf = _containing(leaves, *_physical(u[:2], space[:2]))
        return 0.5 if leaf is None else (leaf[6] + 1) / (leaf[5] + 2)

    starts = _starts(rng, batch, len(space), prior)
    if sampler == "mh":
        trace = mh(evaluate, rng, starts, cap, eps=eps)
        moves = [m["accepted"] for m in trace if m["step"] > 0 and not m["burn_in"]]
        summary = {"acceptance_post_burn_in": sum(moves) / len(moves) if moves else None, "final_step_size": trace[-1]["step_size"] if trace else None,
                   "burn_in_rows": sum(m["burn_in"] for m in trace), "target": "eps + 1[theory_ok], eps = %g" % eps,
                   "target_note": "an indicator target: accepted states are draws from the survivor set, not a physics posterior"}
    else:
        low, high = space[0][:2]
        anchors = np.array([[((x0 + x1) / 2 - low) / (high - low), ((y0 + y1) / 2 - low) / (high - low)] for x0, x1, y0, y1, *_ in leaves]).reshape(-1, 2)
        trace = pso(evaluate, rng, starts, cap, anchors)
        summary = {"best_fitness": max((m["fitness"] for m in trace), default=None), "anchors": len(anchors),
                   "fitness": "theory_ok * d_min (unit cube; leaf centers in mphi, Mbar)"}
    rows = [{**row, **meta} for row, meta in records]
    raw_csv = out / "raw_stochastic_points.csv"
    _write_rows(raw_csv, rows, CANONICAL_COLUMNS + MESH_COLUMNS + PROFILE_COLUMNS + SAMPLER_COLUMNS)
    parquet, reason = write_parquet(str(raw_csv), str(raw_csv.with_suffix(".parquet")))
    valid = sum(_theory_ok(row) for row in rows)
    manifest = {"schema": "dhb.stochastic_12520.manifest.v1", "campaign_id": cfg["campaign_id"], "sampler": sampler, "seed": seed,
        "tan_beta": tb, "config_sha256": _sha256(config_path), "effective_sha256": effective, "physics": cfg["physics"], "mesh": cfg["mesh"],
        "profile": cfg["profile"], "stochastic": cfg["stochastic"], "summary": summary, "theory_ok_fraction": valid / len(rows) if rows else None,
        "mass_convention_authority": convention, "canonical_engine": {"executable": str(executable), "sha256": _sha256(executable),
        "dihiggs_git": _git(root), "boundary_git": _git(Path(__file__).resolve().parents[2])},
        "leaf_namespace": "mesh_leaf_id = '%s:' + finest containing leaf id (root cell if none); never matched by survivor_v2 seeding" % sampler,
        "explored_seed": {"path": str(Path(explored).resolve()), "sha256": _sha256(explored), "regime_matched_leaves": len(leaves),
                          "seeded_attempts": 0, "use": "starting points only"} if explored else None,
        "status": "COMPLETE", "budget": {"cap": cap, "fresh_rows": len(rows), "theory_ok_rows": valid, "remaining": cap - len(rows)},
        "raw_csv": str(raw_csv), "parquet_written": parquet, "parquet_skipped_reason": reason,
        "wall_s": round(time.monotonic() - started, 1), "finished_at_utc": _now()}
    _write_json(out / "manifest.json", manifest)
    print()
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True); parser.add_argument("--output-dir", required=True)
    parser.add_argument("--tan-beta", type=float, required=True); parser.add_argument("--sampler", choices=("mh", "pso"), required=True)
    parser.add_argument("--seed", type=int, required=True); parser.add_argument("--smoke", action="store_true", help="evaluation cap 64")
    parser.add_argument("--explored", metavar="CSV", help="survival prior for starting points: output of `lake explored --export`")
    args = parser.parse_args(argv)
    manifest = run(args.config, args.output_dir, args.tan_beta, args.sampler, args.seed, args.explored, args.smoke)
    print("[DHB] stochastic %s: rows=%d theory_ok=%.3f wall=%.1fs" % (args.sampler, manifest["budget"]["fresh_rows"], manifest["theory_ok_fraction"] or 0, manifest["wall_s"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
