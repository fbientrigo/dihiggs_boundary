"""Drift guard for external-tool versions and the v3 convention sha pin.

The convention YAML lives only in dihiggs; scripts/check_workspace.py verifies
its bytes at the pinned dihiggs commit.
"""

import os

import pytest
yaml = pytest.importorskip("yaml")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO_ROOT, "external_tools.lock.yaml")

# --- shared cross-repo pins (keep identical in all three repos) ------------
EXPECTED_VERSIONS = {
    "2HDMC": "1.8",
    "HiggsTools": "v1.2",
    "HiggsBounds_dataset": "v1.7",
    "HiggsSignals_dataset": "v1.1",
}
PINNED_CONVENTIONS_SHA256 = "4f3a938ed54dbc779d25f691ce1dd06fe17af69751105dc3b69ccb6b7d92fff6"
CONVENTIONS_SCHEMA_VERSION = "physics_conventions_v3"


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


def test_manifest_conventions_block_matches_pins():
    conv = _load_manifest()["conventions"]
    assert conv["sha256"] == PINNED_CONVENTIONS_SHA256
    assert conv["schema_version"] == CONVENTIONS_SCHEMA_VERSION


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
