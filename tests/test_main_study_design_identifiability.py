"""Synthetic structural rank tests; never load results or run agents."""
import json

import pytest

from scripts import audit_main_study_design_identifiability as audit


def test_historical_schedule_has_exact_treatment_position_alias():
    result = audit.analyze_schedule(audit.HISTORICAL_SCHEDULE)
    assert result["planned_cells"] == 40
    assert result["all_tasks_share_historical_fixed_order"] is True
    assert result["rank_task_intercepts"] == 10
    assert result["rank_task_plus_treatment"] == 13
    assert result["rank_task_plus_position"] == 13
    assert result["rank_task_plus_treatment_plus_position"] == 13
    assert result["additional_treatment_rank_after_position"] == 0
    assert result["additional_position_rank_after_treatment"] == 0
    assert result["separate_treatment_and_position_effects_identifiable"] is False
    assert result["original_treatment_execution_authenticated"] is False
    assert result["causal_effects_identified"] is False
    assert result["human_validation_performed"] is False


def test_variable_within_task_order_restores_structural_identifiability_only():
    # A purely synthetic schedule, not an executed replication. Reordering
    # across tasks breaks the exact identity between treatment and position.
    arms = list(audit.VARIANTS)
    order = tuple(
        (task_id, arm)
        for index, task_id in enumerate(audit.TASK_IDS)
        for arm in arms[index % 4:] + arms[:index % 4]
    )
    result = audit.analyze_schedule(order)
    assert result["rank_task_plus_treatment_plus_position"] == 16
    assert result["additional_treatment_rank_after_position"] == 3
    assert result["additional_position_rank_after_treatment"] == 3
    assert result["separate_treatment_and_position_effects_identifiable"] is True
    assert result["causal_effects_identified"] is False
    assert result["original_treatment_execution_authenticated"] is False


@pytest.mark.parametrize("bad", [
    tuple(),
    audit.HISTORICAL_SCHEDULE[:-1],
    audit.HISTORICAL_SCHEDULE[:-1] + (audit.HISTORICAL_SCHEDULE[0],),
    (("other-task", "D3"),) + audit.HISTORICAL_SCHEDULE[1:],
    (("main-01", "unregistered-arm"),) + audit.HISTORICAL_SCHEDULE[1:],
    (("main-01", 1),) + audit.HISTORICAL_SCHEDULE[1:],
    (["main-01", "D3"],) + audit.HISTORICAL_SCHEDULE[1:],
])
def test_invalid_schedules_fail_closed(bad):
    with pytest.raises(audit.IdentifiabilityError):
        audit.analyze_schedule(bad)


def test_exact_rank_rejects_nonrectangular_or_ambiguous_input():
    for rows in ([], [[]], [[1], [1, 0]], [[True], [1]], [[1.0]]):
        with pytest.raises(audit.IdentifiabilityError):
            audit.exact_rank(rows)


def test_exact_rank_detects_dependent_columns():
    assert audit.exact_rank([[1, 2, 3], [2, 4, 6], [1, 1, 1]]) == 2
    assert audit.exact_rank([[1, 0], [0, 1]]) == 2


def test_cli_reports_no_empirical_claims(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["audit_main_study_design_identifiability"])
    assert audit.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["classification"] == "structural_design_identifiability_only_no_outcomes"
    assert result["treatments_or_evaluators_rerun"] is False
    assert result["time_varying_provider_conditions_observed"] is False
