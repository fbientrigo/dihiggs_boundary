"""Bounded adaptive rectangular profile scan seeded from a completed grid."""

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from .profiled_m2_scan import (
    CANONICAL_COLUMNS, _canonical_api, _git, _lhs, _mass_convention,
    _now, _theory_ok, _write_rows, write_parquet,
)


MESH_COLUMNS = [
    "mesh_leaf_id", "mesh_parent_id", "mesh_depth", "mesh_source",
    "mphi_min_GeV", "mphi_max_GeV", "Mbar_min_GeV", "Mbar_max_GeV",
    "mphi_center_GeV", "Mbar_center_GeV",
]
LEAF_FIELDS = [
    "tan_beta", "leaf_id", "parent_id", "depth", "active", "mphi_min_GeV",
    "mphi_max_GeV", "Mbar_min_GeV", "Mbar_max_GeV", "mphi_center_GeV",
    "Mbar_center_GeV", "coverage_state", "seed_status", "has_survivor",
    "profile_count", "valid_count", "dominant_rejection_stage",
    "dominant_rejection_reason", "best_point_id",
]


def _tag(value):
    return ("%.0e" % value).replace("+", "").replace("-", "m")


def _number(row, key):
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return math.nan


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _load_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def root_index(value, low, high, n):
    """Assign a seed coordinate to a half-open root cell, closing at high."""
    if not low <= value <= high:
        raise ValueError("coordinate outside adaptive mesh")
    return min(n - 1, int((value - low) * n / (high - low)))


def _leaf_id(tb, depth, ix, iy, parent=""):
    base = "tb_%s_d%02d_x%03d_y%03d" % (_tag(tb), depth, ix, iy)
    return base if not parent else parent + "/" + base.rsplit("_", 2)[-2] + "_" + base.rsplit("_", 1)[-1]


def _new_leaf(tb, depth, ix, iy, low, high, n, parent_id="", source="seed"):
    width = (high - low) / (n * (2 ** depth))
    x0, y0 = low + ix * width, low + iy * width
    return {
        "tan_beta": float(tb), "leaf_id": _leaf_id(tb, depth, ix, iy, parent_id),
        "parent_id": parent_id, "depth": depth, "ix": ix, "iy": iy, "active": True,
        "mphi_min_GeV": x0, "mphi_max_GeV": x0 + width,
        "Mbar_min_GeV": y0, "Mbar_max_GeV": y0 + width,
        "mphi_center_GeV": x0 + width / 2, "Mbar_center_GeV": y0 + width / 2,
        "mesh_source": source, "coverage_state": "seed_incomplete" if source == "seed" else "new_incomplete",
        "seed_status": "unassigned" if source == "seed" else "not_applicable",
        "has_survivor": False, "profile_count": 0, "valid_count": 0,
        "dominant_rejection_stage": "", "dominant_rejection_reason": "", "best_point_id": "",
    }


def root_leaves(tan_betas, low, high, n):
    return [_new_leaf(tb, 0, ix, iy, low, high, n) for tb in tan_betas for ix in range(n) for iy in range(n)]


def children(leaf, low, high, root_n):
    leaf["active"] = False
    leaf["coverage_state"] = "refined"
    depth, ix, iy = leaf["depth"] + 1, leaf["ix"] * 2, leaf["iy"] * 2
    return [_new_leaf(leaf["tan_beta"], depth, ix + dx, iy + dy, low, high, root_n, leaf["leaf_id"], "adaptive")
            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1))]


def refinement_targets(leaves, depth):
    """Return same-depth Chebyshev-one-cell halos around survivor evidence."""
    result = []
    for tb in sorted({leaf["tan_beta"] for leaf in leaves}):
        level = [leaf for leaf in leaves if leaf["active"] and leaf["tan_beta"] == tb and leaf["depth"] == depth]
        survivors = [leaf for leaf in level if leaf["has_survivor"]]
        for leaf in level:
            if any(abs(leaf["ix"] - survivor["ix"]) <= 1 and abs(leaf["iy"] - survivor["iy"]) <= 1 for survivor in survivors):
                result.append(leaf)
    return sorted(result, key=lambda leaf: (leaf["tan_beta"], leaf["leaf_id"]))


