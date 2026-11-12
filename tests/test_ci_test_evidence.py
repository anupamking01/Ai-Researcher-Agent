"""Synthetic-only checks for the offline CI provenance receipt."""
from pathlib import Path

import pytest
import yaml

from scripts import verify_ci_test_evidence as evidence


SHA = "a" * 40
CONTEXT = {
    "GITHUB_REPOSITORY": "anupamking01/Ai-Researcher-Agent",
    "GITHUB_SHA": SHA,
    "GITHUB_RUN_ID": "123456",
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_EVENT_NAME": "push",
}
DEPS = {"requirements.txt": b"app-deps", "requirements-ci.lock": b"locked-deps"}


def _log(summary="6 passed, 4 warnings in 1.25s (0:00:01)"):
    return (evidence.FIREWALL_MARKER + "\n" + summary + "\n").encode()


def test_synthetic_success_receipt_is_exact_commit_bound():
    result = evidence.build_receipt(
        _log(), context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS
    )
    assert result["status"].endswith("not_independently_attested")
    assert result["test_counts"] == {"passed": 6, "warnings": 4}
    assert result["checkout_sha"] == SHA
    assert result["firewall_activation_marker_observed"] is True
    assert result["actual_egress_independently_attested"] is False
    assert result["human_validation_performed"] is False


@pytest.mark.parametrize("bad_log", [
    b"", b"6 passed in 1.2s\n",
    _log("1 failed, 5 passed in 1.2s"),
    _log() + b"6 passed in 1.25s\n",
    _log().replace(b"Offline pytest egress isolation active", b"off"),
    _log().replace(b"in 1.25s", b"failed in 1.25s"),
])
def test_no_pass_on_incomplete_or_ambiguous_log(bad_log):
    with pytest.raises(ValueError):
        evidence.build_receipt(
            bad_log, context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS
        )


@pytest.mark.parametrize("change", [
    {"GITHUB_SHA": "b" * 40},
    {"GITHUB_EVENT_NAME": "deployment"},
    {"GITHUB_REPOSITORY": "other/repo"},
    {"GITHUB_RUN_ATTEMPT": "0"},
])
def test_wrong_run_identity_cannot_issue_receipt(change):
    with pytest.raises(ValueError):
        evidence.build_receipt(
            _log(), context={**CONTEXT, **change},
            checkout_sha=SHA, dependency_bytes=DEPS
        )


def test_missing_dependency_pin_fails_closed():
    with pytest.raises(ValueError):
        evidence.build_receipt(
            _log(), context=CONTEXT, checkout_sha=SHA,
            dependency_bytes={"requirements.txt": b"x"},
        )


def test_workflow_keeps_piped_wrapper_and_publishes_both_evidence_files():
    workflow = yaml.load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/tests.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["unit-tests"]["steps"]
    test_step = next(s for s in steps if s.get("name") == "Run offline unit tests")
    assert test_step["run"].strip().splitlines() == [
        "set -euo pipefail",
        'bash scripts/run_offline_pytest_firewalled.sh 2>&1 | tee "$RUNNER_TEMP/vera-offline-tests.log"',
    ]
    verify_step = next(s for s in steps if s.get("name") == "Bind exact-commit offline test evidence")
    assert "python -m scripts.verify_ci_test_evidence" in verify_step["run"]
    artifact = next(s for s in steps if s.get("name", "").startswith("Retain source-bound offline test"))
    assert artifact["with"]["if-no-files-found"] == "error"
    assert "vera-offline-tests.log" in artifact["with"]["path"]
    assert "vera-offline-test-receipt.json" in artifact["with"]["path"]


def test_workflow_requires_independent_identity_replay_before_evidence_upload():
    """Do not publish a producer receipt without exercising its offline consumer."""
    workflow = yaml.load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/tests.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["unit-tests"]["steps"]
    producer_index = next(
        i for i, step in enumerate(steps)
        if step.get("name") == "Bind exact-commit offline test evidence"
    )
    replay_index = next(
        i for i, step in enumerate(steps)
        if step.get("name") == "Replay exact-commit offline test evidence before upload"
    )
    upload_index = next(
        i for i, step in enumerate(steps)
        if step.get("name", "").startswith("Retain source-bound offline test")
    )
    assert producer_index < replay_index < upload_index
    replay_step = steps[replay_index]
    assert replay_step.get("shell") == "bash"
    assert "continue-on-error" not in replay_step
    script = replay_step["run"]
    assert script.splitlines()[0] == "set -euo pipefail"
    assert "python -m scripts.verify_retained_ci_test_evidence" in script
    for flag, value in (
        ("--log", "$RUNNER_TEMP/vera-offline-tests.log"),
        ("--receipt", "$RUNNER_TEMP/vera-offline-test-receipt.json"),
        ("--checkout-sha", "$GITHUB_SHA"),
        ("--run-id", "$GITHUB_RUN_ID"),
        ("--run-attempt", "$GITHUB_RUN_ATTEMPT"),
        ("--event", "$GITHUB_EVENT_NAME"),
    ):
        assert f'{flag} "{value}"' in script
    # The receipt must not supply the independent expected run identity.
    assert "jq" not in script and "|| true" not in script
