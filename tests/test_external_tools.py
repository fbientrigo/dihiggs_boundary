"""Drift guard for external-tool versions and the shared conventions file.

The three repos (dihiggs, dihiggs_boundary, dihiggs_hep_cross) are separate git
repos and cannot see each other in CI. Cross-repo agreement is instead enforced
by SHARED PINNED CONSTANTS asserted independently in each repo:

  * EXPECTED_VERSIONS  -- every repo's external_tools.lock.yaml must declare
    these same tool versions.
  * PINNED_CONVENTIONS_MD5 -- every repo's conventions/physics_conventions.yaml
    must hash to this. Since the file is byte-identical across repos, one pinned
    md5 makes any drift in any repo fail that repo's CI.

Keep these constants identical across the three test_external_tools.py copies.
"""

import hashlib
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO_ROOT, "external_tools.lock.yaml")
CONVENTIONS = os.path.join(REPO_ROOT, "conventions", "physics_conventions.yaml")

# --- shared cross-repo pins (keep identical in all three repos) ------------
EXPECTED_VERSIONS = {
    "2HDMC": "1.8",
    "HiggsTools": "v1.2",
    "HiggsBounds_dataset": "v1.7",
    "HiggsSignals_dataset": "v1.1",
}
PINNED_CONVENTIONS_MD5 = "a2fea4c862d3b678334fd07a396f26ba"
CONVENTIONS_SCHEMA_VERSION = "physics_conventions_v1"


def _load_manifest():
    yaml = pytest.importorskip("yaml")
    with open(MANIFEST) as fh:
        return yaml.safe_load(fh)


def test_manifest_present_and_parses():
    assert os.path.exists(MANIFEST), "missing external_tools.lock.yaml"
    manifest = _load_manifest()
    assert manifest["schema_version"] == "external_tools_v1"
    assert "tools" in manifest


def test_declared_versions_match_shared_pins():
    """Every tool version must equal the cross-repo pinned value; a bump in one
    repo without the others fails here."""
    tools = _load_manifest()["tools"]
    for name, expected in EXPECTED_VERSIONS.items():
        assert name in tools, "manifest missing tool %s" % name
        assert tools[name]["version"] == expected, (
            "%s version %r != pinned %r" % (name, tools[name]["version"], expected)
        )


def test_conventions_md5_matches_pin():
    """The shared conventions file must hash to the pinned md5 (byte-identical
    across the three repos)."""
    assert os.path.exists(CONVENTIONS)
    with open(CONVENTIONS, "rb") as fh:
        actual = hashlib.md5(fh.read()).hexdigest()
    assert actual == PINNED_CONVENTIONS_MD5, (
        "conventions/physics_conventions.yaml md5 %s != pinned %s "
        "(did the shared file drift?)" % (actual, PINNED_CONVENTIONS_MD5)
    )


def test_manifest_conventions_block_matches_file():
    """The manifest's recorded md5/schema_version must match the actual file, so
    the manifest cannot silently lag the conventions file."""
    conv = _load_manifest()["conventions"]
    assert conv["md5"] == PINNED_CONVENTIONS_MD5
    assert conv["schema_version"] == CONVENTIONS_SCHEMA_VERSION
    with open(CONVENTIONS, "rb") as fh:
        actual = hashlib.md5(fh.read()).hexdigest()
    assert conv["md5"] == actual


def test_vendored_paths_exist_when_declared():
    """If a tool declares a vendored_path, it must exist in this repo (catches a
    renamed/moved vendored tree that would break the build)."""
    tools = _load_manifest()["tools"]
    for name, meta in tools.items():
        path = meta.get("vendored_path")
        if path:
            assert os.path.exists(os.path.join(REPO_ROOT, path)), (
                "%s vendored_path %r does not exist" % (name, path)
            )
