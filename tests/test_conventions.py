import os

import pytest

from dhb import contracts, schema

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Convention YAML has one owner: dihiggs. Sibling checkout, or $DIHIGGS_ROOT.
CONVENTIONS = os.path.join(
    os.environ.get("DIHIGGS_ROOT", os.path.join(os.path.dirname(REPO_ROOT), "dihiggs")),
    "conventions", "physics_conventions.yaml",
)
if not os.path.exists(CONVENTIONS):
    pytest.skip("dihiggs convention YAML not found at %s; set DIHIGGS_ROOT" % CONVENTIONS, allow_module_level=True)


@pytest.fixture
def conventions():
    yaml = pytest.importorskip("yaml")
    with open(CONVENTIONS) as fh:
        return yaml.safe_load(fh)


def test_hbar_c_matches_conventions(conventions):
    assert contracts.HBAR_C_GEV_MM == float(conventions["constants"]["hbar_c_gev_mm"])


def test_v3_names_distinguish_phi_from_legacy_boundary_schema(conventions):
    assert conventions["schema_version"] == "physics_conventions_v3"
    assert conventions["states"]["phi"]["canonical_symbol"] == "phi"
    assert conventions["states"]["phi"]["pdg_id"] == 35
    # The v0 CSV/API names remain readable for historical replay only.
    assert schema.MASS_COLUMN["h2"] == "mH"
    assert conventions["states"]["phi"]["legacy_mass_fields"] == [
        "mH", "mH_input_GeV", "mH2_GeV"
    ]
    assert "H" in conventions["states"]["phi"]["forbidden_unqualified_aliases"]
