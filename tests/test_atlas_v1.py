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
    verdict = atlas_v1.classify_row(base_row(threshold_class="NEAR", N_over_S95="1.0"))
    assert verdict["region_class"] == "allowed_signal_near_threshold"
    assert verdict["is_signal_at_or_above_S95"] is True


def test_allowed_signal_above():
    verdict = atlas_v1.classify_row(base_row(threshold_class="ABOVE", N_over_S95="2.0"))
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
        base_row(signal_calibration_status="PROVISIONAL")
    )
    assert verdict["region_class"] == "allowed_signal_below"
    assert verdict["is_signal_calibration_validated"] is False
    assert "signal_calibration_not_validated" in verdict["atlas_notes"]


def test_theory_and_hbhs_keep_priority_over_signal_classification():
    assert atlas_v1.classify_row(base_row(theory_ok="0"))["region_class"] == "theory_fail"
    assert atlas_v1.classify_row(base_row(enrich_status="skipped_theory_fail"))["region_class"] == "hbhs_not_run"
    assert atlas_v1.classify_row(base_row(hb_allowed="0", exp_ok="0"))["region_class"] == "hb_excluded"
    assert atlas_v1.classify_row(base_row(exp_ok="0"))["region_class"] == "hs_tension"
