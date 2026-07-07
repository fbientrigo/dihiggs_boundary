import math
import os
import re

from dhb import schema

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVALUATE_POINT_CPP = os.path.join(REPO_ROOT, "src", "evaluate_point.cpp")


def test_block_columns_match_cpp_header(sample_rows, sample_csv_path):
    """The python schema must list the HBHS block columns in exactly the
    order written by src/evaluate_point.cpp (checked via the committed
    fixture header)."""
    with open(sample_csv_path) as fh:
        header = fh.readline().strip().split(",")
    start = header.index("hbhs_block_ok")
    assert header[start:] == schema.HBHS_BLOCK_COLUMNS


def _cpp_char_array(source, name):
    """Extract a `const char* name[N] = {"a", "b", ...};` literal from C++."""
    m = re.search(name + r"\s*\[\s*\d*\s*\]\s*=\s*\{([^}]*)\}", source)
    assert m, "could not find C++ array %s in evaluate_point.cpp" % name
    return re.findall(r'"([^"]*)"', m.group(1))


def test_cpp_source_building_blocks_match_schema():
    """Non-circular guard against C++/python drift: instead of re-deriving the
    column order (which both sides encode the same way), assert the *raw name
    arrays* the C++ header writer loops over equal the python schema
    constants. If someone renames a scalar/fermion/pair in evaluate_point.cpp
    without updating schema.py (or vice versa), this fails without needing to
    compile the evaluator.
    """
    if not os.path.exists(EVALUATE_POINT_CPP):
        # Source not present (e.g. python-only checkout); the fixture test
        # above still guards the committed schema.
        import pytest

        pytest.skip("src/evaluate_point.cpp not present")
    with open(EVALUATE_POINT_CPP) as fh:
        source = fh.read()

    assert tuple(_cpp_char_array(source, "kNeutralNames")) == schema.NEUTRALS
    assert tuple(_cpp_char_array(source, "kEffFermionNames")) == schema.EFF_FERMIONS
    assert tuple(_cpp_char_array(source, "kHhPairNames")) == schema.HH_PAIRS

    # The effective-boson labels are emitted as inline literals in
    # write_hbhs_header (not an array); assert each appears with the eff_ prefix.
    for boson in schema.EFF_BOSONS:
        assert ('eff_" << h << "_%s' % boson) in source, (
            "boson label %s missing from evaluate_point.cpp header writer" % boson
        )


def test_block_column_count():
    cols = schema.HBHS_BLOCK_COLUMNS
    assert len(cols) == len(set(cols))
    # 1 flag + 3*(12 fermion + 5 boson + 3 hiZ) + 3 widths + 3*10 BRs + 10 charged
    assert len(cols) == 1 + 3 * 20 + 3 + 3 * 10 + 10


def test_parse_float():
    assert schema.parse_float({"x": "1.5"}, "x") == 1.5
    assert math.isnan(schema.parse_float({"x": "nan"}, "x"))
    assert math.isnan(schema.parse_float({"x": ""}, "x"))
    assert math.isnan(schema.parse_float({}, "x"))


def test_parse_flag():
    assert schema.parse_flag({"x": "1"}, "x")
    assert not schema.parse_flag({"x": "0"}, "x")
    assert not schema.parse_flag({"x": "nan"}, "x")
    assert not schema.parse_flag({}, "x")


def test_missing_columns():
    assert schema.missing_columns(["a", "b"], ["a", "b"]) == []
    assert schema.missing_columns(["a"], ["a", "b"]) == ["b"]
    assert schema.missing_columns(None, ["a"]) == ["a"]


def test_fixture_covers_pass_and_fail(sample_rows):
    flags = {row["theory_ok"] for row in sample_rows}
    assert flags == {"0", "1"}
    for row in sample_rows:
        assert row["hbhs_block_ok"] == row["theory_ok"]
