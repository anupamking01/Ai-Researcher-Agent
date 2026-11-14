"""Synthetic-only tamper tests for downloaded offline test-evidence pairs."""
import hashlib
import json

import pytest

from scripts import verify_ci_test_evidence as producer
from scripts import verify_retained_ci_test_evidence as replay


SHA = "a" * 40
RUN_ID = "123456"
DEPS = {"requirements.txt": b"app-deps", "requirements-ci.lock": b"ci-pins"}
CONTEXT = {
    "GITHUB_REPOSITORY": "anupamking01/Ai-Researcher-Agent",
    "GITHUB_SHA": SHA,
    "GITHUB_RUN_ID": RUN_ID,
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_EVENT_NAME": "push",
}
LOG = (producer.FIREWALL_MARKER + "\n7 passed, 2 warnings in 0.23s\n").encode()


def _receipt(log=LOG, *, context=CONTEXT, deps=DEPS):
    value = producer.build_receipt(
        log, context=context, checkout_sha=context["GITHUB_SHA"],
        dependency_bytes=deps,
    )
    # Synthetic receipt represents the pinned CI interpreter, not this test host.
    value["python_version"] = replay.runtime.PINNED_VERSION_TEXT
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _verify(log=LOG, receipt=None, *, deps=DEPS, sha=SHA, run_id=RUN_ID,
            attempt="1", event="push"):
    return replay.verify_retained_evidence(
        log, _receipt() if receipt is None else receipt,
        checkout_sha=sha, run_id=run_id, run_attempt=attempt, event=event,
        dependency_bytes=deps,
    )


@pytest.mark.parametrize("summary,label", [
    ("7 passed, 2 deselected in 0.23s", "deselected"),
    ("7 passed, 1 xpassed in 0.23s", "xpassed"),
])
def test_replay_rejects_coherently_rehashed_pruned_or_xpassed_receipts(summary, label):
    changed_log = (producer.FIREWALL_MARKER + "\n" + summary + "\n").encode()
    forged = json.loads(_receipt())
    forged["test_counts"] = {"passed": 7, label: 2 if label == "deselected" else 1}
    forged["log_bytes"] = len(changed_log)
    forged["log_sha256"] = hashlib.sha256(changed_log).hexdigest()
    forged_bytes = (json.dumps(forged, sort_keys=True, indent=2) + "\n").encode()
    with pytest.raises(ValueError, match="deselected|unexpectedly passing"):
        _verify(log=changed_log, receipt=forged_bytes)


def test_unchanged_source_bound_receipt_replays():
    assert _verify()["test_counts"] == {"passed": 7, "warnings": 2}


def test_a_pr_synthetic_merge_sha_and_event_can_be_independently_pinned():
    context = {**CONTEXT, "GITHUB_EVENT_NAME": "pull_request", "GITHUB_SHA": "b" * 40}
    assert _verify(receipt=_receipt(context=context), sha="b" * 40,
                   event="pull_request")["workflow_event"] == "pull_request"


@pytest.mark.parametrize("override", [
    {"log": LOG + b"unexpected appended output\n"},
    {"log": LOG.replace(b"7 passed", b"6 passed")},
    {"deps": {**DEPS, "requirements-ci.lock": b"altered"}},
    {"sha": "b" * 40},
    {"run_id": "123457"},
    {"attempt": "2"},
    {"event": "pull_request"},
])
def test_rejects_changed_log_deps_or_independent_identity(override):
    with pytest.raises(ValueError):
        _verify(**override)


@pytest.mark.parametrize("key,value", [
    ("test_counts", {"passed": 8, "warnings": 2}),
    ("schema_version", True),
    ("firewall_activation_marker_observed", 1),
    ("original_treatment_authenticated", True),
    ("python_version", "../../other"),
    ("python_version", "3.11.16"),
    ("python_version", "3.12.0"),
    ("workflow_event", "pull_request"),
])
def test_rejects_modified_receipt_fields_even_if_canonically_serialized(key, value):
    receipt = json.loads(_receipt())
    receipt[key] = value
    corrupted = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    with pytest.raises(ValueError):
        _verify(receipt=corrupted)


@pytest.mark.parametrize("corrupt", [
    b"", b"{" + b" " * replay.MAX_RECEIPT_BYTES,
    b'{"schema_version": 1, "schema_version": 1}',
    b'\xff', b'[]',
    _receipt().replace(b'"schema_version": 1', b'"schema_version": 1.0'),
    _receipt().replace(b'"schema_version": 1', b'"schema_version": NaN'),
    _receipt().replace(b'  "schema_version"', b'\t"schema_version"'),
])
def test_rejects_noncanonical_ambiguous_or_invalid_receipts(corrupt):
    with pytest.raises(ValueError):
        _verify(receipt=corrupt)

# The replay function above verifies receipt arithmetic. The CLI additionally
# must verify the *actual checkout bytes*: rev-parse HEAD alone accepts a dirty
# working tree with unchanged revision and unchanged receipt inputs.
def _offline_replay_cli_fixture(tmp_path, monkeypatch):
    import subprocess
    import sys

    checkout = tmp_path / "checkout"
    checkout.mkdir()

    def git(*arguments):
        return subprocess.check_output(
            ["git", "-C", str(checkout), *arguments],
            text=True,
        ).strip()

    git("init", "-q")
    git("config", "user.email", "vera-synthetic@example.invalid")
    git("config", "user.name", "VERA Synthetic")
    (checkout / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    for name, content in DEPS.items():
        (checkout / name).write_bytes(content)
    git("add", ".")
    git("commit", "-qm", "synthetic clean replay checkout")
    sha = git("rev-parse", "HEAD")

    log_file = tmp_path / "retained-log.txt"
    receipt_file = tmp_path / "retained-receipt.json"
    log_file.write_bytes(LOG)
    receipt_file.write_bytes(_receipt(context={**CONTEXT, "GITHUB_SHA": sha}))

    monkeypatch.setattr(producer, "ROOT", checkout)
    monkeypatch.setattr(sys, "argv", [
        "verify_retained_ci_test_evidence",
        "--log", str(log_file),
        "--receipt", str(receipt_file),
        "--checkout-sha", sha,
        "--run-id", RUN_ID,
        "--run-attempt", "1",
        "--event", "push",
    ])
    return checkout, git


def test_replay_cli_accepts_clean_exact_source_checkout(tmp_path, monkeypatch, capsys):
    _offline_replay_cli_fixture(tmp_path, monkeypatch)
    assert replay.main() == 0
    assert "LOCALLY CONSISTENT" in capsys.readouterr().out


@pytest.mark.parametrize("change", ["tracked_edit", "hidden_tracked_edit", "untracked_file"])
def test_replay_cli_rejects_modified_source_despite_same_head(
    tmp_path, monkeypatch, capsys, change,
):
    checkout, git = _offline_replay_cli_fixture(tmp_path, monkeypatch)
    if change == "hidden_tracked_edit":
        git("update-index", "--assume-unchanged", "source.py")
    if change in ("tracked_edit", "hidden_tracked_edit"):
        (checkout / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
    else:
        (checkout / "unreviewed_test.py").write_text(
            "def test_other(): pass\n", encoding="utf-8"
        )
    # All three cases still have the original Git HEAD. The hidden edit even
    # preserves an apparently clean porcelain status.
    if change == "hidden_tracked_edit":
        assert git("status", "--porcelain") == ""
    with pytest.raises(SystemExit) as caught:
        replay.main()
    assert caught.value.code == 1
    assert "VERA RETAINED CI EVIDENCE: FAIL" in capsys.readouterr().err
