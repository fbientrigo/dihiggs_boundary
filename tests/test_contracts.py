import csv
import os

import pytest

from dhb import atlas, contracts, schema, validate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACTS_DIR = os.path.join(REPO_ROOT, "contracts")


# --- the committed YAML mirror must match the code -------------------------


def test_emitted_yaml_matches_committed():
    """`python -m dhb.contracts --emit` output must equal the committed
    contracts/*.yaml, so the machine-readable mirror can never silently drift
    from dhb.contracts. If this fails, re-run the emit and commit the result."""
    yaml = pytest.importorskip("yaml")
    for name, contract in contracts.CONTRACTS.items():
        path = os.path.join(CONTRACTS_DIR, name + ".yaml")
        assert os.path.exists(path), "missing committed contract %s (run emit)" % path
        with open(path) as fh:
            committed = yaml.safe_load(fh)
        assert committed == contract, (
            "contracts/%s.yaml is stale; run `python -m dhb.contracts --emit`" % name
        )


def test_contract_required_columns_are_subsets_of_full():
    for name, contract in contracts.CONTRACTS.items():
        full = contract.get("full_columns")
        if full is None:
            continue
        missing = set(contract["required_columns"]) - set(full)
        assert not missing, "%s: required not in full_columns: %s" % (name, missing)


def test_theory_full_columns_match_fixture_header(sample_csv_path):
    """The full evaluate_point_v1 column list must equal the fixture header."""
    with open(sample_csv_path) as fh:
        header = fh.readline().strip().split(",")
    assert header == contracts.EVALUATE_POINT_FULL_COLUMNS


def test_atlas_required_matches_enriched_contract():
    assert set(
        atlas.REQUIRED_THEORY_COLUMNS + atlas.REQUIRED_HBHS_COLUMNS
    ) == set(contracts.ENRICHED["required_columns"])


# --- validator behaviour ---------------------------------------------------


def test_validate_accepts_good_theory_csv(sample_csv_path):
    report = validate.validate_csv(sample_csv_path, contracts.THEORY)
    assert report.ok, report.describe()
    assert report.n_rows > 0


def test_validate_rejects_renamed_column(tmp_path, sample_csv_path):
    """Renaming a required column (the exact drift the contract exists to
    catch) must fail validation."""
    with open(sample_csv_path) as fh:
        rows = list(csv.reader(fh))
    header = rows[0]
    header[header.index("theory_ok")] = "theory_okay"  # typo'd rename
    out = tmp_path / "renamed.csv"
    with open(out, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    report = validate.validate_csv(str(out), contracts.THEORY)
    assert not report.ok
    assert "theory_ok" in report.missing_columns


def test_validate_catches_broken_ctau_invariant(tmp_path, sample_csv_path):
    """A row whose ctau_mm_H2 no longer equals hbar_c / total_width_H2 must be
    flagged, even though every column is present."""
    with open(sample_csv_path, newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)
    # Corrupt ctau on the first row that has a positive width.
    corrupted = False
    for row in rows:
        w = schema.parse_float(row, "total_width_H2")
        if schema.is_finite(w) and w > 0:
            row["ctau_mm_H2"] = "1.0"  # deliberately wrong
            corrupted = True
            break
    assert corrupted, "fixture had no positive-width row to corrupt"
    out = tmp_path / "bad_ctau.csv"
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    report = validate.validate_csv(str(out), contracts.THEORY)
    assert not report.ok
    assert any("ctau" in name for name, _c, _e in report.invariant_violations)


def test_validate_empty_csv(tmp_path):
    out = tmp_path / "empty.csv"
    out.write_text("")
    report = validate.validate_csv(str(out), contracts.THEORY)
    assert not report.ok
    assert report.error


def test_validate_missing_file(tmp_path):
    report = validate.validate_csv(str(tmp_path / "nope.csv"), contracts.THEORY)
    assert not report.ok
    assert report.error