def budgeted_targets(targets, existing_rows, cap, proposals):
    """Keep whole four-child refinements within the canonical-row cap."""
    count = max(0, (cap - existing_rows) // (4 * proposals))
    return targets[:count], targets[count:]


def eligible_refinement_targets(leaves, depth, max_depth):
    return refinement_targets(leaves, depth) if depth < max_depth else []


def _mode(rows, field):
    values = [row.get(field, "") for row in rows if row.get(field, "")]
    return min(set(values), key=lambda x: (-values.count(x), x)) if values else ""


def _update_leaf(leaf, rows, expected=None):
    valid = [row for row in rows if _theory_ok(row)]
    leaf["profile_count"], leaf["valid_count"] = len(rows), len(valid)
    leaf["has_survivor"] = bool(valid)
    leaf["dominant_rejection_stage"] = _mode([row for row in rows if not _theory_ok(row)], "rejection_stage")
    leaf["dominant_rejection_reason"] = _mode([row for row in rows if not _theory_ok(row)], "rejection_reason")
    best = max(valid, key=lambda row: abs(_number(row, "g_physical_hphiphi_GeV")), default=None)
    leaf["best_point_id"] = best.get("point_id", "") if best else ""
    complete = bool(rows) if expected is None else len(rows) == expected
    if leaf["mesh_source"] == "seed":
        leaf["seed_status"] = "survivor" if valid else ("tested_empty" if complete else "incomplete")
        leaf["coverage_state"] = "seed_survivor" if valid else ("seed_tested_empty" if complete else "seed_incomplete")
    elif leaf["coverage_state"] != "pending_refinement":
        leaf["coverage_state"] = "survivor_region" if valid else ("no_survivor_found" if complete else "new_incomplete")


def _annotate_seed(seed_rows, leaves, low, high, root_n, expected_counts=None):
    lookup = {(leaf["tan_beta"], leaf["ix"], leaf["iy"]): leaf for leaf in leaves if leaf["depth"] == 0}
    grouped = {leaf["leaf_id"]: [] for leaf in leaves if leaf["depth"] == 0}
    result = []
    for row in seed_rows:
        tb, x, y = (_number(row, key) for key in ("tan_beta_input", "mH_input_GeV", "M_plot_GeV"))
        leaf = lookup.get((tb, root_index(x, low, high, root_n), root_index(y, low, high, root_n)))
        if leaf is None:
            raise ValueError("seed row does not match configured tan(beta) or root mesh")
        merged = dict(row)
        merged.update(_mesh_row(leaf, "seed"))
        result.append(merged); grouped[leaf["leaf_id"]].append(merged)
    for leaf in leaves:
        _update_leaf(leaf, grouped[leaf["leaf_id"]], (expected_counts or {}).get(leaf["leaf_id"]))
    return result


def _seed_expected_counts(seed_manifest, leaves, low, high, root_n):
    grid = seed_manifest.get("outer_grid", {})
    try:
        mphi, mbar = grid["m_phi_GeV"], grid["M_plot_GeV"]
        nx, ny = int(mphi["n"]), int(mbar["n"])
        profiles = int(seed_manifest["profile"]["n_proposals"])
        xs = [float(mphi["min"]) + i * (float(mphi["max"]) - float(mphi["min"])) / (nx - 1) for i in range(nx)]
        ys = [float(mbar["min"]) + i * (float(mbar["max"]) - float(mbar["min"])) / (ny - 1) for i in range(ny)]
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return {}
    by_root = {(leaf["tan_beta"], leaf["ix"], leaf["iy"]): leaf["leaf_id"] for leaf in leaves}
    counts = {leaf["leaf_id"]: 0 for leaf in leaves}
    for tb in {leaf["tan_beta"] for leaf in leaves}:
        for x in xs:
            for y in ys:
                counts[by_root[tb, root_index(x, low, high, root_n), root_index(y, low, high, root_n)]] += profiles
    return counts


def _mesh_row(leaf, source):
    return {"mesh_leaf_id": leaf["leaf_id"], "mesh_parent_id": leaf["parent_id"], "mesh_depth": leaf["depth"], "mesh_source": source,
            "mphi_min_GeV": leaf["mphi_min_GeV"], "mphi_max_GeV": leaf["mphi_max_GeV"],
            "Mbar_min_GeV": leaf["Mbar_min_GeV"], "Mbar_max_GeV": leaf["Mbar_max_GeV"],
            "mphi_center_GeV": leaf["mphi_center_GeV"], "Mbar_center_GeV": leaf["Mbar_center_GeV"]}


def _shard_valid(path):
    try:
        rows = _load_csv(path)
        return len(rows) == 1 and set(MESH_COLUMNS) <= set(rows[0])
    except (OSError, csv.Error):
        return False


def _failure(context, reason):
    row = {"schema_version": "dihiggs.point.v2", "producer": "DihiggsPointV2Evaluator", "campaign_id": context["campaign_id"],
           "run_id": context["run_id"], "point_id": "attempt_%s_p_%02d" % (context["mesh_leaf_id"].replace("/", "_"), context["profile_index"]),
           "yukawa_type": context["yukawa_type"], "mh_input_GeV": context["mh_input_GeV"], "mH_input_GeV": context["mH_input_GeV"],
           "mA_input_GeV": context["mA_input_GeV"], "mHp_input_GeV": context["mHp_input_GeV"],
           "sin_beta_minus_alpha_input": context["sin_beta_minus_alpha_input"], "tan_beta_input": context["tan_beta"],
           "M2_input_GeV2": context["M2_input_GeV2"], "m12_sq_input_GeV2": context["M2_input_GeV2"] / (context["tan_beta"] + 1 / context["tan_beta"]),
           "lambda6_input": context["lambda6_from_X"], "lambda7_input": context["lambda7_input"], "construction_ok": 0, "numerical_ok": 0,
           "theory_ok_v1": 0, "triple_ok_legacy": 0, "rejection_stage": "runner", "rejection_reason": reason, "profile_status": "evaluator_failed"}
    row.update(context); return row


def _run_profile(job):
    shard, leaf, context, cfg, executable, root, api = job
    if _shard_valid(shard):
        return _load_csv(shard)[0]
    M2Engine, ScanGrid, FixedParams = api
    canonical = shard.with_suffix(".canonical.csv")
    fixed = FixedParams(mA=context["mA_input_GeV"], mHp=context["mHp_input_GeV"],
                        sin_ba=float(cfg["physics"]["sin_beta_minus_alpha"]), tan_beta=context["tan_beta"],
                        lambda6=context["lambda6_from_X"], lambda7=float(cfg["physics"]["lambda7"]),
                        mh=float(cfg["physics"]["mh_GeV"]), yukawa_type=int(cfg["physics"]["yukawa_type"]))
    command = M2Engine(context["campaign_id"], context["run_id"]).build_command(
        executable, ScanGrid(context["mH_input_GeV"], context["mH_input_GeV"], 1, context["M2_input_GeV2"], context["M2_input_GeV2"], 1), fixed, canonical)
    try:
        process = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False, timeout=float(cfg["runtime"]["timeout_s"]))
        code = process.returncode
    except subprocess.TimeoutExpired:
        code = "timeout"
    if code == 0 and canonical.is_file():
        rows = _load_csv(canonical)
        row = rows[0] if len(rows) == 1 else _failure(context, "unexpected_canonical_row_count")
    else:
        row = _failure(context, "evaluator_returncode_%s" % code)
    row.update(_mesh_row(leaf, "adaptive")); row.update(context)
    _write_rows(shard, [row], list(dict.fromkeys(CANONICAL_COLUMNS + list(context) + MESH_COLUMNS + ["profile_status"])))
    canonical.unlink(missing_ok=True)
    return row


