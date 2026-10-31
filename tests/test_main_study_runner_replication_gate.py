"""Noncanonical direct-run gate: synthetic, offline, no treatment execution."""
import asyncio
from pathlib import Path

import pytest

from scripts import run_budget_main_study as study


@pytest.mark.parametrize("ack", [
    None, "", "noncanonical_replication", "NONCANONICAL_REPLICATION ",
    "NONCANONICAL_EVALUATOR_RECOVERY", "CANONICAL_REPLAY",
])
def test_direct_runner_rejects_missing_or_wrong_ack_before_environment(
    monkeypatch, ack
):
    argv = ["run_budget_main_study.py"]
    if ack is not None:
        argv += ["--noncanonical-replication-ack", ack]
    monkeypatch.setattr(study.sys, "argv", argv)
    monkeypatch.setattr(
        study, "_check_environment",
        lambda: pytest.fail("environment must not be consulted before acknowledgment"),
    )
    monkeypatch.setattr(
        study, "_load_task_file",
        lambda *_: pytest.fail("task selection must not precede acknowledgment"),
    )
    with pytest.raises(SystemExit, match="noncanonical replication"):
        asyncio.run(study._run_main_study())


def test_acknowledged_runner_reaches_environment_without_model_execution(monkeypatch):
    monkeypatch.setattr(
        study.sys, "argv",
        ["run_budget_main_study.py", "--noncanonical-replication-ack",
         study.NONCANONICAL_REPLICATION_ACK],
    )

    class PreflightReached(Exception):
        pass

    def stop_before_any_agent_import():
        raise PreflightReached()

    monkeypatch.setattr(study, "_check_environment", stop_before_any_agent_import)
    with pytest.raises(PreflightReached):
        asyncio.run(study._run_main_study())


def test_new_manifest_declares_noncanonical_origin_and_no_replacement():
    provenance = study._noncanonical_replication_provenance()
    assert provenance == {
        "classification": "noncanonical_replication",
        "original_frozen_study_id": "budget-main-v1",
        "original_actions_treatment_run_id": 34620917346,
        "original_runner_commit": "c3c15e46a8eec3a8bbc24c968eedc0548172a897",
        "can_replace_original_treatment_evidence": False,
    }
    # Assert this contract is actually embedded in the production manifest
    # rather than merely exposed by an unused helper function.
    source = (Path(__file__).resolve().parents[1] / "scripts" /
              "run_budget_main_study.py").read_text(encoding="utf-8")
    assert '"replication_provenance": _noncanonical_replication_provenance(),' in source


def test_workflow_carries_acknowledgment_into_direct_runner():
    workflow = (Path(__file__).resolve().parents[1] / ".github" /
                "workflows" / "budget-main-study.yml").read_text(encoding="utf-8")
    assert (
        "run: python scripts/run_budget_main_study.py --max-agent-cost-usd 3.00 "
        "--noncanonical-replication-ack NONCANONICAL_REPLICATION"
    ) in workflow
    assert "Require explicit noncanonical replication acknowledgement" in workflow
