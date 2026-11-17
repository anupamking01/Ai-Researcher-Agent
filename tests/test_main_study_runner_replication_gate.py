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


@pytest.fixture
def configured_replication_env(monkeypatch):
    """Synthetic settings only; no provider credentials or network calls."""
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-not-a-real-key")
    monkeypatch.setenv("SMART_LLM_MODEL", "synthetic-smart")
    monkeypatch.setenv("FAST_LLM_MODEL", "synthetic-fast")
    monkeypatch.setenv("TEMPERATURE", "0.7")


@pytest.mark.parametrize("value", [
    "NaN", "nan", "Inf", "-Infinity", "1e999", "-0.01", "2.01",
    "not-a-number",
])
def test_replication_temperature_rejects_invalid_or_nonfinite_settings(
    configured_replication_env, monkeypatch, value,
):
    """No invalid numerical parameter may enter a new study manifest."""
    monkeypatch.setenv("TEMPERATURE", value)
    with pytest.raises(SystemExit, match="TEMPERATURE must be a finite number"):
        study._check_environment()


@pytest.mark.parametrize("value", ["0", "0.7", "1", "2"])
def test_replication_temperature_accepts_finite_domain(
    configured_replication_env, monkeypatch, value,
):
    monkeypatch.setenv("TEMPERATURE", value)
    study._check_environment()


@pytest.mark.parametrize("name", [
    "OPENAI_API_KEY", "SMART_LLM_MODEL", "FAST_LLM_MODEL", "TEMPERATURE",
])
def test_replication_rejects_whitespace_only_required_settings(
    configured_replication_env, monkeypatch, name,
):
    monkeypatch.setenv(name, "   \\t  ")
    with pytest.raises(SystemExit, match="Missing or blank experiment"):
        study._check_environment()


def test_invalid_temperature_blocks_before_task_selection_or_model_import(
    configured_replication_env, monkeypatch,
):
    monkeypatch.setenv("TEMPERATURE", "NaN")
    monkeypatch.setattr(
        study.sys, "argv",
        ["run_budget_main_study.py", "--noncanonical-replication-ack",
         study.NONCANONICAL_REPLICATION_ACK],
    )
    monkeypatch.setattr(
        study, "_load_task_file",
        lambda *_: pytest.fail("invalid settings must not select any tasks"),
    )
    monkeypatch.setattr(
        study.importlib, "import_module",
        lambda *_: pytest.fail("invalid settings must not import agent modules"),
    )
    with pytest.raises(SystemExit, match="TEMPERATURE must be a finite number"):
        asyncio.run(study._run_main_study())
