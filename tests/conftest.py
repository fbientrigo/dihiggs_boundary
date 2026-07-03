import csv
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "python"))

FIXTURES = os.path.join(REPO_ROOT, "tests", "fixtures")
SAMPLE_CSV = os.path.join(FIXTURES, "evaluate_point_sample.csv")


@pytest.fixture
def sample_csv_path():
    return SAMPLE_CSV


@pytest.fixture
def sample_rows():
    with open(SAMPLE_CSV, newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture
def theory_ok_row(sample_rows):
    for row in sample_rows:
        if row["theory_ok"] == "1":
            return row
    raise AssertionError("fixture has no theory_ok row")


@pytest.fixture
def theory_fail_row(sample_rows):
    for row in sample_rows:
        if row["theory_ok"] == "0":
            return row
    raise AssertionError("fixture has no theory-fail row")


# ---------------------------------------------------------------------------
# Fake Higgs.predictions module for unit tests (no HiggsTools required)
# ---------------------------------------------------------------------------


class FakeNeutralEffectiveCouplings:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __getattr__(self, name):
        try:
            return self.kwargs[name]
        except KeyError:
            raise AttributeError(name)


class FakeParticle:
    def __init__(self, particle_id, charge, cp):
        self.particle_id = particle_id
        self.charge = charge
        self.cp_value = cp
        self.mass_value = None
        self.total_width = 0.0
        self.brs = []
        self.decay_widths = []
        self.cxns = []
        self.eff_couplings = None
        self.eff_kwargs = None

    def setMass(self, value):
        self.mass_value = value

    def setTotalWidth(self, value):
        self.total_width = value

    def setBr(self, *args):
        self.brs.append(args)

    def setDecayWidth(self, *args):
        *_, width = args
        self.decay_widths.append(args)
        self.total_width += width

    def setCxn(self, coll, prod, value):
        self.cxns.append((coll, prod, value))

    def totalWidth(self):
        return self.total_width


class FakePredictions:
    def __init__(self):
        self.particles = {}

    def addParticle(self, particle):
        self.particles[particle.particle_id] = particle
        return particle

    def particle(self, particle_id):
        return self.particles[particle_id]


class FakeEffectiveCouplingCxns:
    @staticmethod
    def ppHpmtb(collider, mass, cHpmtbR, cHpmtbL, brtHpb):
        return 0.125


class FakeHP:
    """Stand-in for the Higgs.predictions module, capturing all calls."""

    Predictions = FakePredictions
    BsmParticle = FakeParticle
    NeutralEffectiveCouplings = FakeNeutralEffectiveCouplings
    EffectiveCouplingCxns = FakeEffectiveCouplingCxns
    smLikeEffCouplings = FakeNeutralEffectiveCouplings()

    @staticmethod
    def effectiveCouplingInput(particle, coups, **kwargs):
        particle.eff_couplings = coups
        particle.eff_kwargs = kwargs


@pytest.fixture
def fake_hp():
    return FakeHP