def _write_leaf_csv(path, leaves):
    _write_rows(path, leaves, LEAF_FIELDS + ["ix", "iy", "mesh_source"])


def _new_shard_paths(out):
    return sorted(path for path in out.glob("tanbeta_*/raw_shards/*/*.csv") if not path.name.endswith(".canonical.csv"))


def _count_new_rows(out):
    return sum(1 for _ in _new_shard_paths(out))


def _read_new_rows(out, leaf_ids=None):
    allowed = {leaf_id.replace("/", "__") for leaf_id in leaf_ids} if leaf_ids is not None else None
    paths = (path for path in _new_shard_paths(out) if allowed is None or path.parent.name in allowed)
    return [row for path in paths for row in _load_csv(path)]


def _consolidate_new_rows(out, output, fields):
    temporary = output.with_suffix(output.suffix + ".tmp")
    count = 0
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for path in _new_shard_paths(out):
            with path.open(newline="", encoding="utf-8") as source:
                for row in csv.DictReader(source):
                    writer.writerow(row); count += 1
    os.replace(temporary, output)
    return count


def _progress(done, cap, started, label="adaptive", baseline=0):
    elapsed = max(time.monotonic() - started, 1e-9)
    rate = max(done - baseline, 0) / elapsed
    fraction = min(1.0, done / cap) if cap else 1.0
    width = 28; filled = int(width * fraction)
    eta = (cap - done) / rate if rate > 0 and done < cap else 0.0
    eta_text = "n/a" if done == 0 else "%0.1f min" % (eta / 60)
    print("\r[%s%s] %s %d/%d (%.1f%%), %.1f/s, ETA-to-cap %s" % ("#" * filled, "." * (width - filled), label, done, cap, 100 * fraction, rate, eta_text), end="", flush=True)


