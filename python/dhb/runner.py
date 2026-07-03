"""Run HiggsBounds and HiggsSignals on Predictions objects.

Wraps Higgs.bounds.Bounds and Higgs.signals.Signals; both load their
datasets at construction, so a single runner must be reused for all points
of a run.
"""

import math

from . import schema

SM_REFERENCE_MH = 125.09


def import_higgs_modules():
    """Import the HiggsTools python modules. Kept separate so tests can
    substitute fakes and so the import error is informative."""
    try:
        import Higgs.predictions as HP
        import Higgs.bounds as HB
        import Higgs.signals as HS
    except ImportError as exc:
        raise ImportError(
            "The 'Higgs' module (HiggsTools) is not installed. "
            "Run scripts/build_higgstools.sh first."
        ) from exc
    return HP, HB, HS


class HbhsRunner:
    def __init__(self, hb_dataset, hs_dataset, modules=None):
        HP, HB, HS = modules if modules is not None else import_higgs_modules()
        self.HP = HP
        self.bounds = HB.Bounds(str(hb_dataset))
        self.signals = HS.Signals(str(hs_dataset))
        self._sm_chi2 = None

    def sm_reference_chi2(self):
        """HiggsSignals chi2 of a single SM-like Higgs at 125.09 GeV,
        computed once and cached; reference for delta chi2."""
        if self._sm_chi2 is None:
            pred = self.HP.Predictions()
            h = pred.addParticle(self.HP.BsmParticle("h", "neutral", "even"))
            h.setMass(SM_REFERENCE_MH)
            self.HP.effectiveCouplingInput(h, self.HP.smLikeEffCouplings)
            self._sm_chi2 = float(self.signals(pred))
        return self._sm_chi2

    def run_point(self, pred):
        hb = self.bounds(pred)

        max_obsratio = float("nan")
        limiting_particle = ""
        limiting_process = ""
        for particle_id, applied in dict(hb.selectedLimits).items():
            ratio = float(applied.obsRatio())
            if not math.isfinite(max_obsratio) or ratio > max_obsratio:
                max_obsratio = ratio
                limiting_particle = particle_id
                # keep the enriched CSV naively comma-splittable, matching
                # the rest of the pipeline (no quoted fields)
                limiting_process = (
                    applied.limit().processDesc().replace(",", ";")
                )

        chi2 = float(self.signals(pred))
        sm_chi2 = self.sm_reference_chi2()

        return {
            "hb_allowed": bool(hb.allowed),
            "hb_max_obsratio": max_obsratio,
            "hb_limiting_particle": limiting_particle,
            "hb_limiting_process": limiting_process,
            "hs_chi2": chi2,
            "hs_nobs": int(self.signals.observableCount()),
            "hs_chi2_sm_ref": sm_chi2,
            "hs_delta_chi2": chi2 - sm_chi2,
        }


def dataset_paths_from_env(environ):
    hb = environ.get("DHB_HB_DATASET_ROOT", "")
    hs = environ.get("DHB_HS_DATASET_ROOT", "")
    return hb, hs
