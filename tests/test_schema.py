import math

from dhb import schema


def test_block_columns_match_cpp_header(sample_rows, sample_csv_path):
    """The python schema must list the HBHS block columns in exactly the
    order written by src/evaluate_point.cpp."""
    with open(sample_csv_path) as fh:
        header = fh.readline().strip().split(",")
    start = header.index("hbhs_block_ok")
    assert header[start:] == schema.HBHS_BLOCK_COLUMNS


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
