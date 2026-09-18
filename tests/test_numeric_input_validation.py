import pytest

from scripts.validate_numeric_inputs import require_finite_number, require_nonnegative


def test_finite_number_accepts_valid_measurement():
    assert require_finite_number("125.0", "tokens") == 125.0


def test_finite_number_rejects_nonfinite_measurement():
    with pytest.raises(ValueError):
        require_finite_number("nan", "metric")


def test_finite_number_rejects_text():
    with pytest.raises(ValueError):
        require_finite_number("unknown", "latency")


def test_nonnegative_accepts_zero():
    assert require_nonnegative("0", "cost") == 0.0


def test_nonnegative_rejects_negative_measurement():
    with pytest.raises(ValueError):
        require_nonnegative("-0.01", "cost")
