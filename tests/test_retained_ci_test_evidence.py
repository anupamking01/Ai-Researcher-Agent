"""Synthetic-only tamper tests for downloaded offline test-evidence pairs."""
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
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _verify(log=LOG, receipt=None, *, deps=DEPS, sha=SHA, run_id=RUN_ID,
            attempt="1", event="push"):
    return replay.verify_retained_evidence(
        log, _receipt() if receipt is None else receipt,
        checkout_sha=sha, run_id=run_id, run_attempt=attempt, event=event,
        dependency_bytes=deps,
    )


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
