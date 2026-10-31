import pytest

from scripts.validate_numeric_inputs import require_nonnegative, require_unit_interval


@pytest.mark.parametrize("value", ["-1e-324", "-1e-5000"])
def test_nonnegative_rejects_negative_values_rounded_to_negative_zero(value):
    with pytest.raises(ValueError, match="negative"):
        require_nonnegative(value, "treatment_cost_usd")


def test_nonnegative_rejects_positive_measurement_underflow():
    with pytest.raises(ValueError, match="underflow"):
        require_nonnegative("1e-324", "latency_seconds")


@pytest.mark.parametrize("value", ["1.0000000000000001", "1.0000000000000000000001"])
def test_unit_interval_rejects_values_rounded_to_one(value):
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        require_unit_interval(value, "support_rate")


def test_unit_interval_rejects_negative_value_rounded_to_zero():
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        require_unit_interval("-1e-324", "support_rate")


def test_unit_interval_rejects_positive_nonzero_underflow():
    with pytest.raises(ValueError, match="underflow"):
        require_unit_interval("1e-324", "support_rate")


def test_continuous_bounds_accept_finite_representable_measurements():
    assert require_nonnegative("0.04", "treatment_cost_usd") == pytest.approx(0.04)
    assert require_unit_interval("1", "support_rate") == 1.0
    assert require_nonnegative("1e-320", "latency_seconds") > 0


def test_main_study_preflight_rejects_subnormal_negative_cost():
    from scripts.validate_main_study_inputs import validate_rows

    treatment = {
        "successful_sources": "3", "total_tokens": "1200", "model_calls": "2",
        "report_words": "500", "treatment_cost_usd": "-1e-324",
        "latency_seconds": "12.5",
    }
    evaluator = {
        "claims_checked": "4", "supported": "2", "partially_supported": "1",
        "unsupported": "1", "contradicted": "0",
    }
    with pytest.raises(ValueError, match="negative value for main row 2 treatment_cost_usd"):
        validate_rows([treatment], [evaluator])
