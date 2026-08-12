import csv
import json

from dhb import atlas_v1, llp_signal, schema


def base_row(**overrides):
    row = {
        "theory_ok": "1",
        "hb_allowed": "1",
        "hs_delta_chi2": "1.0",
        "exp_ok": "1",
        "enrich_status": schema.ENRICH_STATUS_OK,
    }
    for column in llp_signal.SIGNAL_COLUMNS:
        row[column] = ""
    row.update(
        {
            "llp_signal_schema_version": llp_signal.SIGNAL_SCHEMA_VERSION,
            "signal_domain_status": llp_signal.DOMAIN_SUPPORTED,
            "signal_status": llp_signal.STATUS_COMPUTED_VALIDATED,
            "signal_calibration_version": "test_v1",
            "signal_calibration_status": "VALIDATED",
            "Trackless_Aeff": "0.2",
            "sigma_visible_fb": "0.1",
            "N_expected": "1.5",
            "S95": "3.0",
            "N_over_S95": "0.5",
            "threshold_class": "BELOW",
        }
    )
    row.update(overrides)
    return row


def test_allowed_signal_below():
    verdict = atlas_v1.classify_row(base_row())
    assert verdict["region_class"] == "allowed_signal_below"
    assert verdict["is_allowed"] is True
    assert verdict["is_signal_domain_supported"] is True
    assert verdict["is_signal_calibration_validated"] is True
    assert verdict["is_signal_at_or_above_S95"] is False


def test_allowed_signal_near_threshold():
    verdict = atlas_v1.classify_row(
        base_row(threshold_class="NEAR", N_expected="3.0", N_over_S95="1.0")
    )
    assert verdict["region_class"] == "allowed_signal_near_threshold"
    assert verdict["is_signal_at_or_above_S95"] is True


def test_allowed_signal_above():
    verdict = atlas_v1.classify_row(
        base_row(threshold_class="ABOVE", N_expected="6.0", N_over_S95="2.0")
    )
    assert verdict["region_class"] == "allowed_signal_above"
    assert verdict["is_signal_at_or_above_S95"] is True


def test_outside_recast_domain_is_separate_from_theory_and_hbhs():
    verdict = atlas_v1.classify_row(
        base_row(
            signal_domain_status=llp_signal.DOMAIN_OUTSIDE,
            threshold_class="",
            N_over_S95="",
        )
    )
    assert verdict["is_allowed"] is True
    assert verdict["region_class"] == "allowed_outside_recast_domain"
    assert verdict["is_signal_domain_supported"] is False


def test_missing_coupling_becomes_no_signal_calibration_not_theory_failure():
    verdict = atlas_v1.classify_row(
        base_row(
            signal_domain_status=llp_signal.DOMAIN_MISSING,
            threshold_class="",
            N_over_S95="",
        )
    )
    assert verdict["is_allowed"] is True
    assert verdict["region_class"] == "allowed_no_signal_calibration"


def test_provisional_calibration_is_not_hidden():
    verdict = atlas_v1.classify_row(
        base_row(
            signal_calibration_status="PROVISIONAL",
            signal_status=llp_signal.STATUS_COMPUTED_PROVISIONAL,
        )
    )
    assert verdict["region_class"] == "allowed_signal_below"
    assert verdict["is_signal_calibration_validated"] is False
    assert "signal_calibration_not_validated" in verdict["atlas_notes"]


def test_theory_and_hbhs_keep_priority_over_signal_classification():
    assert atlas_v1.classify_row(base_row(theory_ok="0"))["region_class"] == "theory_fail"
    assert atlas_v1.classify_row(base_row(enrich_status="skipped_theory_fail"))["region_class"] == "hbhs_not_run"
    assert atlas_v1.classify_row(base_row(hb_allowed="0", exp_ok="0"))["region_class"] == "hb_excluded"
    assert atlas_v1.classify_row(base_row(exp_ok="0"))["region_class"] == "hs_tension"


def test_hb_excluded_row_is_not_allowed_when_exp_ok_is_inconsistent():
    verdict = atlas_v1.classify_row(base_row(hb_allowed="0", exp_ok="1"))
    assert verdict["region_class"] == "hb_excluded"
    assert verdict["is_allowed"] is False


def test_inconsistent_supported_signal_state_fails_closed():
    verdict = atlas_v1.classify_row(
        base_row(
            signal_status=llp_signal.STATUS_NOT_COMPUTED,
            threshold_class="BELOW",
            N_expected="6.0",
            N_over_S95="2.0",
        )
    )
    assert verdict["region_class"] == "allowed_no_signal_calibration"
    assert verdict["is_signal_domain_supported"] is False
    assert verdict["is_signal_at_or_above_S95"] is False
    assert "inconsistent_supported_signal_state" in verdict["atlas_notes"]


def test_supported_threshold_label_must_not_contradict_its_yield_ratio():
    verdict = atlas_v1.classify_row(
        base_row(threshold_class="BELOW", N_expected="6.0", N_over_S95="2.0")
    )
    assert verdict["region_class"] == "allowed_no_signal_calibration"
    assert verdict["is_signal_at_or_above_S95"] is False


def test_atlas_manifest_identifies_input_and_dirty_checkout(tmp_path):
    row = base_row()
    for column in schema.LLP_SIGNAL_NORMALIZED_INPUT_COLUMNS:
        row[column] = "1.0"
    input_path = tmp_path / "llp_signal_enriched.csv"
    with input_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    assert atlas_v1.run(["--input", str(input_path), "--output-dir", str(tmp_path)]) == 0
    manifest = json.loads((tmp_path / "boundary_atlas_v1_manifest.json").read_text())
    assert len(manifest["input_sha256"]) == 64
    assert isinstance(manifest["git_dirty"], bool)
