"""Bounded, resumable profile scan that consumes canonical ``dihiggs.point.v2`` rows."""

import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from .atlas import write_parquet


CANONICAL_COLUMNS = """schema_version producer producer_commit producer_dirty evaluator_api campaign_id run_id point_id yukawa_type yukawa_type_installed mh_input_GeV mH_input_GeV mA_input_GeV mHp_input_GeV sin_beta_minus_alpha_input tan_beta_input beta_input_rad M2_input_GeV2 m12_sq_input_GeV2 lambda6_input lambda7_input lambda1_reconstructed lambda2_reconstructed lambda3_reconstructed lambda4_reconstructed lambda5_reconstructed lambda6_reconstructed lambda7_reconstructed tan_beta_reconstructed m12_sq_reconstructed_GeV2 M2_reconstructed_GeV2 construction_ok numerical_ok rejection_stage rejection_reason positivity_reported_ok unitarity_ok perturbativity_ok stability_reported_ok stability_dependency_alias triple_ok_legacy theory_ok_v1 experimental_evaluated experimental_ok two_hdmc_hphiphi_real_GeV two_hdmc_hphiphi_imag_GeV g_physical_hphiphi_GeV g_physical_hphiphi_abs_GeV g_hH2H2_GeV width_bb_GeV width_cc_GeV width_tt_GeV width_tautau_GeV width_WW_GeV width_ZZ_GeV width_gammagamma_GeV width_Zgamma_GeV width_gg_GeV width_hh_GeV total_width_GeV width_unaccounted_GeV br_bb br_cc br_tt br_tautau br_WW br_ZZ br_gammagamma br_Zgamma br_gg br_hh width_ok ctau_mm""".split()
PROFILE_COLUMNS = [
    "outer_cell_id", "outer_mphi_index", "outer_M_index", "m_phi_GeV",
    "M_plot_GeV", "delta_M2_GeV2", "relative_delta_M2", "profile_index",
    "profile_seed", "X_lambda6_times_tan_beta", "lambda6_from_X", "lambda6_clipped",
    "Delta_heavy_GeV", "mA_minus_mphi_GeV", "profile_status",
]


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _theory_ok(row):
    try:
        return float(row.get("theory_ok_v1", "")) == 1.0
    except (TypeError, ValueError):
        return False