def _load_config(config_path):
    path = Path(config_path).resolve(); cfg = yaml.safe_load(path.read_text())
    if not isinstance(cfg, dict) or cfg.get("schema_version") != "dhb.adaptive_m2_boundary.v1":
        raise ValueError("unsupported adaptive mesh config")
    root = (path.parent / cfg["dihiggs_root"]).resolve(); executable = (root / cfg["evaluator"]).resolve()
    if not executable.is_file(): raise ValueError("canonical evaluator missing: %s" % executable)
    cfg["seed"]["seed_raw_csv"] = str((path.parent / cfg["seed"]["raw_csv"]).resolve())
    cfg["seed"]["seed_manifest"] = str((path.parent / cfg["seed"]["manifest"]).resolve())
    return path, cfg, root, executable


def run(config_path, output_dir, smoke=False):
    config_path, cfg, dihiggs_root, executable = _load_config(config_path)
    if smoke:
        cfg = json.loads(json.dumps(cfg)); cfg["mesh"]["max_depth"] = min(1, int(cfg["mesh"]["max_depth"])); cfg["mesh"]["new_evaluation_cap"] = min(512, int(cfg["mesh"]["new_evaluation_cap"]))
        cfg["campaign_id"] += "_smoke"
    out = Path(output_dir).resolve() / cfg["campaign_id"]; out.mkdir(parents=True, exist_ok=True)
    state_path, seed_path = out / "mesh_state.json", out / "seed_profiled_points.csv"
    low, high, root_n = (float(cfg["mesh"][key]) for key in ("min_GeV", "max_GeV", "root_cells"))
    root_n = int(root_n); tbs = [float(value) for value in cfg["tan_beta_slices"]]
    if state_path.exists():
        state = json.loads(state_path.read_text()); leaves = state["leaves"]
    else:
        leaves = root_leaves(tbs, low, high, root_n)
        seed_manifest = json.loads(Path(cfg["seed"]["seed_manifest"]).read_text())
        expected = _seed_expected_counts(seed_manifest, leaves, low, high, root_n)
        seed_rows = _annotate_seed(_load_csv(cfg["seed"]["seed_raw_csv"]), leaves, low, high, root_n, expected)
        _write_rows(seed_path, seed_rows, list(seed_rows[0]) if seed_rows else CANONICAL_COLUMNS + MESH_COLUMNS)
        state = {"schema": "dhb.adaptive_m2_mesh.state.v1", "leaves": leaves}; _write_json(state_path, state)
    api = _canonical_api(dihiggs_root); profile = cfg["profile"]; envelope = profile["lambda6_hard_envelope"]
    max_depth, cap, n_profile = int(cfg["mesh"]["max_depth"]), int(cfg["mesh"]["new_evaluation_cap"]), int(profile["n_proposals"])
    progress_started, progress_baseline, progress_done = time.monotonic(), _count_new_rows(out), 0
    _progress(progress_baseline, cap, progress_started, baseline=progress_baseline)
    for depth in range(max_depth):
        targets = eligible_refinement_targets(leaves, depth, max_depth)
        if not targets: continue
        existing = _count_new_rows(out); cost = 4 * n_profile
        selected, pending = budgeted_targets(targets, existing, cap, n_profile)
        for leaf in pending: leaf["coverage_state"] = "pending_refinement"
        if not selected: break
        new_leaves = [child for leaf in selected for child in children(leaf, low, high, root_n)]
        leaves.extend(new_leaves); jobs = []
        for leaf in new_leaves:
            tb = leaf["tan_beta"]; x_spec = dict(profile["X_lambda6_times_tan_beta"])
            x_spec["min"] = max(float(x_spec["min"]), float(envelope["min"]) * tb); x_spec["max"] = min(float(x_spec["max"]), float(envelope["max"]) * tb)
            samples = _lhs("%s:%s" % (profile["seed"], format(tb, ".17g")), n_profile, {"X": x_spec, "Delta": profile["Delta_heavy_GeV"]})
            shard_dir = out / ("tanbeta_" + _tag(tb)) / "raw_shards" / leaf["leaf_id"].replace("/", "__"); shard_dir.mkdir(parents=True, exist_ok=True)
            for index, (x, delta) in enumerate(zip(samples["X"], samples["Delta"])):
                unclipped, lam6 = x / tb, min(max(x / tb, float(envelope["min"])), float(envelope["max"]))
                context = {"campaign_id": cfg["campaign_id"], "run_id": "%s_p_%02d" % (leaf["leaf_id"].replace("/", "_"), index), "profile_index": index,
                    "profile_seed": "%s:%s" % (profile["seed"], format(tb, ".17g")), "tan_beta": tb, "yukawa_type": int(cfg["physics"]["yukawa_type"]),
                    "mh_input_GeV": float(cfg["physics"]["mh_GeV"]), "mH_input_GeV": leaf["mphi_center_GeV"], "M2_input_GeV2": leaf["Mbar_center_GeV"] ** 2,
                    "mA_input_GeV": leaf["mphi_center_GeV"] + delta, "mHp_input_GeV": leaf["mphi_center_GeV"] + delta,
                    "sin_beta_minus_alpha_input": float(cfg["physics"]["sin_beta_minus_alpha"]), "lambda7_input": float(cfg["physics"]["lambda7"]),
                    "X_lambda6_times_tan_beta": x, "lambda6_from_X": lam6, "lambda6_clipped": int(lam6 != unclipped), "Delta_heavy_GeV": delta,
                    "mA_minus_mphi_GeV": delta, "mesh_leaf_id": leaf["leaf_id"], "mesh_parent_id": leaf["parent_id"], "mesh_depth": leaf["depth"], "mesh_source": "adaptive"}
                jobs.append((shard_dir / ("profile_%02d.csv" % index), leaf, context, cfg, executable, dihiggs_root, api))
        fresh_jobs = [job for job in jobs if not _shard_valid(job[0])]
        with ThreadPoolExecutor(max_workers=int(cfg["runtime"]["max_workers"])) as pool:
            for _ in pool.map(_run_profile, fresh_jobs):
                progress_done += 1
                if progress_done == len(fresh_jobs) or progress_done % 16 == 0:
                    _progress(progress_baseline + progress_done, cap, progress_started, "depth-%d" % depth, progress_baseline)
        new_rows = _read_new_rows(out, {leaf["leaf_id"] for leaf in new_leaves}); grouped = {leaf["leaf_id"]: [] for leaf in new_leaves}
        for row in new_rows:
            if row.get("mesh_leaf_id") in grouped: grouped[row["mesh_leaf_id"]].append(row)
        for leaf in new_leaves: _update_leaf(leaf, grouped[leaf["leaf_id"]], n_profile)
        state["leaves"] = leaves; _write_json(state_path, state)
    raw_fields = CANONICAL_COLUMNS + MESH_COLUMNS + ["profile_index", "profile_seed", "X_lambda6_times_tan_beta", "lambda6_from_X", "lambda6_clipped", "Delta_heavy_GeV", "mA_minus_mphi_GeV", "profile_status"]
    total_new_rows = _consolidate_new_rows(out, out / "raw_adaptive_points.csv", raw_fields)
    _write_leaf_csv(out / "mesh_leaves.csv", leaves)
    raw_parquet, parquet_reason = write_parquet(str(out / "raw_adaptive_points.csv"), str(out / "raw_adaptive_points.parquet"))
    state["leaves"] = leaves; _write_json(state_path, state)
    manifest = {"schema": "dhb.adaptive_m2_mesh.manifest.v1", "campaign_id": cfg["campaign_id"], "config_sha256": _sha256(config_path),
                "effective_config_sha256": hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
                "seed_artifacts": [{"path": cfg["seed"][key], "sha256": _sha256(cfg["seed"][key])} for key in ("seed_raw_csv", "seed_manifest")],
                "physics": cfg["physics"], "mass_convention_authority": _mass_convention(dihiggs_root, float(cfg["physics"]["mh_GeV"])),
                "canonical_engine": {"executable": str(executable), "dihiggs_git": _git(dihiggs_root), "boundary_git": _git(Path(__file__).resolve().parents[2])},
                "mesh": cfg["mesh"], "profile": profile, "new_evaluations": total_new_rows, "budget_remaining": cap - total_new_rows,
                "pending_leaf_ids": [leaf["leaf_id"] for leaf in leaves if leaf["active"] and leaf["coverage_state"] == "pending_refinement"],
                "terminal_leaf_ids": [leaf["leaf_id"] for leaf in leaves if leaf["active"] and leaf["depth"] >= max_depth],
                "stopped_at_depth": max((leaf["depth"] for leaf in leaves), default=0), "state": str(state_path), "raw_csv": str(out / "raw_adaptive_points.csv"),
                "seed_csv": str(seed_path), "parquet_written": raw_parquet, "parquet_skipped_reason": parquet_reason, "finished_at_utc": _now()}
    _write_json(out / "manifest.json", manifest)
    print()
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--config", required=True); parser.add_argument("--output-dir", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv); manifest = run(args.config, args.output_dir, args.smoke)
    print("[DHB] adaptive mesh: new_rows=%d pending=%d" % (manifest["new_evaluations"], len(manifest["pending_leaf_ids"])))
    return 0


if __name__ == "__main__": raise SystemExit(main())
