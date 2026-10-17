import pytest

from scripts.validate_numeric_inputs import (
    require_finite_number,
    require_nonnegative,
    require_nonnegative_integer,
    require_unit_interval,
)


def test_finite_number_accepts_valid_measurement():
    assert require_finite_number("125.0", "tokens") == 125.0


@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf"])
def test_finite_number_rejects_nonfinite_measurement(value):
    with pytest.raises(ValueError):
        require_finite_number(value, "metric")


def test_finite_number_rejects_text():
    with pytest.raises(ValueError):
        require_finite_number("unknown", "latency")


def test_nonnegative_accepts_zero():
    assert require_nonnegative("0", "cost") == 0.0


def test_nonnegative_rejects_negative_measurement():
    with pytest.raises(ValueError):
        require_nonnegative("-0.01", "cost")


@pytest.mark.parametrize("value, expected", [("0", 0), ("3", 3), ("3.0", 3)])
def test_nonnegative_integer_accepts_exact_counts(value, expected):
    assert require_nonnegative_integer(value, "claims_checked") == expected


@pytest.mark.parametrize("value", ["-1", "3.1", "3.6", "nan", "inf"])
def test_nonnegative_integer_rejects_invalid_counts(value):
    with pytest.raises(ValueError):
        require_nonnegative_integer(value, "claims_checked")


@pytest.mark.parametrize("value", ["0", "0.25", "1"])
def test_unit_interval_accepts_valid_proportions(value):
    assert require_unit_interval(value, "support_rate") == float(value)


@pytest.mark.parametrize("value", ["-0.001", "1.001", "nan", "inf"])
def test_unit_interval_rejects_invalid_proportions(value):
    with pytest.raises(ValueError):
        require_unit_interval(value, "support_rate")
