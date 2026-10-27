"""Random outer-cell exploration using the unchanged canonical evaluator."""

import argparse
import csv
import hashlib
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from .adaptive_m2_mesh import (
    CANONICAL_COLUMNS, MESH_COLUMNS, _canonical_api, _git, _lhs, _mass_convention,
    _new_leaf, _now, _run_profile, _shard_valid, _tag, _write_json, write_parquet,
)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _paths(out):
    return sorted(path for path in out.glob("tanbeta_*/raw_shards/*/*.csv") if not path.name.endswith(".canonical.csv"))


def _count(out):
    return sum(1 for _ in _paths(out))


def _consolidate(out, output, fields):
    temporary = output.with_suffix(output.suffix + ".tmp")
    count = 0
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for path in _paths(out):
            with path.open(newline="", encoding="utf-8") as source:
                for row in csv.DictReader(source):
                    writer.writerow(row); count += 1
    os.replace(temporary, output)
    return count


def _occupied(state, low, high, root_n, depth):
    """Reserve depth-cell centres already evaluated by the adaptive campaign."""
    scale = root_n * (2 ** depth); occupied = set()
    for leaf in state.get("leaves", []):
        if not leaf.get("profile_count"):
            continue
        tb = float(leaf["tan_beta"])
        ix = min(scale - 1, max(0, int((float(leaf["mphi_center_GeV"]) - low) * scale / (high - low))))
        iy = min(scale - 1, max(0, int((float(leaf["Mbar_center_GeV"]) - low) * scale / (high - low))))
        occupied.add((tb, ix, iy))
    return occupied


def _random_leaves(tan_betas, low, high, root_n, depth, count, seed, occupied):
    scale = root_n * (2 ** depth); rng = random.Random(seed); leaves = []
    per_slice, remainder = divmod(count, len(tan_betas))
    for index, tb in enumerate(tan_betas):
        target = per_slice + (index < remainder); chosen = []; used = set()
        # Sample an oversize deterministic pool; retries are unnecessary at this density.
        for token in rng.sample(range(scale * scale), target * 3 + 32):
            x, y = divmod(token, scale)
            if (tb, x, y) in occupied or (x, y) in used:
                continue
            used.add((x, y)); chosen.append(_new_leaf(tb, depth, x, y, low, high, root_n, "", "random_exploration"))
            if len(chosen) == target:
                break
        if len(chosen) != target:
            raise RuntimeError("not enough unoccupied random exploration cells")
        leaves.extend(chosen)
    return leaves


def _progress(done, total, started):
    elapsed = max(time.monotonic() - started, 1e-9); rate = done / elapsed
    fraction = min(1.0, done / total) if total else 1.0; width = 28; filled = int(width * fraction)
    eta = (total - done) / rate if rate and done < total else 0.0
    print("\r[%s%s] exploration %d/%d (%.1f%%), %.1f/s, ETA %0.1f min" % ("#" * filled, "." * (width - filled), done, total, 100 * fraction, rate, eta / 60), end="", flush=True)


def _config(path):
    path = Path(path).resolve(); cfg = yaml.safe_load(path.read_text())
    if cfg.get("schema_version") != "dhb.adaptive_m2_exploration.v1":
        raise ValueError("unsupported exploration config")
    root = (path.parent / cfg["dihiggs_root"]).resolve(); executable = (root / cfg["evaluator"]).resolve()
    if not executable.is_file(): raise ValueError("canonical evaluator missing: %s" % executable)
    cfg["seed"]["adaptive_manifest"] = str((path.parent / cfg["seed"]["adaptive_manifest"]).resolve())
    cfg["seed"]["adaptive_state"] = str((path.parent / cfg["seed"]["adaptive_state"]).resolve())
    return path, cfg, root, executable


