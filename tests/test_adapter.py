import math

import pytest

from dhb import adapter, schema


def test_rejects_row_without_block(theory_fail_row, fake_hp):
    with pytest.raises(ValueError):
        adapter.build_predictions(theory_fail_row, fake_hp)


def test_particle_content(theory_ok_row, fake_hp):
    pred, _ = adapter.build_predictions(theory_ok_row, fake_hp)
    assert set(pred.particles) == {"h1", "h2", "h3", "hc"}
    assert pred.particle("h1").cp_value == "even"
    assert pred.particle("h2").cp_value == "even"
    assert pred.particle("h3").cp_value == "odd"
    assert pred.particle("hc").charge == "single"
    for name in ("h1", "h2", "h3", "hc"):
        expected_mass = float(theory_ok_row[schema.MASS_COLUMN[name]])
        assert pred.particle(name).mass_value == expected_mass


def test_neutral_effective_coupling_mapping(theory_ok_row, fake_hp):
    coups = adapter.neutral_eff_couplings(theory_ok_row, "h2", fake_hp)
    k = coups.kwargs
    # complex kappas: CP-even from *_s, CP-odd from *_p
    assert k["tt"] == complex(
        float(theory_ok_row["eff_h2_tt_s"]), float(theory_ok_row["eff_h2_tt_p"])
    )
    # first generation reuses the second (Type-I generation universality)
    assert k["uu"] == k["cc"]
    assert k["dd"] == k["ss"]
    assert k["ee"] == k["mumu"]
    assert k["WW"] == float(theory_ok_row["eff_h2_WW"])
    assert k["Zgam"] == float(theory_ok_row["eff_h2_Zga"])
    assert k["gamgam"] == float(theory_ok_row["eff_h2_gaga"])
    # kappa_lambda only meaningful for the SM-like h1
    assert k["lam"] == 0.0
    assert adapter.neutral_eff_couplings(theory_ok_row, "h1", fake_hp).kwargs[
        "lam"
    ] == 1.0


def test_loop_couplings_not_recomputed(theory_ok_row, fake_hp):
    """ggH and H->gamgam must be rescaled with the 2HDMC loop-accurate
    kappas (which include the charged Higgs contribution), not recomputed
    from tt/bb."""
    pred, _ = adapter.build_predictions(theory_ok_row, fake_hp)
    for name in schema.NEUTRALS:
        kwargs = pred.particle(name).eff_kwargs
        assert kwargs == {"calcggH": False, "calcHgamgam": False}


def test_bsm_decay_widths(theory_ok_row, fake_hp):
    """BSM decays are set as partial widths BR * Gamma_total(2HDMC)."""
    row = dict(theory_ok_row)
    row["br_h2_h1h1"] = "0.25"
    row["br_h3_h1Z"] = "0.5"
    pred, _ = adapter.build_predictions(row, fake_hp)

    h2_width = float(row[schema.TOTAL_WIDTH_COLUMN["h2"]])
    assert ("h1", "h1", pytest.approx(0.25 * h2_width)) in [
        tuple(x) for x in pred.particle("h2").decay_widths
    ]
    h3_width = float(row[schema.TOTAL_WIDTH_COLUMN["h3"]])
    assert ("Z", "h1", pytest.approx(0.5 * h3_width)) in [
        tuple(x) for x in pred.particle("h3").decay_widths
    ]
    # zero BRs are skipped entirely
    for args in pred.particle("h1").decay_widths:
        assert args[-1] > 0.0


def test_charged_higgs_setup(theory_ok_row, fake_hp):
    row = dict(theory_ok_row)
    row["br_t_hcb"] = "0.01"
    pred, _ = adapter.build_predictions(row, fake_hp)
    hc = pred.particle("hc")

    brs = {args[:-1]: args[-1] for args in hc.brs}
    assert ("tb",) in brs and brs[("tb",)] == float(row["br_hc_tb"])
    assert ("taunu",) in brs

    cxns = {(coll, prod): value for coll, prod, value in hc.cxns}
    assert cxns[("LHC13", "Hpmtb")] == 0.125  # FakeEffectiveCouplingCxns
    assert cxns[("LHC13", "brtHpb")] == 0.01
    assert cxns[("LHC8", "brtHpb")] == 0.01


def test_width_rel_diff(theory_ok_row, fake_hp):
    """The diagnostic compares reconstructed vs 2HDMC total widths."""
    pred, diagnostics = adapter.build_predictions(theory_ok_row, fake_hp)
    # the fake effectiveCouplingInput sets no SM widths, and hc's width is
    # set exactly from the row, so the worst deviation is ~100% (neutral
    # widths are entirely missing in the fake)
    assert 0.99 <= diagnostics["width_rel_diff_max"] <= 1.0

    # if all widths match exactly, the diagnostic is 0
    for name in ("h1", "h2", "h3", "hc"):
        pred.particle(name).total_width = float(
            theory_ok_row[schema.TOTAL_WIDTH_COLUMN[name]]
        )
    assert adapter.width_rel_diff_max(pred, theory_ok_row) == 0.0


def test_nan_row_values_do_not_crash(theory_ok_row, fake_hp):
    row = dict(theory_ok_row)
    row["br_h2_h1h1"] = "nan"
    row["hc_kappa_t"] = "nan"
    pred, _ = adapter.build_predictions(row, fake_hp)
    assert ("h1", "h1") not in [
        tuple(args[:-1]) for args in pred.particle("h2").decay_widths
    ]
    cxns = {(coll, prod) for coll, prod, _ in pred.particle("hc").cxns}
    assert ("LHC13", "Hpmtb") not in cxns


def test_width_rel_diff_ignores_invalid_reference(theory_ok_row, fake_hp):
    row = dict(theory_ok_row)
    row["total_width_h3"] = "nan"
    pred, diagnostics = adapter.build_predictions(row, fake_hp)
    assert math.isfinite(diagnostics["width_rel_diff_max"])
