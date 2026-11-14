"""Offline evaluator CLI acknowledgment tests; no model calls."""
import pytest

from scripts import evaluate_posthoc_support as evaluator


@pytest.mark.parametrize("ack", [
    None, "", "noncanonical_evaluator_recovery",
    "NONCANONICAL_EVALUATOR_RECOVERY ", "NONCANONICAL_REPLICATION",
    "CANONICAL_RECOVERY",
])
def test_unacknowledged_direct_evaluator_stops_before_credentials(monkeypatch, ack):
    argv = ["evaluate_posthoc_support.py"]
    if ack is not None:
        argv += ["--noncanonical-evaluator-replay-ack", ack]
    monkeypatch.setattr(evaluator.sys, "argv", argv)
    with monkeypatch.context() as m:
        m.setattr(
            evaluator.os, "getenv",
            lambda *_args, **_kwargs: pytest.fail(
                "credential lookup must not precede replay acknowledgment"
            ),
        )
        with pytest.raises(SystemExit, match="noncanonical acknowledgement"):
            evaluator.main()


def test_correct_ack_reaches_credentials_without_provider_call(monkeypatch):
    monkeypatch.setattr(evaluator.sys, "argv", [
        "evaluate_posthoc_support.py", "--noncanonical-evaluator-replay-ack",
        evaluator.NONCANONICAL_EVALUATOR_REPLAY_ACK,
    ])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="Missing required environment variable: OPENAI_API_KEY"):
        evaluator.main()


def test_replay_metadata_cannot_be_mistaken_for_original_recovery():
    assert evaluator._noncanonical_evaluator_replay_provenance() == {
        "classification": "noncanonical_evaluator_replay",
        "original_frozen_study_id": "budget-main-v1",
        "original_actions_evaluator_recovery_run_id": 34783525480,
        "original_actions_treatment_run_id": 34620917346,
        "can_replace_original_evaluator_evidence": False,
        "historical_archive_custody_authenticated": False,
    }
