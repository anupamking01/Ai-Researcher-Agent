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


def test_verbose_pytest_durations_footer_can_issue_complete_receipt():
    # Reproduces -vv --durations=10: last pytest line has both '=' borders.
    log = (
        evidence.FIREWALL_MARKER + "\n"
        "tests/test_example.py::test_one PASSED [100%]\n"
        "======================= slowest 10 durations =======================\n"
        "0.01s call     tests/test_example.py::test_one\n"
        "======================= 1 passed in 0.02s =======================\n"
    ).encode()
    receipt = evidence.build_receipt(
        log, context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS,
    )
    assert receipt["test_counts"] == {"passed": 1}
    assert receipt["pytest_elapsed_seconds"] == "0.02"


def test_verbose_summary_crlf_is_bound_by_independent_replay():
    import json
    from scripts import verify_retained_ci_test_evidence as replay

    log = _log(
        "================= 6 passed, 4 warnings in 1.25s (0:00:01) =================="
    ).replace(b"\n", b"\r\n")
    receipt = evidence.build_receipt(
        log, context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS,
    )
    receipt["python_version"] = replay.runtime.PINNED_VERSION_TEXT
    retained = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    assert replay.verify_retained_evidence(
        log, retained, checkout_sha=SHA, run_id="123456",
        run_attempt="1", event="push", dependency_bytes=DEPS,
    ) == receipt


@pytest.mark.parametrize("bad_summary", [
    "========== 1 passed in 0.02s",
    "1 passed in 0.02s ==========",
    "========== 1 failed, 1 passed in 0.02s ==========",
    "========== 1 passed, 1 xpassed in 0.02s ==========",
    "========== 1 passed, 2 deselected in 0.02s ==========",
    "========== 1 passed in 0.02s ========== garbage",
])
def test_decorated_pytest_summary_fails_closed_on_partial_or_unsafe_footer(
    bad_summary,
):
    with pytest.raises(ValueError):
        evidence.build_receipt(
            _log(bad_summary), context=CONTEXT,
            checkout_sha=SHA, dependency_bytes=DEPS,
        )


def test_duplicate_verbose_and_plain_summary_is_not_certified():
    log = _log(
        "============ 2 passed in 0.03s ============"
    ) + b"2 passed in 0.03s\n"
    with pytest.raises(ValueError, match="ambiguous"):
        evidence.build_receipt(
            log, context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS,
        )


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
    header = f"VERA full-suite shard 0/16; selected 1 modules; checkout {SHA}"
    log = (header + "\ntests/test_00.py\n" + evidence.FIREWALL_MARKER
           + "\ncollecting ... collected 1 items\n"
           + "tests/test_00.py::test_ok PASSED [100%]\n"
           + "1 passed in 0.2s\n").encode()
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
    assert receipt["full_ci_total_modules"] == 16
    assert receipt["full_ci_selected_modules_sha256"] == hashlib.sha256(manifest).hexdigest()


@pytest.mark.parametrize("mutation,reason", [
    ("missing_collection", "collection"),
    ("missing_completion", "collected and completed"),
    ("duplicated_completion", "duplicate completion node"),
    ("wrong_outcome", "per-test completion outcomes"),
])
def test_full_ci_receipt_rejects_inconsistent_verbose_completion(
    tmp_path, monkeypatch, mutation, reason,
):
    log, manifest = _synthetic_full_shard(tmp_path, monkeypatch)
    if mutation == "missing_collection":
        log = log.replace(b"collecting ... collected 1 items\n", b"")
    elif mutation == "missing_completion":
        log = log.replace(b"tests/test_00.py::test_ok PASSED [100%]\n", b"")
    elif mutation == "duplicated_completion":
        node = b"tests/test_00.py::test_ok PASSED [100%]\n"
        log = log.replace(node, node + node)
    elif mutation == "wrong_outcome":
        log = log.replace(b" PASSED [100%]", b" SKIPPED [100%]")
    with pytest.raises(ValueError, match=reason):
        evidence.build_receipt(
            log, context=CONTEXT, checkout_sha=SHA,
            dependency_bytes=DEPS, selected_modules=manifest, shard=0,
        )



