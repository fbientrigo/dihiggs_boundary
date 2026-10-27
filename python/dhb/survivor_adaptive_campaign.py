"""Fresh, survivor-led 125.20 GeV adaptive profile campaign.

Historical leaves are deliberately only a deterministic scheduling hint.  This
module never reads a historical point verdict when deciding whether a leaf has
a survivor.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from .adaptive_m2_mesh import (
    CANONICAL_COLUMNS, MESH_COLUMNS, _canonical_api, _git, _new_leaf, _now,
    _run_profile, _shard_valid, _tag, _write_json, _write_rows, children,
    write_parquet,
)
from .profiled_m2_scan import _lhs, _mass_convention, _theory_ok


Z95 = 1.959963984540054
LEAF_FIELDS = [
    "tan_beta", "leaf_id", "parent_id", "depth", "ix", "iy", "active",
    "mphi_min_GeV", "mphi_max_GeV", "Mbar_min_GeV", "Mbar_max_GeV",
    "mphi_center_GeV", "Mbar_center_GeV", "attempts", "successes",
    "theory_pass_fraction", "wilson95_low", "wilson95_high",
    "zero_event_upper_95", "decision_state", "coverage_state",
    "priority_provenance", "historical_hint", "historical_hint_score",
    "historical_hint_provenance", "has_survivor",
    "best_point_id", "mesh_source",
]


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def wilson95(successes, attempts):
    """Two-sided Wilson 95% interval, including the finite zero-success case."""
    if attempts <= 0:
        return math.nan, math.nan
    p = successes / attempts
    denominator = 1 + Z95 * Z95 / attempts
    center = (p + Z95 * Z95 / (2 * attempts)) / denominator
    radius = Z95 * math.sqrt(p * (1 - p) / attempts + Z95 * Z95 / (4 * attempts * attempts)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def zero_event_upper_95(attempts):
    """Exact one-sided 95% binomial upper bound after zero survivors."""
    return 1 - .05 ** (1 / attempts) if attempts else math.nan


def _load(path):
    path = Path(path).resolve()
    cfg = yaml.safe_load(path.read_text())
    if not isinstance(cfg, dict) or cfg.get("schema_version") not in {"dhb.survivor_adaptive_12520.v1", "dhb.survivor_adaptive_12520_tanbeta.v2"}:
        raise ValueError("unsupported survivor adaptive config")
    root = (path.parent / cfg["dihiggs_root"]).resolve()
    executable = (root / cfg["evaluator"]).resolve()
    if not executable.is_file():
        raise ValueError("canonical evaluator missing: %s" % executable)
    for key in ("manifest", "state", "archive_manifest"):
        cfg["historical_hint"][key] = str((path.parent / cfg["historical_hint"][key]).resolve())
    archive = json.loads(Path(cfg["historical_hint"]["archive_manifest"]).read_text())
    if archive.get("convention", {}).get("status") != "historical_only":
        raise ValueError("historical hint archive is not historical-only")
    if cfg["schema_version"].endswith("v2"):
        quotas = cfg.get("slice_batch_quotas", [])
        batch = int(cfg["profile"]["batch_size"])
        if len(quotas) != len(cfg["tan_beta_slices"]) or any(int(q) != q or int(q) < int(cfg["mesh"]["root_cells"]) ** 2 for q in quotas):
            raise ValueError("v2 slice batch quotas must cover every root cell")
        if batch * sum(map(int, quotas)) != int(cfg["mesh"]["new_evaluation_cap"]):
            raise ValueError("v2 cap must equal the exact per-slice batch quotas")
    return path, cfg, root, executable


def _new_root_leaves(cfg):
    mesh, leaves = cfg["mesh"], []
    low, high, n = float(mesh["min_GeV"]), float(mesh["max_GeV"]), int(mesh["root_cells"])
    for tb in map(float, cfg["tan_beta_slices"]):
        for ix in range(n):
            for iy in range(n):
                leaf = _new_leaf(tb, 0, ix, iy, low, high, n, source="calibration")
                leaf.update(attempts=0, successes=0, theory_pass_fraction=math.nan,
                            wilson95_low=math.nan, wilson95_high=math.nan,
                            zero_event_upper_95=math.nan, decision_state="inconclusive",
                            coverage_state="inconclusive", priority_provenance="root_calibration",
                            historical_hint=False, historical_hint_score=0.0,
                            historical_hint_provenance="none", has_survivor=False, best_point_id="")
                leaves.append(leaf)
    return leaves


def _historical_rectangles(cfg):
    """Read only historical geometry; v2 never reads a historical verdict."""
    state = json.loads(Path(cfg["historical_hint"]["state"]).read_text())
    geometry_only = cfg.get("schema_version", "").endswith("v2")
    return [(float(leaf["tan_beta"]), float(leaf["mphi_min_GeV"]), float(leaf["mphi_max_GeV"]),
             float(leaf["Mbar_min_GeV"]), float(leaf["Mbar_max_GeV"]))
            for leaf in state.get("leaves", []) if leaf.get("active") and (leaf.get("mesh_source") == "adaptive" if geometry_only else leaf.get("has_survivor"))]


def _overlaps_history(leaf, history):
    return any(leaf["tan_beta"] == tb and leaf["mphi_min_GeV"] < x1 and x0 < leaf["mphi_max_GeV"]
               and leaf["Mbar_min_GeV"] < y1 and y0 < leaf["Mbar_max_GeV"]
               for tb, x0, x1, y0, y1 in history)


def _history_score(leaf, history):
    """Interpolate binary 125.13 rectangle occupancy in log(tan beta)."""
    slices = sorted({entry[0] for entry in history})
    if not slices:
        return 0.0, "historical_12513_log_interpolation:none"
    target = float(leaf["tan_beta"])
    lower = max((value for value in slices if value <= target), default=slices[0])
    upper = min((value for value in slices if value >= target), default=slices[-1])
    def occupied(tb):
        return float(any(tb == htb and leaf["mphi_min_GeV"] < x1 and x0 < leaf["mphi_max_GeV"]
                         and leaf["Mbar_min_GeV"] < y1 and y0 < leaf["Mbar_max_GeV"]
                         for htb, x0, x1, y0, y1 in history))
    low, high = occupied(lower), occupied(upper)
    weight = 0.0 if lower == upper else (math.log10(target) - math.log10(lower)) / (math.log10(upper) - math.log10(lower))
    score = low + weight * (high - low)
    return score, "historical_12513_log_interpolation:%.17g:%.17g:%.17g" % (lower, upper, weight)


def _verify_historical_inputs(cfg):
    """Check only the archived files used as geometry hints, before any output."""
    archive_manifest = Path(cfg["historical_hint"]["archive_manifest"])
    inventory = archive_manifest.parent / json.loads(archive_manifest.read_text())["sha256_inventory"]
    expected = {}
    with inventory.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            expected[row["path"]] = row["sha256"]
    checked = []
    for key in ("manifest", "state"):
        path = Path(cfg["historical_hint"][key])
        relative = str(path.relative_to(inventory.parent))
        actual = _sha256(path)
        if expected.get(relative) != actual:
            raise ValueError("historical checksum mismatch: %s" % relative)
        checked.append({"path": str(path), "sha256": actual})
    return {"inventory": str(inventory), "inventory_sha256": _sha256(inventory), "checked": checked}


def _halo_ids(leaves, depth):
    result = set()
    for tb in {leaf["tan_beta"] for leaf in leaves}:
        level = [leaf for leaf in leaves if leaf["active"] and leaf["depth"] == depth and leaf["tan_beta"] == tb]
        survivors = [leaf for leaf in level if leaf["has_survivor"]]
        result.update(leaf["leaf_id"] for leaf in level if any(abs(leaf["ix"] - hit["ix"]) <= 1 and abs(leaf["iy"] - hit["iy"]) <= 1 for hit in survivors))
    return result


def priority(leaf, halo_ids, historical_hint):
    """Current evidence wins; history breaks only otherwise equal scheduling ties."""
    if leaf["has_survivor"]:
        return 0, "current_survivor"
    if leaf["leaf_id"] in halo_ids:
        return 1, "current_survivor_halo"
    if historical_hint:
        return 2, "historical_12513_hint"
    return 3, "none"


def _paths(out, leaf_id=None):
    paths = out.glob("tanbeta_*/raw_shards/*/*.csv")
    return sorted(path for path in paths if not path.name.endswith(".canonical.csv") and (leaf_id is None or path.parent.name == leaf_id.replace("/", "__")))


def _rows(out, leaf_id):
    rows = []
    for path in _paths(out, leaf_id):
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def _update_leaf(leaf, rows, max_zero):
    """Leaf verdict from this run's rows plus any prior lake coverage (prior_attempts/prior_successes, see load_explored)."""
    successes = [row for row in rows if _theory_ok(row)]
    n, k = len(rows) + leaf.get("prior_attempts", 0), len(successes) + leaf.get("prior_successes", 0)
    leaf["attempts"], leaf["successes"] = n, k
    leaf["has_survivor"] = bool(k)
    leaf["theory_pass_fraction"] = k / n if n else math.nan
    leaf["wilson95_low"], leaf["wilson95_high"] = wilson95(k, n)
    leaf["zero_event_upper_95"] = zero_event_upper_95(n) if not k else math.nan
    leaf["best_point_id"] = max(successes, key=lambda row: abs(float(row.get("g_physical_hphiphi_GeV", "nan"))), default={}).get("point_id", leaf.get("prior_best_point_id", ""))
    leaf["decision_state"] = "survivor" if k else ("tested_empty_95" if n >= max_zero else "inconclusive")
    leaf["coverage_state"] = leaf["decision_state"]


