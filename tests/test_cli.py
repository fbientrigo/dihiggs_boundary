import csv
import json
import math
import os

import pytest

from dhb import enrich, schema


class FakeRunner:
    """Replaces dhb.runner.HbhsRunner in CLI tests."""

    def __init__(self, hb_dataset, hs_dataset, modules=None):
        self.hb_dataset = hb_dataset
        self.hs_dataset = hs_dataset
        self.HP = object()
        self._sm_chi2 = 100.0
        self.calls = 0

    def run_point(self, pred):
        self.calls += 1
        return {
            "hb_allowed": True,
            "hb_max_obsratio": 0.5,
            "hb_limiting_particle": "h1",
            "hb_limiting_process": "LHC13 fake process",
            "hs_chi2": 101.0,
            "hs_nobs": 159,
            "hs_chi2_sm_ref": 100.0,
            "hs_delta_chi2": 1.0,
        }


@pytest.fixture
def patched_cli(monkeypatch):
    monkeypatch.setattr(enrich.runner, "HbhsRunner", FakeRunner)
    monkeypatch.setattr(
        enrich.adapter,
        "build_predictions",
        lambda row, HP: (object(), {"width_rel_diff_max": 0.01}),
    )
    return enrich


def run_cli(patched_cli, tmp_path, sample_csv_path, extra_args=()):
    output = tmp_path / "enriched.csv"
    code = patched_cli.run(
        [
            "--input",
            str(sample_csv_path),
            "--output",
            str(output),
            "--hb-dataset",
            "/fake/hb",
            "--hs-dataset",
            "/fake/hs",
        ]
        + list(extra_args)
    )
    return code, output


def test_cli_appends_columns_and_passes_rows_through(
    patched_cli, tmp_path, sample_csv_path, sample_rows
):
    code, output = run_cli(patched_cli, tmp_path, sample_csv_path)
    assert code == 0
    with open(output, newline="") as fh:
        reader = csv.DictReader(fh)
        out_rows = list(reader)
        assert reader.fieldnames[-len(schema.ENRICHMENT_COLUMNS):] == (
            schema.ENRICHMENT_COLUMNS
        )
    assert len(out_rows) == len(sample_rows)
    for src, out in zip(sample_rows, out_rows):
        assert out["point_id"] == src["point_id"]
        assert out["theory_ok"] == src["theory_ok"]
        if src["theory_ok"] == "1":
            assert out["enrich_status"] == "ok"
            assert out["hb_allowed"] == "1"
            assert out["exp_ok"] == "1"
            assert float(out["hs_delta_chi2"]) == 1.0
        else:
            assert out["enrich_status"] == "skipped_theory_fail"
            assert out["hb_allowed"] == ""
            assert out["exp_ok"] == ""
            assert math.isnan(float(out["hs_chi2"]))


def test_cli_writes_manifest_and_no_tmp(patched_cli, tmp_path, sample_csv_path):
    code, output = run_cli(patched_cli, tmp_path, sample_csv_path)
    assert code == 0
    assert not os.path.exists(str(output) + ".tmp")
    manifest_path = tmp_path / "hbhs_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["stage"] == "hbhs_enrichment"
    assert manifest["enriched_schema_version"] == schema.ENRICHED_SCHEMA_VERSION
    assert manifest["counts"]["total"] == 5
    assert manifest["counts"]["enriched"] == 3
    assert manifest["counts"]["skipped"] == 2
    assert manifest["counts"]["errors"] == 0


def test_cli_adapter_error_is_recorded_not_fatal(
    patched_cli, tmp_path, sample_csv_path, monkeypatch
):
    def boom(row, HP):
        raise RuntimeError("bad, row")

    monkeypatch.setattr(enrich.adapter, "build_predictions", boom)
    code, output = run_cli(patched_cli, tmp_path, sample_csv_path)
    assert code == 0
    with open(output, newline="") as fh:
        rows = list(csv.DictReader(fh))
    statuses = [r["enrich_status"] for r in rows if r["theory_ok"] == "1"]
    assert all(s.startswith("adapter_error:") for s in statuses)
    # the error text must not corrupt the CSV (no commas)
    assert all("," not in s for s in statuses)


def test_cli_rejects_input_without_block_columns(patched_cli, tmp_path):
    bad_input = tmp_path / "bad.csv"
    bad_input.write_text("point_id,theory_ok\np1,1\n")
    code, _ = run_cli(patched_cli, tmp_path / "sub", bad_input)
    assert code == 2
