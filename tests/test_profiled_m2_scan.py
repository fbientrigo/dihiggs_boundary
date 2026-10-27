import math

from dhb.profiled_m2_scan import _lhs


def test_lhs_is_reproducible_and_stratified():
    spec = {"X": {"min": 1e-5, "max": 1.0, "scale": "log"}, "Delta": {"min": 150, "max": 500, "scale": "linear"}}
    first = _lhs("seed", 4, spec)
    assert first == _lhs("seed", 4, spec)
    assert all(1e-5 <= value <= 1 for value in first["X"])
    assert all(150 <= value <= 500 for value in first["Delta"])
    assert len({math.floor((math.log10(value) + 5) * 4 / 5) for value in first["X"]}) == 4