def _geometry(leaf):
    return (leaf["leaf_id"], float(leaf["tan_beta"]), float(leaf["mphi_min_GeV"]), float(leaf["mphi_max_GeV"]),
            float(leaf["Mbar_min_GeV"]), float(leaf["Mbar_max_GeV"]))


def load_explored(path, cfg, convention_id):
    """Prior coverage from `lake explored --export`: {leaf geometry: (n_points, n_valid, best_point_id)}.

    Only rows of this exact regime count: lambda7 and mh equal, and convention_id equal when the lake knows it
    (commits before 2026-10-27 have none; there mh is the measured proxy). The leaf id and its rectangle must both
    match, so a mesh with other root cells or bounds is never mistaken for this one."""
    lam7, mh, prior = float(cfg["physics"]["lambda7"]), float(cfg["physics"]["mh_GeV"]), {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not row["lambda7"] or not row["mh_GeV"] or float(row["lambda7"]) != lam7 or not math.isclose(float(row["mh_GeV"]), mh, rel_tol=1e-9):
                continue
            if row.get("convention_id") and row["convention_id"] != convention_id:
                continue
            key, n = _geometry(row), int(row["n_points"])
            # ponytail: max over commits/campaigns, not a sum: a growing campaign re-commits its earlier rows, and an
            # undercount only re-runs a batch while an overcount would skip unexplored work. Sum distinct point_ids if that matters.
            if n > prior.get(key, (0,))[0]:
                prior[key] = (n, int(row["n_valid"]), row.get("best_point_id", ""))
    return prior


def _seed(leaf, prior, max_zero):
    """A new leaf already explored in the lake starts from its recorded counts instead of from zero."""
    n, k, best = prior.get(_geometry(leaf), (0, 0, ""))
    if n:
        leaf.update(prior_attempts=n, prior_successes=k, prior_best_point_id=best)
        _update_leaf(leaf, [], max_zero)
    return leaf


def _contexts(leaf, cfg, replicate):
    profile, physics = cfg["profile"], cfg["physics"]
    tb, n = leaf["tan_beta"], int(profile["batch_size"])
    envelope = profile["lambda6_hard_envelope"]
    spec = dict(profile["X_lambda6_times_tan_beta"])
    spec["min"] = max(float(spec["min"]), float(envelope["min"]) * tb)
    spec["max"] = min(float(spec["max"]), float(envelope["max"]) * tb)
    seed = "%s:%s:r%d" % (profile["seed"], leaf["leaf_id"], replicate)
    samples = _lhs(seed, n, {"X": spec, "Delta": profile["Delta_heavy_GeV"]})
    for index, (x, delta) in enumerate(zip(samples["X"], samples["Delta"])):
        unclipped = x / tb
        lam6 = min(max(unclipped, float(envelope["min"])), float(envelope["max"]))
        yield index, {"campaign_id": cfg["campaign_id"], "run_id": "%s_r%02d_p%02d" % (leaf["leaf_id"].replace("/", "_"), replicate, index),
            "profile_index": index, "profile_replicate": replicate, "profile_seed": seed, "tan_beta": tb,
            "yukawa_type": int(physics["yukawa_type"]), "mh_input_GeV": float(physics["mh_GeV"]),
            "mH_input_GeV": leaf["mphi_center_GeV"], "M2_input_GeV2": leaf["Mbar_center_GeV"] ** 2,
            "mA_input_GeV": leaf["mphi_center_GeV"] + delta, "mHp_input_GeV": leaf["mphi_center_GeV"] + delta,
            "sin_beta_minus_alpha_input": float(physics["sin_beta_minus_alpha"]), "lambda7_input": float(physics["lambda7"]),
            "X_lambda6_times_tan_beta": x, "lambda6_from_X": lam6, "lambda6_clipped": int(lam6 != unclipped),
            "Delta_heavy_GeV": delta, "mA_minus_mphi_GeV": delta, "mesh_leaf_id": leaf["leaf_id"],
            "mesh_parent_id": leaf["parent_id"], "mesh_depth": leaf["depth"], "mesh_source": leaf["mesh_source"]}


def _run_batch(out, leaves, cfg, executable, dihiggs_root, api, cap, started):
    """Evaluate one complete 16-point replicate per leaf; never overrun the cap."""
    batch = int(cfg["profile"]["batch_size"])
    eligible = [leaf for leaf in leaves if leaf["attempts"] + batch <= cap]
    jobs = []
    for leaf in eligible:
        replicate = -(-leaf["attempts"] // batch)  # ceil: a partial prior replicate is never re-proposed
        directory = out / ("tanbeta_" + _tag(leaf["tan_beta"])) / "raw_shards" / leaf["leaf_id"].replace("/", "__")
        directory.mkdir(parents=True, exist_ok=True)
        for index, context in _contexts(leaf, cfg, replicate):
            jobs.append((directory / ("replicate_%02d_profile_%02d.csv" % (replicate, index)), leaf, context, cfg, executable, dihiggs_root, api))
    fresh = [job for job in jobs if not _shard_valid(job[0])]
    with ThreadPoolExecutor(max_workers=int(cfg["runtime"]["max_workers"])) as pool:
        for done, _ in enumerate(pool.map(_run_profile, fresh), 1):
            if done == len(fresh) or done % batch == 0:
                elapsed = max(time.monotonic() - started, 1e-9)
                rate = done / elapsed
                eta = (len(fresh) - done) / rate if rate else 0
                print("\r[DHB] survivor adaptive: %d/%d batch rows, %.1f/s, ETA %.1fs" % (done, len(fresh), rate, eta), end="", flush=True)
    for leaf in eligible:
        _update_leaf(leaf, _rows(out, leaf["leaf_id"]), int(cfg["profile"]["zero_success_max_attempts"]))
    return len(jobs)


def _consolidate(out, output, fields):
    temporary, count = output.with_suffix(output.suffix + ".tmp"), 0
    with temporary.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore", lineterminator="\n"); writer.writeheader()
        for path in _paths(out):
            with path.open(newline="", encoding="utf-8") as source:
                for row in csv.DictReader(source): writer.writerow(row); count += 1
    os.replace(temporary, output)
    return count


def _save_state(path, leaves):
    _write_json(path, {"schema": "dhb.survivor_adaptive_12520.state.v1", "leaves": leaves})


def slice_batch_quotas(cfg):
    """The v2 contract is batch-exact; v1 retains its single global cap."""
    quotas = cfg.get("slice_batch_quotas")
    if quotas is None:
        return None
    return {float(tb): int(quota) for tb, quota in zip(cfg["tan_beta_slices"], quotas)}


def _new_v2_leaf(leaf, history):
    score, provenance = _history_score(leaf, history)
    leaf.update(attempts=0, successes=0, theory_pass_fraction=math.nan,
                wilson95_low=math.nan, wilson95_high=math.nan,
                zero_event_upper_95=math.nan, decision_state="inconclusive",
                coverage_state="inconclusive", priority_provenance="new",
                historical_hint=bool(score), historical_hint_score=score,
                historical_hint_provenance=provenance, has_survivor=False,
                best_point_id="")
    return leaf


def _annotate_v2(leaves, history):
    halo = set().union(*(_halo_ids(leaves, depth) for depth in {leaf["depth"] for leaf in leaves}))
    for leaf in leaves:
        score, provenance = _history_score(leaf, history)
        leaf["historical_hint_score"] = score
        leaf["historical_hint"] = bool(score)
        leaf["historical_hint_provenance"] = provenance
        _, leaf["priority_provenance"] = priority(leaf, halo, bool(score))
    return halo


def _v2_rank(leaf, halo):
    return (*priority(leaf, halo, bool(leaf["historical_hint_score"])), -leaf["historical_hint_score"], leaf["attempts"], leaf["leaf_id"])


def _run_v2(config_path, cfg, dihiggs_root, executable, output_dir, smoke, mass_convention, history_checks, only_tan_beta=None, explored=None):
    """Run each slice to its independent exact batch quota."""
    if smoke:
        cfg = json.loads(json.dumps(cfg))
        cfg["mesh"]["root_cells"] = 4
        cfg["mesh"]["max_depth"] = 1
        cfg["slice_batch_quotas"] = [16] * len(cfg["tan_beta_slices"])
        cfg["mesh"]["new_evaluation_cap"] = 16 * int(cfg["profile"]["batch_size"]) * len(cfg["tan_beta_slices"])
        cfg["campaign_id"] += "_smoke"
    out = Path(output_dir).resolve() / cfg["campaign_id"]
    out.mkdir(parents=True, exist_ok=True)
    state_path, history = out / "campaign_state.json", _historical_rectangles(cfg)
    max_zero = int(cfg["profile"]["zero_success_max_attempts"])
    prior = load_explored(explored, cfg, mass_convention["convention_id"]) if explored else {}
    leaves = json.loads(state_path.read_text())["leaves"] if state_path.exists() else _new_root_leaves(cfg)
    if not state_path.exists():  # a resumed run keeps its state; prior coverage then seeds only leaves it creates
        for leaf in leaves:
            _seed(_new_v2_leaf(leaf, history), prior, max_zero)
    quotas, batch = slice_batch_quotas(cfg), int(cfg["profile"]["batch_size"])
    api, started = _canonical_api(dihiggs_root), time.monotonic()
    low, high, root_n = float(cfg["mesh"]["min_GeV"]), float(cfg["mesh"]["max_GeV"]), int(cfg["mesh"]["root_cells"])
    depth_limit = min(int(cfg["mesh"]["max_depth"]), int(math.log2(int(cfg["mesh"]["max_cells_per_axis"]) / root_n)))
    if only_tan_beta is not None and float(only_tan_beta) not in quotas:
        raise ValueError("requested tan(beta) is not in config")
    selected = {float(only_tan_beta)} if only_tan_beta is not None else set(quotas)
    for tb, quota in quotas.items():
        if tb not in selected:
            continue
        limit = quota * batch
        roots = [leaf for leaf in leaves if leaf["tan_beta"] == tb and leaf["depth"] == 0 and not leaf["attempts"]]
        if roots:
            _run_batch(out, roots, cfg, executable, dihiggs_root, api, limit, started)
            _save_state(state_path, leaves)
        while sum(leaf["attempts"] for leaf in leaves if leaf["tan_beta"] == tb) < limit:
            active = [leaf for leaf in leaves if leaf["tan_beta"] == tb and leaf["active"]]
            halo = _annotate_v2(active, history)
            used = sum(leaf["attempts"] for leaf in leaves if leaf["tan_beta"] == tb)
            remaining = (limit - used) // batch
            refinable = [leaf for leaf in active if leaf["depth"] < depth_limit and (leaf["has_survivor"] or leaf["historical_hint_score"] > 0)]
            if remaining >= 4 and refinable:
                parent = min(refinable, key=lambda leaf: _v2_rank(leaf, halo))
                new = [_seed(_new_v2_leaf(child, history), prior, max_zero) for child in children(parent, low, high, root_n)]
                leaves.extend(new)
                _run_batch(out, [leaf for leaf in new if not leaf["attempts"]], cfg, executable, dihiggs_root, api, limit, started)
                _save_state(state_path, leaves)
                continue
            eligible = [leaf for leaf in active if leaf["has_survivor"] or leaf["attempts"] < max_zero]
            if not eligible:
                raise RuntimeError("v2 quota cannot be filled without exceeding the zero-success safeguard")
            _run_batch(out, [min(eligible, key=lambda leaf: _v2_rank(leaf, halo))], cfg, executable, dihiggs_root, api, limit, started)
            _save_state(state_path, leaves)
        active = [leaf for leaf in leaves if leaf["tan_beta"] == tb and leaf["active"]]
        if any(leaf["depth"] < depth_limit and (leaf["has_survivor"] or leaf["historical_hint_score"] > 0) for leaf in active):
            for leaf in active:
                if leaf["depth"] < depth_limit and (leaf["has_survivor"] or leaf["historical_hint_score"] > 0):
                    leaf["decision_state"] = leaf["coverage_state"] = "pending_refinement"
            _save_state(state_path, leaves)
    fields = CANONICAL_COLUMNS + MESH_COLUMNS + ["profile_index", "profile_replicate", "profile_seed", "X_lambda6_times_tan_beta", "lambda6_from_X", "lambda6_clipped", "Delta_heavy_GeV", "mA_minus_mphi_GeV", "profile_status"]
    raw_csv = out / "raw_fresh_12520_tanbeta_v2_points.csv"
    total = _consolidate(out, raw_csv, fields)
    completed = [tb for tb, quota in quotas.items() if sum(leaf["attempts"] for leaf in leaves if leaf["tan_beta"] == tb) == quota * batch]
    seeded = sum(leaf.get("prior_attempts", 0) for leaf in leaves)
    complete = len(completed) == len(quotas) and total + seeded == int(cfg["mesh"]["new_evaluation_cap"])
    _write_rows(out / "rectangular_leaves.csv", leaves, LEAF_FIELDS)
    parquet, reason = write_parquet(str(raw_csv), str(raw_csv.with_suffix(".parquet"))) if complete else (False, "deferred until all tan(beta) slices finish")
    manifest = {"schema": "dhb.survivor_adaptive_12520_tanbeta.manifest.v2", "campaign_id": cfg["campaign_id"], "config_sha256": _sha256(config_path),
        "effective_config_sha256": hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(), "physics": cfg["physics"], "mesh": cfg["mesh"], "profile": cfg["profile"],
        "mass_convention_authority": mass_convention, "canonical_engine": {"executable": str(executable), "sha256": _sha256(executable), "dihiggs_git": _git(dihiggs_root), "boundary_git": _git(Path(__file__).resolve().parents[2])},
        "historical_inputs": history_checks["checked"], "historical_archive_checksum_verification": history_checks,
        "historical_hint_scoring": {"method": "binary rectangle occupancy linearly interpolated in log(tan_beta)", "historical_tan_beta_slices": sorted({entry[0] for entry in history}), "scheduling_only": True},
        "historical_evidence_policy": "125.13 geometry is a deterministic priority hint only; no historical rows, outcomes, intervals, fractions, or classifications were pooled into this 125.20 campaign.",
        "explored_seed": {"path": str(Path(explored).resolve()), "sha256": _sha256(explored), "regime_matched_leaves": len(prior),
                          "seeded_leaves": sum(1 for leaf in leaves if leaf.get("prior_attempts")), "seeded_attempts": seeded} if explored else None,
        "status": "COMPLETE" if complete else "RUNNING", "completed_tan_beta_slices": completed, "last_selected_tan_beta_slices": sorted(selected),
        "budget": {"cap": int(cfg["mesh"]["new_evaluation_cap"]), "batch_size": batch, "slice_batch_quotas": [{"tan_beta": tb, "batches": quota, "rows": quota * batch} for tb, quota in quotas.items()], "fresh_rows": total, "remaining": int(cfg["mesh"]["new_evaluation_cap"]) - total - seeded},
        "effective_max_depth": depth_limit, "raw_csv": str(raw_csv), "state": str(state_path), "parquet_written": parquet, "parquet_skipped_reason": reason, "finished_at_utc": _now()}
    _write_json(out / "manifest.json", manifest)
    if complete:
        from .survivor_adaptive_aggregate import aggregate_run
        aggregate_run(out)
    print(); return manifest


def run(config_path, output_dir, smoke=False, only_tan_beta=None, explored=None):
    config_path, cfg, dihiggs_root, executable = _load(config_path)
    if smoke and not cfg["schema_version"].endswith("v2"):
        cfg = json.loads(json.dumps(cfg)); cfg["mesh"]["root_cells"] = 4; cfg["mesh"]["max_depth"] = 1; cfg["mesh"]["new_evaluation_cap"] = 2048; cfg["campaign_id"] += "_smoke"
    # Fail before writing a fresh row if the canonical evaluator disagrees
    # with this campaign's claimed active mass convention.
    mass_convention = _mass_convention(dihiggs_root, float(cfg["physics"]["mh_GeV"]))
    if cfg["schema_version"].endswith("v2"):
        return _run_v2(config_path, cfg, dihiggs_root, executable, output_dir, smoke, mass_convention, _verify_historical_inputs(cfg), only_tan_beta, explored)
    if explored is not None:
        raise ValueError("--explored is supported only for the v2 campaign")
    if only_tan_beta is not None:
        raise ValueError("--tan-beta is supported only for the v2 campaign")
    out = Path(output_dir).resolve() / cfg["campaign_id"]; out.mkdir(parents=True, exist_ok=True)
    state_path = out / "campaign_state.json"; history = _historical_rectangles(cfg)
    leaves = json.loads(state_path.read_text())["leaves"] if state_path.exists() else _new_root_leaves(cfg)
    cap, batch = int(cfg["mesh"]["new_evaluation_cap"]), int(cfg["profile"]["batch_size"])
    if cap < len(leaves) * batch: raise ValueError("campaign cap cannot cover root calibration")
    api, started = _canonical_api(dihiggs_root), time.monotonic()
    root = [leaf for leaf in leaves if leaf["active"] and leaf["depth"] == 0 and not leaf["attempts"]]
    if root: _run_batch(out, root, cfg, executable, dihiggs_root, api, cap, started); _save_state(state_path, leaves)
    low, high, root_n = float(cfg["mesh"]["min_GeV"]), float(cfg["mesh"]["max_GeV"]), int(cfg["mesh"]["root_cells"])
    depth_limit = min(int(cfg["mesh"]["max_depth"]), int(math.log2(int(cfg["mesh"]["max_cells_per_axis"]) / root_n)))
    for depth in range(depth_limit):
        level = [leaf for leaf in leaves if leaf["active"] and leaf["depth"] == depth]
        halo = _halo_ids(level, depth)
        for leaf in level:
            leaf["historical_hint"] = _overlaps_history(leaf, history)
            _, leaf["priority_provenance"] = priority(leaf, halo, leaf["historical_hint"])
        # A zero-survivor halo/history cell gets at most four independent batches.
        extra = [leaf for leaf in level if not leaf["has_survivor"] and leaf["attempts"] < int(cfg["profile"]["zero_success_max_attempts"])
                 and leaf["priority_provenance"] != "none"]
        remaining = cap - sum(leaf["attempts"] for leaf in leaves)
        extra = sorted(extra, key=lambda leaf: (*priority(leaf, halo, leaf["historical_hint"]), leaf["leaf_id"]))[:remaining // batch]
        if extra: _run_batch(out, extra, cfg, executable, dihiggs_root, api, cap, started); _save_state(state_path, leaves)
        remaining = cap - sum(leaf["attempts"] for leaf in leaves)
        targets = sorted((leaf for leaf in level if leaf["priority_provenance"] != "none"), key=lambda leaf: (*priority(leaf, halo, leaf["historical_hint"]), leaf["leaf_id"]))
        chosen, pending = targets[:remaining // (4 * batch)], targets[remaining // (4 * batch):]
        for leaf in pending:
            leaf["decision_state"] = leaf["coverage_state"] = "pending_refinement"
        new = [child for leaf in chosen for child in children(leaf, low, high, root_n)]
        for leaf in new:
            leaf.update(attempts=0, successes=0, theory_pass_fraction=math.nan, wilson95_low=math.nan, wilson95_high=math.nan,
                        zero_event_upper_95=math.nan, decision_state="inconclusive", coverage_state="inconclusive",
                        priority_provenance="new", historical_hint=_overlaps_history(leaf, history), historical_hint_score=0.0,
                        historical_hint_provenance="exact_12513_slice_only", has_survivor=False, best_point_id="")
        leaves.extend(new)
        if new: _run_batch(out, new, cfg, executable, dihiggs_root, api, cap, started); _save_state(state_path, leaves)
    fields = CANONICAL_COLUMNS + MESH_COLUMNS + ["profile_index", "profile_replicate", "profile_seed", "X_lambda6_times_tan_beta", "lambda6_from_X", "lambda6_clipped", "Delta_heavy_GeV", "mA_minus_mphi_GeV", "profile_status"]
    total = _consolidate(out, out / "raw_fresh_12520_points.csv", fields)
    _write_rows(out / "rectangular_leaves.csv", leaves, LEAF_FIELDS)
    parquet, reason = write_parquet(str(out / "raw_fresh_12520_points.csv"), str(out / "raw_fresh_12520_points.parquet"))
    manifest = {"schema": "dhb.survivor_adaptive_12520.manifest.v1", "campaign_id": cfg["campaign_id"], "config_sha256": _sha256(config_path),
        "effective_config_sha256": hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(), "physics": cfg["physics"], "mesh": cfg["mesh"], "profile": cfg["profile"],
        "mass_convention_authority": mass_convention, "canonical_engine": {"executable": str(executable), "sha256": _sha256(executable), "dihiggs_git": _git(dihiggs_root), "boundary_git": _git(Path(__file__).resolve().parents[2])},
        "historical_inputs": [{"path": cfg["historical_hint"][key], "sha256": _sha256(cfg["historical_hint"][key])} for key in ("manifest", "state")],
        "historical_archive_manifest": {"path": cfg["historical_hint"]["archive_manifest"], "sha256": _sha256(cfg["historical_hint"]["archive_manifest"])},
        "historical_evidence_policy": "125.13 geometry is a deterministic priority hint only; its outcomes were not pooled statistically or used to classify 125.20 survivors.",
        "budget": {"cap": cap, "root_calibration_rows": len([leaf for leaf in leaves if leaf["depth"] == 0]) * batch, "fresh_rows": total, "remaining": cap - total}, "effective_max_depth": depth_limit,
        "raw_csv": str(out / "raw_fresh_12520_points.csv"), "state": str(state_path), "parquet_written": parquet, "parquet_skipped_reason": reason, "finished_at_utc": _now()}
    _write_json(out / "manifest.json", manifest)
    from .survivor_adaptive_aggregate import aggregate_run
    aggregate_run(out)
    print(); return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--config", required=True); parser.add_argument("--output-dir", required=True); parser.add_argument("--smoke", action="store_true"); parser.add_argument("--tan-beta", type=float, help="run or resume one configured v2 slice")
    parser.add_argument("--explored", metavar="CSV", help="skip/reuse leaves already explored for this regime: output of `lake explored --export`")
    args = parser.parse_args(argv); manifest = run(args.config, args.output_dir, args.smoke, args.tan_beta, args.explored); print("[DHB] survivor adaptive: status=%s rows=%d" % (manifest.get("status", "COMPLETE"), manifest["budget"]["fresh_rows"])); return 0


if __name__ == "__main__": raise SystemExit(main())
