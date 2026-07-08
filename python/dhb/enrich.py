"""CLI: enrich an evaluate_point CSV with HiggsBounds/HiggsSignals results.

Usage:
    python -m dhb.enrich --input runs/<id>/evaluate_point.csv \
        --output runs/<id>/hbhs_enriched.csv \
        [--config configs/theory_atlas_v0.yaml] \
        [--hb-dataset PATH] [--hs-dataset PATH] [--all-points]

Input rows are passed through unchanged; the enrichment columns
(schema.ENRICHMENT_COLUMNS) are appended. Only rows with theory_ok=1 and a
valid HBHS input block are evaluated (all rows with a valid block when
--all-points is given); other rows get enrich_status=skipped_theory_fail.
The output is written atomically (.tmp -> rename) and accompanied by
<output_dir>/hbhs_manifest.json.
"""

import argparse
import csv
import datetime
import json
import os
import subprocess
import sys

from . import adapter, classify, contracts, runner, schema


def _nan_result():
    result = {}
    for column in schema.ENRICHMENT_COLUMNS:
        result[column] = float("nan")
    result["hb_allowed"] = ""
    result["hb_limiting_particle"] = ""
    result["hb_limiting_process"] = ""
    result["exp_ok"] = ""
    return result


def _format_value(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return repr(value)
    return value


def _git_commit(repo_dir):
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except OSError:
        return "unknown"


def _higgstools_version():
    try:
        from importlib.metadata import version

        return version("HiggsTools")
    except Exception:
        return "unknown"


def enrich_rows(rows, hbhs_runner, settings, all_points=False):
    """Generator: yields each input row dict extended with the enrichment
    columns. `rows` is an iterable of csv.DictReader rows."""
    HP = hbhs_runner.HP
    for row in rows:
        result = _nan_result()
        eligible = schema.parse_flag(row, "hbhs_block_ok") and (
            all_points or schema.parse_flag(row, "theory_ok")
        )
        if not eligible:
            result["enrich_status"] = schema.ENRICH_STATUS_SKIPPED
        else:
            try:
                pred, diagnostics = adapter.build_predictions(row, HP)
                result.update(hbhs_runner.run_point(pred))
                result["width_rel_diff_max"] = diagnostics["width_rel_diff_max"]
                result["exp_ok"] = classify.exp_ok(
                    result["hb_allowed"],
                    result["hs_delta_chi2"],
                    settings["hs_delta_chi2_max"],
                )
                result["enrich_status"] = schema.ENRICH_STATUS_OK
            except Exception as exc:  # keep the campaign row, record failure
                result = _nan_result()
                result["enrich_status"] = "adapter_error:%s" % (
                    str(exc).replace(",", ";").replace("\n", " ")
                )
        merged = dict(row)
        for column in schema.ENRICHMENT_COLUMNS:
            merged[column] = _format_value(result[column])
        yield merged


def run(argv=None):
    parser = argparse.ArgumentParser(
        description="Enrich an evaluate_point CSV with HiggsBounds/"
        "HiggsSignals results (HiggsTools)."
    )
    parser.add_argument("--input", required=True, help="evaluate_point CSV")
    parser.add_argument("--output", required=True, help="enriched CSV to write")
    parser.add_argument(
        "--config",
        default="",
        help="run config yaml with an evaluation.experiment_higgstools block",
    )
    parser.add_argument(
        "--hb-dataset",
        default=os.environ.get("DHB_HB_DATASET_ROOT", ""),
        help="HiggsBounds dataset root (default: $DHB_HB_DATASET_ROOT)",
    )
    parser.add_argument(
        "--hs-dataset",
        default=os.environ.get("DHB_HS_DATASET_ROOT", ""),
        help="HiggsSignals dataset root (default: $DHB_HS_DATASET_ROOT)",
    )
    parser.add_argument(
        "--all-points",
        action="store_true",
        help="enrich every row with a valid HBHS block, not only theory_ok",
    )
    args = parser.parse_args(argv)

    if not args.hb_dataset or not args.hs_dataset:
        parser.error(
            "HB/HS dataset paths missing: pass --hb-dataset/--hs-dataset or "
            "source scripts/setup_env.sh"
        )

    settings = classify.load_experiment_config(args.config)
    hbhs_runner = runner.HbhsRunner(args.hb_dataset, args.hs_dataset)

    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tmp_output = args.output + ".tmp"
    counts = {"total": 0, "enriched": 0, "skipped": 0, "errors": 0}
    with open(args.input, newline="") as infile:
        reader = csv.DictReader(infile)
        if reader.fieldnames is None:
            print("[DHB][FAIL] Empty input CSV: %s" % args.input, file=sys.stderr)
            return 2
        # Required input columns come from the theory contract (single source
        # of truth), not an inline list, so enrich and dhb.contracts stay in
        # sync. This is exactly ["point_id", "theory_ok"] + HBHS_BLOCK_COLUMNS.
        missing = schema.missing_columns(
            reader.fieldnames, contracts.THEORY["required_columns"]
        )
        if missing:
            print(
                "[DHB][FAIL] Input is missing HBHS block columns (rebuild "
                "evaluate_point?): %s" % ",".join(missing[:5]),
                file=sys.stderr,
            )
            return 2
        fieldnames = list(reader.fieldnames) + schema.ENRICHMENT_COLUMNS
        with open(tmp_output, "w", newline="") as outfile:
            writer = csv.DictWriter(
                outfile, fieldnames=fieldnames, lineterminator="\n"
            )
            writer.writeheader()
            for merged in enrich_rows(
                reader, hbhs_runner, settings, all_points=args.all_points
            ):
                writer.writerow(merged)
                counts["total"] += 1
                status = merged["enrich_status"]
                if status == schema.ENRICH_STATUS_OK:
                    counts["enriched"] += 1
                elif status == schema.ENRICH_STATUS_SKIPPED:
                    counts["skipped"] += 1
                else:
                    counts["errors"] += 1
    os.replace(tmp_output, args.output)

    manifest = {
        "stage": "hbhs_enrichment",
        "enriched_schema_version": schema.ENRICHED_SCHEMA_VERSION,
        "theory_schema_version": schema.THEORY_SCHEMA_VERSION,
        "input": os.path.abspath(args.input),
        "output": os.path.abspath(args.output),
        "hb_dataset": os.path.abspath(args.hb_dataset),
        "hs_dataset": os.path.abspath(args.hs_dataset),
        "config": os.path.abspath(args.config) if args.config else "",
        "settings": settings,
        "hs_chi2_sm_ref": hbhs_runner._sm_chi2,
        "counts": counts,
        "higgstools_version": _higgstools_version(),
        "dhb_version": __import__("dhb").__version__,
        "git_commit": _git_commit(os.path.dirname(os.path.abspath(__file__))),
        "started_at_utc": started_at,
        "finished_at_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
    }
    manifest_path = os.path.join(
        os.path.dirname(os.path.abspath(args.output)), "hbhs_manifest.json"
    )
    tmp_manifest = manifest_path + ".tmp"
    with open(tmp_manifest, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_manifest, manifest_path)

    print(
        "[DHB] hbhs enrichment completed: total=%(total)d enriched=%(enriched)d "
        "skipped=%(skipped)d errors=%(errors)d" % counts
    )
    print("[DHB] output: %s" % args.output)
    print("[DHB] manifest: %s" % manifest_path)
    return 0


if __name__ == "__main__":
    sys.exit(run())