def run(config_path, output_dir):
    config_path, cfg, dihiggs_root, executable = _config(config_path)
    out = Path(output_dir).resolve() / cfg["campaign_id"]; out.mkdir(parents=True, exist_ok=True)
    low, high = float(cfg["mesh"]["min_GeV"]), float(cfg["mesh"]["max_GeV"])
    root_n, depth, cap = int(cfg["mesh"]["root_cells"]), int(cfg["mesh"]["exploration_depth"]), int(cfg["mesh"]["new_evaluation_cap"])
    profile = cfg["profile"]; n_profile = int(profile["n_proposals"]); total_leaves = cap // n_profile
    state_path = out / "exploration_state.json"
    if state_path.exists():
        leaves = json.loads(state_path.read_text())["leaves"]
    else:
        base_state = json.loads(Path(cfg["seed"]["adaptive_state"]).read_text())
        leaves = _random_leaves([float(x) for x in cfg["tan_beta_slices"]], low, high, root_n, depth, total_leaves, int(profile["seed"]), _occupied(base_state, low, high, root_n, depth))
        _write_json(state_path, {"schema": "dhb.adaptive_m2_exploration.state.v1", "leaves": leaves})
    api = _canonical_api(dihiggs_root); envelope = profile["lambda6_hard_envelope"]
    started = time.monotonic(); done = _count(out); _progress(done, cap, started)
    for start in range(0, len(leaves), int(cfg["runtime"]["leaf_chunk"])):
        chunk = leaves[start:start + int(cfg["runtime"]["leaf_chunk"])]
        jobs = []
        for leaf in chunk:
            tb = leaf["tan_beta"]; x_spec = dict(profile["X_lambda6_times_tan_beta"])
            x_spec["min"] = max(float(x_spec["min"]), float(envelope["min"]) * tb); x_spec["max"] = min(float(x_spec["max"]), float(envelope["max"]) * tb)
            samples = _lhs("%s:%s" % (profile["seed"], format(tb, ".17g")), n_profile, {"X": x_spec, "Delta": profile["Delta_heavy_GeV"]})
            shard_dir = out / ("tanbeta_" + _tag(tb)) / "raw_shards" / leaf["leaf_id"].replace("/", "__"); shard_dir.mkdir(parents=True, exist_ok=True)
            for index, (x, delta) in enumerate(zip(samples["X"], samples["Delta"])):
                unclipped, lam6 = x / tb, min(max(x / tb, float(envelope["min"])), float(envelope["max"]))
                context = {"campaign_id": cfg["campaign_id"], "run_id": "%s_p_%02d" % (leaf["leaf_id"], index), "profile_index": index,
                    "profile_seed": "%s:%s" % (profile["seed"], format(tb, ".17g")), "tan_beta": tb, "yukawa_type": int(cfg["physics"]["yukawa_type"]),
                    "mh_input_GeV": float(cfg["physics"]["mh_GeV"]), "mH_input_GeV": leaf["mphi_center_GeV"], "M2_input_GeV2": leaf["Mbar_center_GeV"] ** 2,
                    "mA_input_GeV": leaf["mphi_center_GeV"] + delta, "mHp_input_GeV": leaf["mphi_center_GeV"] + delta,
                    "sin_beta_minus_alpha_input": float(cfg["physics"]["sin_beta_minus_alpha"]), "lambda7_input": float(cfg["physics"]["lambda7"]),
                    "X_lambda6_times_tan_beta": x, "lambda6_from_X": lam6, "lambda6_clipped": int(lam6 != unclipped), "Delta_heavy_GeV": delta,
                    "mA_minus_mphi_GeV": delta, "mesh_leaf_id": leaf["leaf_id"], "mesh_parent_id": "", "mesh_depth": leaf["depth"], "mesh_source": "random_exploration"}
                jobs.append((shard_dir / ("profile_%02d.csv" % index), leaf, context, cfg, executable, dihiggs_root, api))
        fresh = [job for job in jobs if not _shard_valid(job[0])]
        with ThreadPoolExecutor(max_workers=int(cfg["runtime"]["max_workers"])) as pool:
            for _ in pool.map(_run_profile, fresh):
                done += 1
                if done % 16 == 0 or done == cap: _progress(done, cap, started)
    fields = CANONICAL_COLUMNS + MESH_COLUMNS + ["profile_index", "profile_seed", "X_lambda6_times_tan_beta", "lambda6_from_X", "lambda6_clipped", "Delta_heavy_GeV", "mA_minus_mphi_GeV", "profile_status"]
    total = _consolidate(out, out / "raw_exploration_points.csv", fields)
    with (out / "exploration_leaves.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(leaves[0]), extrasaction="ignore", lineterminator="\n"); writer.writeheader(); writer.writerows(leaves)
    raw_parquet, parquet_reason = write_parquet(str(out / "raw_exploration_points.csv"), str(out / "raw_exploration_points.parquet"))
    manifest = {"schema": "dhb.adaptive_m2_exploration.manifest.v1", "campaign_id": cfg["campaign_id"], "config_sha256": _sha256(config_path),
        "base_adaptive_manifest": {"path": cfg["seed"]["adaptive_manifest"], "sha256": _sha256(cfg["seed"]["adaptive_manifest"])}, "base_adaptive_state": {"path": cfg["seed"]["adaptive_state"], "sha256": _sha256(cfg["seed"]["adaptive_state"])},
        "physics": cfg["physics"], "mesh": cfg["mesh"], "profile": profile, "new_evaluations": total,
        "canonical_engine": {"executable": str(executable), "dihiggs_git": _git(dihiggs_root), "boundary_git": _git(Path(__file__).resolve().parents[2])},
        "mass_convention_authority": _mass_convention(dihiggs_root, float(cfg["physics"]["mh_GeV"])), "raw_csv": str(out / "raw_exploration_points.csv"), "parquet_written": raw_parquet, "parquet_skipped_reason": parquet_reason, "finished_at_utc": _now()}
    _write_json(out / "manifest.json", manifest); print(); return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--config", required=True); parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv); manifest = run(args.config, args.output_dir); print("[DHB] exploration: rows=%d" % manifest["new_evaluations"]); return 0


if __name__ == "__main__": raise SystemExit(main())
