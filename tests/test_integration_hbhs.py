"""Integration tests against a real HiggsTools install and the vendored
HB/HS datasets. Skipped unless the Higgs module is importable and
DHB_HB_DATASET_ROOT / DHB_HS_DATASET_ROOT are set (source
scripts/setup_env.sh and run scripts/build_higgstools.sh first).
"""

import csv
import os

import pytest

HP = pytest.importorskip("Higgs.predictions")

from dhb import adapter, runner  # noqa: E402

pytestmark = pytest.mark.integration

HB_DATASET = os.environ.get("DHB_HB_DATASET_ROOT", "")
HS_DATASET = os.environ.get("DHB_HS_DATASET_ROOT", "")

if not (HB_DATASET and os.path.isdir(HB_DATASET)):
    pytest.skip("DHB_HB_DATASET_ROOT not set", allow_module_level=True)
if not (HS_DATASET and os.path.isdir(HS_DATASET)):
    pytest.skip("DHB_HS_DATASET_ROOT not set", allow_module_level=True)


@pytest.fixture(scope="module")
def hbhs_runner():
    return runner.HbhsRunner(HB_DATASET, HS_DATASET)


def test_sm_like_higgs_is_allowed_with_zero_delta_chi2(hbhs_runner):
    pred = HP.Predictions()
    h = pred.addParticle(HP.BsmParticle("h", "neutral", "even"))
    h.setMass(125.09)
    HP.effectiveCouplingInput(h, HP.smLikeEffCouplings)

    result = hbhs_runner.run_point(pred)
    assert result["hb_allowed"]
    assert result["hs_delta_chi2"] == pytest.approx(0.0, abs=1e-9)
    assert result["hs_nobs"] > 0
    assert result["hs_chi2"] > 0


def test_decoupled_heavy_scalar_changes_nothing(hbhs_runner):
    pred = HP.Predictions()
    h = pred.addParticle(HP.BsmParticle("h", "neutral", "even"))
    h.setMass(125.09)
    HP.effectiveCouplingInput(h, HP.smLikeEffCouplings)
    heavy = pred.addParticle(HP.BsmParticle("H", "neutral", "even"))
    heavy.setMass(800.0)
    HP.effectiveCouplingInput(heavy, HP.scaledSMlikeEffCouplings(1e-4))

    result = hbhs_runner.run_point(pred)
    assert result["hb_allowed"]
    assert result["hs_delta_chi2"] == pytest.approx(0.0, abs=1e-6)


def test_strongly_coupled_heavy_scalar_is_excluded(hbhs_runner):
    """A 400 GeV scalar with SM-like couplings (full-strength ggH and
    H->tautau/VV rates) has been excluded at the LHC for a long time."""
    pred = HP.Predictions()
    heavy = pred.addParticle(HP.BsmParticle("H", "neutral", "even"))
    heavy.setMass(400.0)
    HP.effectiveCouplingInput(heavy, HP.smLikeEffCouplings)

    result = hbhs_runner.run_point(pred)
    assert not result["hb_allowed"]
    assert result["hb_max_obsratio"] > 1.0


def test_enrich_fixture_end_to_end(hbhs_runner, sample_rows):
    enriched = 0
    for row in sample_rows:
        if row["theory_ok"] != "1":
            continue
        pred, diagnostics = adapter.build_predictions(row, HP)
        result = hbhs_runner.run_point(pred)
        enriched += 1
        # fixture points are alignment-limit Type-I with a SM-like h1:
        # they must survive HB and sit close to the SM in HS
        assert result["hb_allowed"], row["point_id"]
        assert result["hs_delta_chi2"] < 10.0, row["point_id"]
        assert diagnostics["width_rel_diff_max"] < 0.2, row["point_id"]
    assert enriched >= 3


def test_alignment_h1_is_sm_like(hbhs_runner, theory_ok_row):
    """In exact alignment the fixture's h1 block must reproduce the SM
    reference chi2 up to the small charged-Higgs gamgam shift."""
    pred, _ = adapter.build_predictions(theory_ok_row, HP)
    h1 = pred.particle("h1")
    assert h1.mass() == pytest.approx(125.09)
    result = hbhs_runner.run_point(pred)
    assert abs(result["hs_delta_chi2"]) < 5.0