@pytest.mark.parametrize("mutation,reason", [
    ("duplicate_node", "duplicate completion node"),
    ("unselected_module", "outside selected modules"),
    ("lookalike_module", "outside selected modules"),
    ("missing_node_identifier", "outside selected modules"),
])
def test_full_ci_rejects_count_preserving_node_substitution(
    tmp_path, monkeypatch, mutation, reason,
):
    # Counts and final footer stay green: provenance fails only on node ID.
    log, manifest = _synthetic_full_shard(tmp_path, monkeypatch)
    log = log.replace(
        b"collecting ... collected 1 items",
        b"collecting ... collected 2 items",
    ).replace(
        b"tests/test_00.py::test_ok PASSED [100%]\n",
        (
            b"tests/test_00.py::test_first PASSED [ 50%]\n"
            b"tests/test_00.py::test_second PASSED [100%]\n"
        ),
    ).replace(b"1 passed in 0.2s", b"2 passed in 0.2s")
    if mutation == "duplicate_node":
        log = log.replace(b"test_second", b"test_first")
    elif mutation == "unselected_module":
        log = log.replace(
            b"test_00.py::test_second", b"test_01.py::test_second",
        )
    elif mutation == "lookalike_module":
        log = log.replace(
            b"test_00.py::test_second", b"test_00.py.bak::test_second",
        )
    elif mutation == "missing_node_identifier":
        log = log.replace(
            b"tests/test_00.py::test_second", b"outside_test_second",
        )
    with pytest.raises(ValueError, match=reason):
        evidence.build_receipt(
            log, context=CONTEXT, checkout_sha=SHA,
            dependency_bytes=DEPS, selected_modules=manifest, shard=0,
        )


def test_full_ci_accepts_distinct_parameterized_node_ids_in_selected_module(
    tmp_path, monkeypatch,
):
    log, manifest = _synthetic_full_shard(tmp_path, monkeypatch)
    log = log.replace(
        b"collecting ... collected 1 items",
        b"collecting ... collected 2 items",
    ).replace(
        b"tests/test_00.py::test_ok PASSED [100%]\n",
        (
            b"tests/test_00.py::test_case[alpha with spaces] PASSED [ 50%]\n"
            b"tests/test_00.py::test_case[beta with spaces] PASSED [100%]\n"
        ),
    ).replace(b"1 passed in 0.2s", b"2 passed in 0.2s")
    receipt = evidence.build_receipt(
        log, context=CONTEXT, checkout_sha=SHA,
        dependency_bytes=DEPS, selected_modules=manifest, shard=0,
    )
    assert receipt["test_counts"]["passed"] == 2


def test_verbose_completion_handles_parameter_ids_with_spaces_and_skip_xfail():
    # Real pytest node IDs can include JSON, spaces, colons or bracketed text.
    evidence._verify_verbose_full_ci_progress(
        [
            "collecting ... collected 3 items",
            'tests/test_a.py::test_case[{"a": 1}-with spaces] PASSED       [ 33%]',
            "tests/test_b.py::test_skip SKIPPED [ 66%]",
            "tests/test_c.py::test_expected_failure XFAIL [100%]",
        ],
        expected={"passed": 1, "skipped": 1, "xfailed": 1},
    )


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



