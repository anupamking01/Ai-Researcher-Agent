"""Offline numeric-domain regressions for treatment resource controls.

These tests do not run treatments, call models, or change frozen artifacts.
"""

import math

import pytest

from logic.experiment import ExperimentConfig, allocate_source_budgets


@pytest.mark.parametrize(
    "field",
    ("source_budget", "search_candidate_multiplier", "max_concurrent_browses"),
)
@pytest.mark.parametrize(
    "invalid",
    (True, 1.0, 1.5, "2", None, 0, -1, float("nan"), float("inf")),
)
def test_discrete_budget_controls_require_positive_exact_int(field, invalid):
    with pytest.raises(ValueError, match=field):
        ExperimentConfig(**{field: invalid})


@pytest.mark.parametrize("field", ("browse_timeout_seconds", "run_timeout_seconds"))
@pytest.mark.parametrize(
    "invalid",
    (True, "60", None, 0, -1, float("nan"), float("inf"), -float("inf"), 10**400),
)
def test_runtime_timeouts_require_positive_finite_numbers(field, invalid):
    with pytest.raises(ValueError, match=field):
        ExperimentConfig(**{field: invalid})


@pytest.mark.parametrize("field", ("browse_timeout_seconds", "run_timeout_seconds"))
@pytest.mark.parametrize("valid", (0.25, 1, 60.0))
def test_runtime_timeouts_accept_real_positive_finite_numbers(field, valid):
    config = ExperimentConfig(**{field: valid})
    assert getattr(config, field) == valid
    assert math.isfinite(getattr(config, field))


@pytest.mark.parametrize(
    ("total_budget", "n_queries"),
    (
        (True, 1), (2.0, 1), (2.5, 1), ("2", 1), (-1, 1),
        (1, True), (1, 1.0), (1, 1.5), (1, "1"), (1, -1),
        (1, float("nan")), (float("inf"), 1),
    ),
)
def test_allocation_rejects_nondiscrete_inputs(total_budget, n_queries):
    with pytest.raises(ValueError, match="non-negative integer"):
        allocate_source_budgets(total_budget, n_queries)


def test_frozen_variant_scheduled_source_budgets_remain_unchanged():
    assert {
        variant: ExperimentConfig.from_variant(variant).source_budget
        for variant in ("D3", "D6", "P6", "P6V")
    } == {"D3": 3, "D6": 6, "P6": 6, "P6V": 6}
    assert allocate_source_budgets(6, 4) == [2, 2, 1, 1]
    assert allocate_source_budgets(3, 5) == [1, 1, 1, 0, 0]
    assert allocate_source_budgets(0, 0) == []
