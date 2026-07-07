import os

import pytest

from dhb import contracts, schema

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONVENTIONS = os.path.join(REPO_ROOT, "conventions", "physics_conventions.yaml")


@pytest.fixture
def conventions():
    yaml = pytest.importorskip("yaml")
    with open(CONVENTIONS) as fh:
        return yaml.safe_load(fh)


def test_conventions_file_present():
    assert os.path.exists(CONVENTIONS)


def test_hbar_c_matches_conventions(conventions):
    """The hbar*c used to derive ctau_mm_H2 must equal the shared conventions
    value. This is the same literal the C++ evaluator and the other repos use;
    the conventions file is what keeps them from drifting apart."""
    assert contracts.HBAR_C_GEV_MM == float(conventions["hbar_c_gev_mm"])


def test_pinned_hbar_c_value():
    # Pin the numeric value so an accidental edit to either side is caught.
    assert contracts.HBAR_C_GEV_MM == 1.973269804e-13


def test_neutral_scalar_naming_matches_schema(conventions):
    """schema.NEUTRALS / MASS_COLUMN must agree with the shared naming map."""
    assert tuple(conventions["neutral_scalars"]) == schema.NEUTRALS
    for hk, meta in conventions["neutral_scalars"].items():
        assert schema.MASS_COLUMN[hk] == meta["mass_column"]
    assert schema.MASS_COLUMN["hc"] == conventions["charged_scalar"]["hc"]["mass_column"]
