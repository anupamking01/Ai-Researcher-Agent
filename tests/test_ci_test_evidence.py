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


@pytest.mark.parametrize("summary,reason", [
    ("1 passed, 9 deselected in 0.02s", "deselected"),
    ("1 passed, 1 xpassed in 0.02s", "unexpectedly passing"),
])
def test_green_pytest_with_pruned_collection_or_xpass_is_not_certified(summary, reason):
    with pytest.raises(ValueError, match=reason):
        evidence.build_receipt(
            _log(summary), context=CONTEXT, checkout_sha=SHA,
            dependency_bytes=DEPS,
        )


def test_explicit_expected_skips_and_xfails_remain_visible_not_hidden():
    receipt = evidence.build_receipt(
        _log("5 passed, 2 skipped, 1 xfailed in 0.02s"),
        context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS,
    )
    assert receipt["test_counts"] == {
        "passed": 5, "skipped": 2, "xfailed": 1,
    }


def _synthetic_full_shard(tmp_path, monkeypatch):
    from scripts import select_full_ci_shard as selector
    test_root = tmp_path / "tests"
    test_root.mkdir()
    for index in range(selector.SHARDS):
        (test_root / f"test_{index:02d}.py").write_text(
            "def test_ok(): assert True\n", encoding="utf-8"
        )
    monkeypatch.setattr(evidence, "ROOT", tmp_path)
    manifest = b"tests/test_00.py\n"
    header = f"VERA full-suite shard 0/8; selected 1 modules; checkout {SHA}"
    log = (header + "\ntests/test_00.py\n" + evidence.FIREWALL_MARKER
           + "\n1 passed in 0.2s\n").encode()
    return log, manifest


def test_full_ci_receipt_binds_actual_source_shard_and_log(tmp_path, monkeypatch):
    import hashlib
    log, manifest = _synthetic_full_shard(tmp_path, monkeypatch)
    receipt = evidence.build_receipt(
        log, context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS,
        selected_modules=manifest, shard=0,
    )
    assert receipt["full_ci_shard"] == 0
    assert receipt["full_ci_selected_module_count"] == 1
    assert receipt["full_ci_total_modules"] == 8
    assert receipt["full_ci_selected_modules_sha256"] == hashlib.sha256(manifest).hexdigest()


@pytest.mark.parametrize("failure", ["wrong_bytes", "wrong_shard", "missing", "log_changed", "duplicate_header"])
def test_full_ci_rejects_unbound_selection_or_transcript(tmp_path, monkeypatch, failure):
    log, manifest = _synthetic_full_shard(tmp_path, monkeypatch)
    shard = 0
    if failure == "wrong_bytes":
        manifest = b"tests/test_01.py\n"
    elif failure == "wrong_shard":
        shard = 1
    elif failure == "missing":
        manifest = None
    elif failure == "log_changed":
        log = log.replace(b"tests/test_00.py\n", b"tests/test_01.py\n")
    elif failure == "duplicate_header":
        log = log.replace(evidence.FIREWALL_MARKER.encode(), log.split(b"\n")[0] + b"\n" + evidence.FIREWALL_MARKER.encode())
    with pytest.raises(ValueError, match="shard|inventory|module|together"):
        evidence.build_receipt(
            log, context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS,
            selected_modules=manifest, shard=shard,
        )


def test_retained_full_ci_receipt_requires_exact_manifest(tmp_path, monkeypatch):
    import json
    from scripts import verify_retained_ci_test_evidence as replay
    log, manifest = _synthetic_full_shard(tmp_path, monkeypatch)
    receipt = evidence.build_receipt(
        log, context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS,
        selected_modules=manifest, shard=0,
    )
    receipt["python_version"] = replay.runtime.PINNED_VERSION_TEXT
    payload = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    kwargs = dict(checkout_sha=SHA, run_id="123456", run_attempt="1",
                  event="push", dependency_bytes=DEPS, shard=0)
    assert replay.verify_retained_evidence(log, payload, selected_modules=manifest, **kwargs) == receipt
    with pytest.raises(ValueError, match="inventory"):
        replay.verify_retained_evidence(
            log, payload, selected_modules=b"tests/test_01.py\n", **kwargs
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
    commands = test_step["run"]
    assert commands.strip().splitlines()[0] == "set -euo pipefail"
    assert "python -m scripts.select_full_ci_shard --verify-partition --shards 8" in commands
    assert '--shard "$VERA_SHARD" --shards 8' in commands
    assert 'bash scripts/run_offline_pytest_firewalled.sh "${test_modules[@]}" 2>&1 | tee -a "$RUNNER_TEMP/vera-offline-tests.log"' in commands
    assert '"$RUNNER_TEMP/vera-offline-test-modules.txt"' in commands
    verify_step = next(s for s in steps if s.get("name") == "Bind exact-commit offline test evidence")
    assert "python -m scripts.verify_ci_test_evidence" in verify_step["run"]
    for step in (verify_step, next(s for s in steps if
                s.get("name") == "Replay exact-commit offline test evidence before upload")):
        assert '--selected-modules "$RUNNER_TEMP/vera-offline-test-modules.txt"' in step["run"]
        assert '--shard "${{ matrix.shard }}"' in step["run"]
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


def test_physical_crlf_log_with_terminal_summary_is_valid():
    log = _log().replace(b"\n", b"\r\n")
    assert evidence.build_receipt(
        log, context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS
    )["test_counts"]["passed"] == 6


@pytest.mark.parametrize("bad_log", [
    _log() + b"unexpected output after summary\n",
    _log().rstrip(b"\n"),
    _log().replace(b"\n", b"\r", 1),
    _log().replace(b"\n", b"\xe2\x80\xa8", 1),
    _log().replace(b"\n", b"\xc2\x85", 1),
    _log().replace(
        evidence.FIREWALL_MARKER.encode(),
        b"reported: " + evidence.FIREWALL_MARKER.encode(),
    ),
    _log().splitlines()[1] + b"\n" + evidence.FIREWALL_MARKER.encode() + b"\n",
])
def test_rejects_out_of_order_nonterminal_or_forged_physical_ci_records(bad_log):
    with pytest.raises(ValueError):
        evidence.build_receipt(
            bad_log, context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS
        )