def _git(root):
    def run(args):
        result = subprocess.run(args, cwd=root, text=True, capture_output=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    return {"commit": run(["git", "rev-parse", "HEAD"]), "dirty": bool(run(["git", "status", "--porcelain"]))}


def _values(spec):
    lo, hi, n = float(spec["min"]), float(spec["max"]), int(spec["n"])
    if n < 1 or lo <= 0 or hi < lo:
        raise ValueError("invalid positive grid range")
    return [lo + (hi - lo) * i / (n - 1) if n > 1 else lo for i in range(n)]


def _lhs(seed, n, ranges):
    """Small deterministic LHS, deliberately using only the standard library."""
    rng = random.Random(str(seed))
    result = {}
    for name, spec in ranges.items():
        lo, hi = float(spec["min"]), float(spec["max"])
        if not (lo > 0 and hi >= lo):
            raise ValueError("invalid profile range for %s" % name)
        values = []
        for index in range(n):
            u = (index + rng.random()) / n
            if spec.get("scale") == "log":
                values.append(10 ** (math.log10(lo) + u * (math.log10(hi) - math.log10(lo))))
            else:
                values.append(lo + u * (hi - lo))
        rng.shuffle(values)
        result[name] = values
    return result


def _tag(value):
    return ("%.0e" % value).replace("+", "").replace("-", "m")


def _load(config_path):
    path = Path(config_path).resolve()
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or data.get("schema_version") != "dhb.profiled_m2_boundary.v1":
        raise ValueError("unsupported profiled M2 config")
    root = (path.parent / data["dihiggs_root"]).resolve()
    executable = (root / data["evaluator"]).resolve()
    if not executable.is_file():
        raise ValueError("canonical evaluator missing: %s" % executable)
    return path, data, root, executable


def _canonical_api(root):
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    from dihiggs.app.orchestrator.engines.m2 import M2Engine
    from dihiggs.app.orchestrator.grid import ScanGrid
    from dihiggs.app.orchestrator.models import FixedParams
    return M2Engine, ScanGrid, FixedParams


def _mass_convention(root, mh):
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    from dihiggs.app.orchestrator.physics_authority import convention_provenance
    return convention_provenance(source_commit=None, requested_mass_gev=mh)


def _shard_valid(path, expected_rows):
    if not path.is_file():
        return False
    try:
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            return reader.fieldnames and set(PROFILE_COLUMNS) <= set(reader.fieldnames) and sum(1 for _ in reader) == expected_rows
    except (OSError, csv.Error):
        return False


def _write_rows(path, rows, fieldnames):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _failure_rows(context, m2_values, reason):
    rows = []
    for m_index, m2 in enumerate(m2_values):
        row = dict(context)
        row.update({"schema_version": "dihiggs.point.v2", "producer": "DihiggsPointV2Evaluator",
                    "campaign_id": context["campaign_id"], "run_id": context["run_id"],
                    "point_id": "attempt_" + context["outer_cell_id"] + "_p_%02d" % context["profile_index"],
                    "yukawa_type": context["yukawa_type"], "mh_input_GeV": context["mh_input_GeV"],
                    "mH_input_GeV": context["mH_input_GeV"], "mA_input_GeV": context["mA_input_GeV"],
                    "mHp_input_GeV": context["mHp_input_GeV"], "sin_beta_minus_alpha_input": context["sin_beta_minus_alpha_input"],
                    "tan_beta_input": context["tan_beta"], "lambda6_input": context["lambda6_from_X"],
                    "lambda7_input": context["lambda7_input"], "M2_input_GeV2": m2,
                    "m12_sq_input_GeV2": m2 / (context["tan_beta"] + 1 / context["tan_beta"]),
                    "construction_ok": 0, "numerical_ok": 0, "theory_ok_v1": 0, "triple_ok_legacy": 0,
                    "rejection_stage": "runner", "rejection_reason": reason,
                    "profile_status": "evaluator_failed", "outer_M_index": context["outer_M_index"]})
        rows.append(row)
    return rows


def _augment(rows, context):
    result = []
    for row in rows:
        m2 = float(row["M2_input_GeV2"])
        mphi = float(row["mH_input_GeV"])
        merged = dict(row)
        merged.update(context)
        merged.update({
            "outer_M_index": context["outer_M_index"],
            "outer_cell_id": "tb_%s_mphi_%02d_M_%02d" % (_tag(context["tan_beta"]), context["outer_mphi_index"], context["outer_M_index"]),
            "m_phi_GeV": mphi, "M_plot_GeV": math.sqrt(m2),
            "delta_M2_GeV2": m2 - mphi * mphi,
            "relative_delta_M2": (m2 - mphi * mphi) / (mphi * mphi),
            "profile_status": "ok",
        })
        result.append(merged)
    return result


def _run_shard(job):
    """Run one exact (m_phi, Mbar, profile) task; one row is non-negotiable."""
    shard, context, mphi, m2, cfg, executable, dihiggs_root, api = job
    M2Engine, ScanGrid, FixedParams = api
    force = context.pop("force")
    if _shard_valid(shard, 1) and not force:
        with shard.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        return len(rows), sum(_theory_ok(row) for row in rows)
    canonical = shard.with_suffix(".canonical.csv")
    fixed = FixedParams(mA=mphi + context["Delta_heavy_GeV"], mHp=mphi + context["Delta_heavy_GeV"],
                        sin_ba=float(cfg["physics"]["sin_beta_minus_alpha"]), tan_beta=context["tan_beta"],
                        lambda6=context["lambda6_from_X"], lambda7=float(cfg["physics"]["lambda7"]),
                        mh=float(cfg["physics"]["mh_GeV"]), yukawa_type=int(cfg["physics"]["yukawa_type"]))
    grid = ScanGrid(mphi, mphi, 1, m2, m2, 1)
    engine = M2Engine(cfg["campaign_id"], "tb_%s_p_%02d_m_%02d_M_%02d" % (_tag(context["tan_beta"]), context["profile_index"], context["outer_mphi_index"], context["outer_M_index"]))
    command = engine.build_command(executable, grid, fixed, canonical)
    try:
        proc = subprocess.run(command, cwd=dihiggs_root, text=True, capture_output=True, check=False, timeout=float(cfg["runtime"]["timeout_s"]))
        stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, returncode = exc.stdout or "", exc.stderr or "", "timeout"
    stdout = stdout.decode() if isinstance(stdout, bytes) else stdout
    stderr = stderr.decode() if isinstance(stderr, bytes) else stderr
    log_dir = shard.parents[1] / "logs"
    (log_dir / (shard.stem + ".stdout.log")).write_text(stdout)
    (log_dir / (shard.stem + ".stderr.log")).write_text(stderr)
    if returncode == 0 and canonical.is_file():
        with canonical.open(newline="") as handle:
            rows = _augment(list(csv.DictReader(handle)), context)
        if len(rows) != 1:
            rows = _failure_rows(context, [m2], "unexpected_canonical_row_count")
    else:
        rows = _failure_rows(context, [m2], "evaluator_returncode_%s" % returncode)
    _write_rows(shard, rows, CANONICAL_COLUMNS + PROFILE_COLUMNS)
    canonical.unlink(missing_ok=True)
    return len(rows), sum(_theory_ok(row) for row in rows)


def _consolidate(shards, output):
    rows = []
    for shard in sorted(shards):
        with shard.open(newline="") as handle:
            rows.extend(csv.DictReader(handle))
    _write_rows(output, rows, CANONICAL_COLUMNS + PROFILE_COLUMNS)
    return len(rows)


def run(config_path, output_dir, smoke=False, only_tan_beta=None, force=False):
    config_path, cfg, dihiggs_root, executable = _load(config_path)
    M2Engine, ScanGrid, FixedParams = _canonical_api(dihiggs_root)
    mass_convention = _mass_convention(dihiggs_root, float(cfg["physics"]["mh_GeV"]))
    if smoke:
        cfg = json.loads(json.dumps(cfg))
        cfg["outer_grid"]["m_phi_GeV"]["n"] = 4
        cfg["outer_grid"]["M_plot_GeV"]["n"] = 4
        cfg["profile"]["n_proposals"] = 4
        cfg["campaign_id"] += "_smoke"
    mphi_values = _values(cfg["outer_grid"]["m_phi_GeV"])
    m_values = _values(cfg["outer_grid"]["M_plot_GeV"])
    m2_values = [value * value for value in m_values]
    if any(b <= a for a, b in zip(m2_values, m2_values[1:])):
        raise ValueError("M_plot grid must be strictly increasing")
    out = Path(output_dir).resolve() / cfg["campaign_id"]
    out.mkdir(parents=True, exist_ok=True)
    tan_betas = [float(x) for x in cfg["tan_beta_slices"]]
    if only_tan_beta is not None:
        tan_betas = [tb for tb in tan_betas if tb == float(only_tan_beta)]
        if not tan_betas:
            raise ValueError("requested tan(beta) is not in config")
    started = _now()
    all_shards, slice_summary = [], []
    for tb in tan_betas:
        profile = cfg["profile"]
        envelope = profile["lambda6_hard_envelope"]
        x_spec = dict(profile["X_lambda6_times_tan_beta"])
        x_spec["min"] = max(float(x_spec["min"]), float(envelope["min"]) * tb)
        x_spec["max"] = min(float(x_spec["max"]), float(envelope["max"]) * tb)
        if x_spec["min"] > x_spec["max"]:
            raise ValueError("empty X envelope at tan(beta)=%s" % tb)
        seed = "%s:%s" % (profile["seed"], format(tb, ".17g"))
        samples = _lhs(seed, int(profile["n_proposals"]), {"X": x_spec, "Delta": profile["Delta_heavy_GeV"]})
        tb_dir = out / ("tanbeta_" + _tag(tb))
        shard_dir, log_dir = tb_dir / "raw_shards", tb_dir / "logs"
        shard_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        jobs = []
        slice_started = time.monotonic()
        for m_index, mphi in enumerate(mphi_values):
            for p_index, (x, delta) in enumerate(zip(samples["X"], samples["Delta"])):
                lam6_unclipped = x / tb
                lam6 = min(max(lam6_unclipped, float(envelope["min"])), float(envelope["max"]))
                for M_index, m2 in enumerate(m2_values):
                    shard = shard_dir / ("mphi_%02d_M_%02d_profile_%02d.csv" % (m_index, M_index, p_index))
                    outer_cell_id = "tb_%s_mphi_%02d_M_%02d" % (_tag(tb), m_index, M_index)
                    context = {"outer_mphi_index": m_index, "outer_M_index": M_index, "outer_cell_id": outer_cell_id,
                           "tan_beta": tb, "profile_index": p_index, "campaign_id": cfg["campaign_id"],
                           "run_id": "tb_%s_p_%02d_m_%02d_M_%02d" % (_tag(tb), p_index, m_index, M_index),
                           "yukawa_type": int(cfg["physics"]["yukawa_type"]), "mh_input_GeV": float(cfg["physics"]["mh_GeV"]),
                           "mH_input_GeV": mphi, "mA_input_GeV": mphi + delta, "mHp_input_GeV": mphi + delta,
                           "sin_beta_minus_alpha_input": float(cfg["physics"]["sin_beta_minus_alpha"]),
                           "lambda7_input": float(cfg["physics"]["lambda7"]), "profile_seed": seed,
                           "X_lambda6_times_tan_beta": x, "lambda6_from_X": lam6,
                           "lambda6_clipped": int(lam6 != lam6_unclipped), "Delta_heavy_GeV": delta,
                           "mA_minus_mphi_GeV": delta, "force": force}
                    jobs.append((shard, context, mphi, m2, cfg, executable, dihiggs_root, (M2Engine, ScanGrid, FixedParams)))
        completed = survivors = 0
        chunk_size = int(cfg["runtime"].get("chunk_size", 100))
        workers = int(cfg["runtime"].get("max_workers", 1))
        for start in range(0, len(jobs), chunk_size):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for count, passed in pool.map(_run_shard, jobs[start:start + chunk_size]):
                    completed += count
                    survivors += passed
        shards = [path for path in shard_dir.glob("*.csv") if not path.name.endswith(".canonical.csv")]
        all_shards.extend(shards)
        raw_csv = tb_dir / "raw_profiled_points.csv"
        _consolidate(shards, raw_csv)
        counts = {}
        with raw_csv.open(newline="") as handle:
            for row in csv.DictReader(handle):
                key = row.get("rejection_stage", "")
                counts[key] = counts.get(key, 0) + 1
        elapsed = time.monotonic() - slice_started
        summary = {"tan_beta": tb, "attempted": completed, "theory_survivors": survivors,
                   "elapsed_s": elapsed, "points_per_s": completed / max(elapsed, 1e-12),
                   "dominant_rejection_stage": max(counts, key=counts.get) if counts else "", "raw_csv": str(raw_csv)}
        slice_summary.append(summary)
        _write_slice_manifest(tb_dir / "slice_manifest.json", summary)
    # Include existing completed slices so a one-slice resume leaves a complete campaign dataset.
    all_shards = [path for path in out.glob("tanbeta_*/raw_shards/*.csv") if not path.name.endswith(".canonical.csv")]
    completed_slices = []
    for path in sorted(out.glob("tanbeta_*/slice_manifest.json")):
        with path.open(encoding="utf-8") as handle:
            completed_slices.append(json.load(handle))
    raw_csv = out / "raw_profiled_points.csv"
    total = _consolidate(all_shards, raw_csv)
    parquet_written, parquet_reason = write_parquet(str(raw_csv), str(out / "raw_profiled_points.parquet"))
    manifest = {"schema_version": "dhb.profiled_m2_boundary.manifest.v1", "campaign_id": cfg["campaign_id"],
                "config_path": str(config_path), "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
                "physics": cfg["physics"], "mass_convention_authority": mass_convention, "outer_grid": cfg["outer_grid"], "M_plot_definition": "sqrt(M2_input_GeV2); derived plotting coordinate, not canonical input",
                "M_grid_note": "M_plot nodes are linear in configured Mbar and each is passed as its exact squared canonical M2 input", "profile": cfg["profile"],
                "effective_X_envelopes": [{"tan_beta": tb, "min": max(float(cfg["profile"]["X_lambda6_times_tan_beta"]["min"]), float(cfg["profile"]["lambda6_hard_envelope"]["min"]) * tb), "max": min(float(cfg["profile"]["X_lambda6_times_tan_beta"]["max"]), float(cfg["profile"]["lambda6_hard_envelope"]["max"]) * tb)} for tb in [float(x) for x in cfg["tan_beta_slices"]]],
                "nuisance_contract": {"mA_equals_mHp": True, "mA_definition": "m_phi + Delta_heavy", "Delta_source": "dihiggs/docs/contracts/high_mass_campaign_template.yaml stage_1 candidate values [150,300,500], status not_launched; bounded diagnostic choice"},
                "canonical_engine": {"adapter": "dihiggs.app.orchestrator.engines.m2.M2Engine", "executable": str(executable), "dihiggs_git": _git(dihiggs_root), "boundary_git": _git(Path(__file__).resolve().parents[2])},
                "started_at_utc": started, "finished_at_utc": _now(), "slice_summary": completed_slices, "raw_csv": str(raw_csv), "n_rows": total,
                "parquet_written": parquet_written, "parquet_skipped_reason": parquet_reason}
    manifest_path = out / "manifest.json"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, manifest_path)
    return manifest


def _write_slice_manifest(path, summary):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--smoke", action="store_true", help="4x4 outer grid and four profile proposals")
    parser.add_argument("--tan-beta", type=float, default=None, help="resume/run one configured slice")
    parser.add_argument("--force", action="store_true", help="replace valid shards")
    args = parser.parse_args(argv)
    manifest = run(args.config, args.output_dir, args.smoke, args.tan_beta, args.force)
    print("[DHB] profiled M2 scan: rows=%s manifest=%s" % (manifest["n_rows"], Path(args.output_dir).resolve() / manifest["campaign_id"] / "manifest.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