def test_full_ci_crlf_transcript_preserves_manifest_and_original_byte_digest(
    tmp_path, monkeypatch,
):
    """Valid CRLF evidence must bind the same exact selection without rewriting it."""
    import hashlib

    log, manifest = _synthetic_full_shard(tmp_path, monkeypatch)
    crlf_log = log.replace(b"\n", b"\r\n")
    receipt = evidence.build_receipt(
        crlf_log, context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS,
        selected_modules=manifest, shard=0,
    )
    assert receipt["full_ci_shard"] == 0
    assert receipt["full_ci_selected_module_count"] == 1
    assert receipt["log_sha256"] == hashlib.sha256(crlf_log).hexdigest()
    assert receipt["log_bytes"] == len(crlf_log)
    # Do not accidentally permit a bare CR to forge a separate physical record.
    with pytest.raises(ValueError, match="bare carriage"):
        evidence.build_receipt(
            crlf_log.replace(b"\r\n", b"\r", 1),
            context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS,
            selected_modules=manifest, shard=0,
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
    assert "python -m scripts.select_full_ci_shard --verify-partition --shards 16" in commands
    assert '--shard "$VERA_SHARD" --shards 16' in commands
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


def test_bounded_evidence_file_capture_at_limit_and_one_byte_over(tmp_path):
    path = tmp_path / "ci-log.txt"
    path.write_bytes(b"12345678")
    assert evidence.read_bounded_evidence(
        path, maximum=8, label="synthetic CI log"
    ) == b"12345678"
    with pytest.raises(ValueError, match="exceeds size limit"):
        evidence.read_bounded_evidence(
            path, maximum=7, label="synthetic CI log"
        )


def test_bounded_evidence_capture_rejects_direct_symlink_and_directory(tmp_path):
    target = tmp_path / "target"
    target.write_bytes(b"safe")
    alias = tmp_path / "alias"
    alias.symlink_to(target)
    with pytest.raises(ValueError, match="regular file"):
        evidence.read_bounded_evidence(alias, maximum=8, label="synthetic receipt")
    with pytest.raises(ValueError, match="regular file"):
        evidence.read_bounded_evidence(tmp_path, maximum=8, label="synthetic receipt")


def test_bounded_evidence_capture_rejects_fifo_without_blocking(tmp_path):
    import os
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO not supported on this OS")
    fifo = tmp_path / "untrusted-pipe"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular file"):
        evidence.read_bounded_evidence(fifo, maximum=8, label="synthetic log")


def test_bounded_evidence_capture_detects_same_inode_content_drift(tmp_path, monkeypatch):
    import os
    path = tmp_path / "ci-log.txt"
    path.write_bytes(b"before")
    original_fdopen = os.fdopen

    class MutatingReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def read(self, count):
            original = self.stream.read(count)
            path.write_bytes(b"after!")
            return original

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

    monkeypatch.setattr(
        evidence.os, "fdopen",
        lambda fd, mode, closefd=False: MutatingReader(
            original_fdopen(fd, mode, closefd=closefd)
        ),
    )
    with pytest.raises(ValueError, match="changed during capture"):
        evidence.read_bounded_evidence(
            path, maximum=64, label="synthetic CI log"
        )


def test_single_pytest_warning_is_a_valid_complete_receipt():
    # Real pytest writes "1 warning", not "1 warnings"; a passing shard
    # must not fail receipt replay merely for this grammatical variation.
    result = evidence.build_receipt(
        _log("832 passed, 1 warning in 12.81s"),
        context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS,
    )
    assert result["test_counts"] == {"passed": 832, "warnings": 1}


def test_mixed_singular_plural_warning_counts_remain_ambiguous():
    with pytest.raises(ValueError, match="duplicate"):
        evidence.build_receipt(
            _log("1 passed, 1 warning, 2 warnings in 0.1s"),
            context=CONTEXT, checkout_sha=SHA, dependency_bytes=DEPS,
        )


def test_bounded_evidence_capture_rejects_external_hardlink_alias(tmp_path):
    import os

    source = tmp_path / "downloaded-log.txt"
    source.write_bytes(b"unaltered bytes")
    outside = tmp_path / "external-alias.txt"
    os.link(source, outside)
    # Same bytes and inode are not enough: the second pathname can mutate the
    # supposedly retained log without touching its downloaded filename.
    with pytest.raises(ValueError, match="exactly one filesystem link"):
        evidence.read_bounded_evidence(
            source, maximum=64, label="synthetic CI log"
        )


def test_bounded_evidence_capture_rejects_same_byte_atomic_path_swap(
    tmp_path, monkeypatch,
):
    import os

    source = tmp_path / "downloaded-log.txt"
    source.write_bytes(b"same exact bytes")
    original_fdopen = os.fdopen

    class SwappingReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def read(self, count):
            captured = self.stream.read(count)
            replacement = tmp_path / "replacement.txt"
            replacement.write_bytes(captured)
            os.replace(replacement, source)
            return captured

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

    monkeypatch.setattr(
        evidence.os, "fdopen",
        lambda fd, mode, closefd=False: SwappingReader(
            original_fdopen(fd, mode, closefd=closefd)
        ),
    )
    # The original opened descriptor retains the same bytes/metadata, but the
    # downloaded pathname now resolves to another inode with identical bytes.
    with pytest.raises(ValueError, match="changed during capture"):
        evidence.read_bounded_evidence(
            source, maximum=64, label="synthetic CI log"
        )


def test_bounded_evidence_capture_rejects_unlinked_path_during_read(
    tmp_path, monkeypatch,
):
    import os

    source = tmp_path / "downloaded-receipt.json"
    source.write_bytes(b"retained bytes")
    original_fdopen = os.fdopen

    class UnlinkingReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def read(self, count):
            captured = self.stream.read(count)
            source.unlink()
            return captured

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

    monkeypatch.setattr(
        evidence.os, "fdopen",
        lambda fd, mode, closefd=False: UnlinkingReader(
            original_fdopen(fd, mode, closefd=closefd)
        ),
    )
    with pytest.raises(ValueError, match="changed during capture"):
        evidence.read_bounded_evidence(
            source, maximum=64, label="synthetic CI receipt"
        )
