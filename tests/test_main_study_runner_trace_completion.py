"""Synthetic, offline regression for noncanonical treatment completion gating."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from logic.experiment import ExperimentConfig
from scripts import run_budget_main_study as study

PRICING = {"models": {"fake": {"input": 1.0, "output": 1.0}}}


def _payload(run_id="run-1", completed=True, task="main-01",
             task_set="test-tasks", variant="D3"):
    return {
        "schema_version": 2,
        "experiment": {
            "variant_id": variant, "task_set_id": task_set, "task_id": task,
            "source_budget": 3 if variant == "D3" else 6,
        },
        "trace": {
            "run_id": run_id, "variant_id": variant, "task_set_id": task_set,
            "task_id": task, "completed": completed,
            "question": "Synthetic question",
            "source_budget": 3 if variant == "D3" else 6,
            "report_path": f"./outputs/{run_id}/research_report.md",
            "source_count": 0, "successful_source_count": 0,
            "failed_source_count": 0, "scheduled_urls": [],
            "successful_urls": [], "failed_urls": [], "query_count": 0,
            "search_call_count": 0, "latency_seconds": 1.0,
            "report_words": 2 if completed else 0,
            "model_call_count": 1, "unavailable_usage_call_count": 0,
            "prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
            "usage_accounting_status": "provider_usage_complete",
            "provider_usage_by_model": {"fake": {
                "model_calls": 1, "unavailable_calls": 0,
                "prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
            }},
        },
    }


def _write(root, payload):
    path = root / payload["trace"]["variant_id"] / (
        payload["trace"]["run_id"] + ".json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = root.parent / payload["trace"]["run_id"] / "research_report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("Synthetic report", encoding="utf-8")
    return path


def _check(
    root, monkeypatch, old=(), *, prior_fingerprints=None,
    prior_report_fingerprints=None, task_question="Synthetic question",
):
    monkeypatch.setattr(study, "TRACE_ROOT", root)
    if prior_fingerprints is None:
        prior_fingerprints = study._snapshot_treatment_traces(tuple(old))
    if prior_report_fingerprints is None:
        prior_report_fingerprints = study._snapshot_treatment_reports(tuple(old))
    return study._require_new_completed_trace(
        tuple(old), prior_fingerprints=prior_fingerprints,
        prior_report_fingerprints=prior_report_fingerprints,
        variant_id="D3", task_set_id="test-tasks",
        task_id="main-01", task_question=task_question,
        pricing=PRICING,
    )


def test_matching_completed_trace_has_verifiable_cost(tmp_path, monkeypatch):
    root = tmp_path / "traces"
    _write(root, _payload())
    assert _check(root, monkeypatch) == pytest.approx(0.000012)


@pytest.mark.parametrize("reported", [
    None, "", "Different study question", "Synthetic question ", True,
])
def test_completed_cell_rejects_changed_or_missing_question(
    tmp_path, monkeypatch, reported,
):
    """Matching variant/task IDs must not certify a substituted question."""
    root = tmp_path / "traces"
    payload = _payload()
    if reported is None:
        del payload["trace"]["question"]
    else:
        payload["trace"]["question"] = reported
    _write(root, payload)
    with pytest.raises(ValueError, match="task question differs from frozen task file"):
        _check(root, monkeypatch)


def test_completed_cell_accepts_exact_unicode_task_question(tmp_path, monkeypatch):
    root = tmp_path / "traces"
    payload = _payload()
    payload["trace"]["question"] = "Compare HTTP/2 vs HTTP/3 — π?"
    _write(root, payload)
    assert _check(
        root, monkeypatch, task_question="Compare HTTP/2 vs HTTP/3 — π?",
    ) == pytest.approx(0.000012)


def test_task_question_gate_is_wired_from_frozen_runner_task():
    root = Path(study.__file__).resolve().parents[1]
    source = (root / "scripts/run_budget_main_study.py").read_text(encoding="utf-8")
    assert 'task_question=task["question"]' in source
    assert 'expected_task_question=task_question' in source


def test_missing_trace_is_not_a_completed_treatment(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="exactly one new trace"):
        _check(tmp_path / "traces", monkeypatch)


@pytest.mark.parametrize(("variation", "message"), [
    ("incomplete", "valid completed trace"),
    ("wrong_task", "valid completed trace"),
    ("wrong_task_set", "valid completed trace"),
    ("wrong_variant", "wrong variant"),
    ("unaccounted_usage", "valid completed trace"),
    ("duplicate", "exactly one new trace"),
])
def test_completion_gate_rejects_bad_trace(
    tmp_path, monkeypatch, variation, message,
):
    root = tmp_path / "traces"
    p = _payload()
    if variation == "incomplete":
        p["trace"]["completed"] = False
        p["trace"]["report_words"] = 0
    elif variation == "wrong_task":
        p["trace"]["task_id"] = "main-99"
        p["experiment"]["task_id"] = "main-99"
    elif variation == "wrong_task_set":
        p["trace"]["task_set_id"] = "other-tasks"
        p["experiment"]["task_set_id"] = "other-tasks"
    elif variation == "wrong_variant":
        p = _payload(variant="D6")
    elif variation == "unaccounted_usage":
        p["trace"]["provider_usage_by_model"]["fake"]["unavailable_calls"] = 1
    _write(root, p)
    if variation == "duplicate":
        _write(root, _payload(run_id="run-2"))
    with pytest.raises(ValueError, match=message):
        _check(root, monkeypatch)


def test_disappeared_prior_trace_rejected(tmp_path, monkeypatch):
    root = tmp_path / "traces"
    old = _write(root, _payload(run_id="old"))
    pins = study._snapshot_treatment_traces((old,))
    old.unlink()
    _write(root, _payload())
    with pytest.raises(ValueError, match="without removing earlier"):
        _check(root, monkeypatch, old=(old,), prior_fingerprints=pins)


def test_unchanged_prior_trace_and_new_completed_trace_accepted(
    tmp_path, monkeypatch,
):
    root = tmp_path / "traces"
    old = _write(root, _payload(run_id="old"))
    pins = study._snapshot_treatment_traces((old,))
    _write(root, _payload())
    assert _check(
        root, monkeypatch, old=(old,), prior_fingerprints=pins,
    ) == pytest.approx(0.000012)


@pytest.mark.parametrize("mutation", ["different_bytes", "same_bytes_new_inode"])
def test_prior_trace_change_cannot_be_hidden_by_new_completed_trace(
    tmp_path, monkeypatch, mutation,
):
    root = tmp_path / "traces"
    old = _write(root, _payload(run_id="old"))
    pins = study._snapshot_treatment_traces((old,))
    _write(root, _payload())
    if mutation == "different_bytes":
        old.write_bytes(old.read_bytes() + b" ")
    else:
        replacement = old.with_suffix(".replacement")
        replacement.write_bytes(old.read_bytes())
        os.replace(replacement, old)
    with pytest.raises(ValueError, match="Prior treatment trace changed"):
        _check(root, monkeypatch, old=(old,), prior_fingerprints=pins)




@pytest.mark.parametrize("problem", [
    "absent", "empty", "wrong_words", "redirected", "misattributed",
])
def test_completion_gate_requires_source_bound_markdown_report(
    tmp_path, monkeypatch, problem,
):
    root = tmp_path / "traces"
    trace = _write(root, _payload())
    report = root.parent / "run-1" / "research_report.md"
    if problem == "absent":
        report.unlink()
    elif problem == "empty":
        report.write_text("", encoding="utf-8")
    elif problem == "wrong_words":
        report.write_text("One two three", encoding="utf-8")
    elif problem == "redirected":
        report.unlink()
        destination = tmp_path / "outsider.md"
        destination.write_text("Synthetic report", encoding="utf-8")
        report.symlink_to(destination)
    elif problem == "misattributed":
        payload = json.loads(trace.read_text(encoding="utf-8"))
        payload["trace"]["report_path"] = "./outputs/someone-else/research_report.md"
        trace.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="report"):
        _check(root, monkeypatch)


@pytest.mark.skipif(
    not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"),
    reason="requires POSIX nonblocking FIFO open",
)
def test_new_completed_report_rejects_fifo_without_blocking(
    tmp_path, monkeypatch,
):
    root = tmp_path / "traces"
    _write(root, _payload())
    report = root.parent / "run-1" / "research_report.md"
    report.unlink()
    os.mkfifo(report)
    real_open = os.open
    observed = []

    def require_nonblocking_open(path, flags, *args, **kwargs):
        if Path(path) == report:
            assert flags & os.O_NONBLOCK, "untrusted report FIFO may block at open"
            observed.append(flags)
        return real_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(study.os, "open", require_nonblocking_open)
        with pytest.raises(ValueError, match="bounded regular file"):
            _check(root, monkeypatch)
    assert observed


def test_new_completed_report_rejects_external_hardlink_alias(
    tmp_path, monkeypatch,
):
    root = tmp_path / "traces"
    _write(root, _payload())
    report = root.parent / "run-1" / "research_report.md"
    alias = tmp_path / "untracked-report-alias.md"
    os.link(report, alias)
    with pytest.raises(ValueError, match="bounded regular file"):
        _check(root, monkeypatch)
    assert alias.read_bytes() == b"Synthetic report"


@pytest.mark.parametrize("mutation", ["modified_bytes", "same_bytes_new_inode"])
def test_prior_report_change_cannot_be_hidden_by_new_completed_trace(
    tmp_path, monkeypatch, mutation,
):
    root = tmp_path / "traces"
    old = _write(root, _payload(run_id="old"))
    monkeypatch.setattr(study, "TRACE_ROOT", root)
    pins = study._snapshot_treatment_traces((old,))
    report_pins = study._snapshot_treatment_reports((old,))
    _write(root, _payload())
    report = root.parent / "old" / "research_report.md"
    if mutation == "modified_bytes":
        report.write_text("Modified report", encoding="utf-8")
    else:
        replacement = report.with_suffix(".replacement")
        replacement.write_bytes(report.read_bytes())
        os.replace(replacement, report)
    with pytest.raises(ValueError, match="Prior completed report changed"):
        _check(
            root, monkeypatch, old=(old,), prior_fingerprints=pins,
            prior_report_fingerprints=report_pins,
        )

@pytest.mark.parametrize("malformed_trace", [False, True])
def test_agent_return_without_valid_trace_stops_and_records_failure(
    tmp_path, monkeypatch, malformed_trace,
):
    """The stub never performs provider calls or publishes experimental data."""
    monkeypatch.setattr(study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(study, "TRACE_ROOT", tmp_path / "outputs" / "experiment_traces")
    monkeypatch.setattr(study.sys, "argv", [
        "run_budget_main_study.py", "--noncanonical-replication-ack",
        study.NONCANONICAL_REPLICATION_ACK,
    ])
    for name, value in {
        "OPENAI_API_KEY": "synthetic-nonsecret", "SMART_LLM_MODEL": "fake",
        "FAST_LLM_MODEL": "fake", "TEMPERATURE": "1",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(study, "_load_task_file", lambda *_: (
        "test-tasks", [{"id": "main-01", "question": "Synthetic question"}],
        {"path": "test.json", "size_bytes": 2, "sha256": "0" * 64},
    ))
    monkeypatch.setattr(study, "_load_pricing", lambda *_: (
        PRICING, {"path": "rates.json", "size_bytes": 2, "sha256": "0" * 64},
    ))
    monkeypatch.setattr(study, "_git_source_state", lambda: {
        "commit": "a" * 40, "tree": "b" * 40,
    })
    monkeypatch.setattr(study, "_execution_environment", lambda: {})
    monkeypatch.setattr(study, "_verify_repository_module_origin", lambda *_: None)
    attempts = []

    async def fake_agent(**kwargs):
        attempts.append(kwargs["experiment_config"].variant_id)
        if malformed_trace:
            broken = study.TRACE_ROOT / "D3" / "run-1.json"
            broken.parent.mkdir(parents=True, exist_ok=True)
            broken.write_text("{not valid JSON", encoding="utf-8")
        return "Synthetic report", "synthetic-report.md"

    actual_import = study.importlib.import_module
    def fake_import(name):
        if name == "logic.experiment":
            return SimpleNamespace(ExperimentConfig=ExperimentConfig)
        if name == "logic.run":
            return SimpleNamespace(run_agent=fake_agent)
        return actual_import(name)

    monkeypatch.setattr(study.importlib, "import_module", fake_import)
    with pytest.raises(SystemExit, match="stopped after D3/main-01 status=failed"):
        asyncio.run(study._run_main_study())
    progress = json.loads(
        (tmp_path / "outputs" / "main_study_progress.json").read_text()
    )
    assert attempts == ["D3"]
    assert progress["attempted_runs"] == 1
    assert progress["completed_runs"] == 0
    assert progress["failed_runs"] == 1
    assert progress["current"] is None
    assert progress["events"][0]["status"] == "failed"
    if malformed_trace:
        assert progress["estimated_treatment_cost_usd"] is None
        assert progress["trace_cost_reconciliation"] == "unverifiable"
        assert "post-treatment trace spend cannot be verified" in progress["events"][0]["error"]
    else:
        assert progress["estimated_treatment_cost_usd"] == 0
        assert progress["trace_cost_reconciliation"] == "recomputed_from_retained_traces"
        assert "exactly one new trace" in progress["events"][0]["error"]


def test_completed_report_gate_reuses_bounded_trace_capture(
    tmp_path, monkeypatch,
):
    root = tmp_path / "traces"
    trace_path = _write(root, _payload())
    original_read = study._read_treatment_trace_bytes
    captures = []

    def guarded_capture(path):
        captures.append(path)
        if len(captures) == 2:
            raise SystemExit("synthetic second-trace-capture rejection")
        return original_read(path)

    monkeypatch.setattr(study, "_read_treatment_trace_bytes", guarded_capture)
    with pytest.raises(ValueError, match="second-trace-capture rejection"):
        _check(root, monkeypatch)
    assert captures == [trace_path, trace_path]


@pytest.mark.parametrize("kind", ["trace", "report"])
def test_prior_fingerprint_refuses_oversized_sparse_evidence_before_read(
    tmp_path, monkeypatch, kind,
):
    root = tmp_path / "traces"
    old = _write(root, _payload(run_id="old"))
    monkeypatch.setattr(study, "TRACE_ROOT", root)
    if kind == "trace":
        path = old
        limit = study._MAX_TREATMENT_TRACE_BYTES
        snapshot = lambda: study._snapshot_treatment_traces((old,))
    else:
        path = study._completed_report_markdown(old)
        limit = study._MAX_COMPLETED_REPORT_BYTES
        snapshot = lambda: study._snapshot_treatment_reports((old,))
    with path.open("r+b") as stream:
        stream.truncate(limit + 1)

    with monkeypatch.context() as patch:
        patch.setattr(
            study.os, "fdopen",
            lambda *args, **kwargs: pytest.fail("oversized prior evidence was opened for reading"),
        )
        with pytest.raises(ValueError, match="bounded single-link regular file"):
            snapshot()


@pytest.mark.parametrize("kind", ["trace", "report"])
def test_prior_fingerprint_refuses_uninventoried_hardlink_alias(
    tmp_path, monkeypatch, kind,
):
    root = tmp_path / "traces"
    old = _write(root, _payload(run_id="old"))
    monkeypatch.setattr(study, "TRACE_ROOT", root)
    path = old if kind == "trace" else study._completed_report_markdown(old)
    alias = tmp_path / f"untracked-{kind}-alias"
    os.link(path, alias)

    with pytest.raises(ValueError, match="bounded single-link regular file"):
        if kind == "trace":
            study._snapshot_treatment_traces((old,))
        else:
            study._snapshot_treatment_reports((old,))
    assert alias.read_bytes() == path.read_bytes()


@pytest.mark.skipif(
    not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"),
    reason="requires POSIX nonblocking FIFO open",
)
def test_prior_trace_fingerprint_rejects_fifo_without_blocking(
    tmp_path, monkeypatch,
):
    root = tmp_path / "traces"
    old = _write(root, _payload(run_id="old"))
    old.unlink()
    os.mkfifo(old)
    actual_open = os.open
    observed = []

    def require_nonblocking_open(path, flags, *args, **kwargs):
        if Path(path) == old:
            assert flags & os.O_NONBLOCK, "opening an untrusted FIFO could block"
            observed.append(flags)
        return actual_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(study.os, "open", require_nonblocking_open)
        with pytest.raises(ValueError, match="bounded single-link regular file"):
            study._snapshot_treatment_traces((old,))
    assert observed

@pytest.mark.parametrize("reader_kind", [
    "new_trace", "new_report", "prior_fingerprint",
])
def test_published_evidence_path_cannot_swap_parent_directory_after_open(
    tmp_path, monkeypatch, reader_kind,
):
    """Reject same-byte replacement through parent relocation after fd open.

    Moving the parent keeps the old inode, its link, bytes, and timestamps
    unchanged; the filename becomes a different inode. No live runs are made.
    """
    root = tmp_path / "traces"
    trace = _write(root, _payload())
    monkeypatch.setattr(study, "TRACE_ROOT", root)
    target = (
        root.parent / "run-1" / "research_report.md"
        if reader_kind == "new_report" else trace
    )
    original_inode = target.stat().st_ino
    original_bytes = target.read_bytes()
    original_fdopen = study.os.fdopen
    relocated_dirs = []

    def redirect_after_fstat(fd, *args, **kwargs):
        stream = original_fdopen(fd, *args, **kwargs)
        if not relocated_dirs and os.fstat(fd).st_ino == original_inode:
            relocated = target.parent.with_name(target.parent.name + "-relocated")
            os.rename(target.parent, relocated)
            target.parent.mkdir()
            target.write_bytes(original_bytes)
            relocated_dirs.append(relocated)
        return stream

    with monkeypatch.context() as patch:
        patch.setattr(study.os, "fdopen", redirect_after_fstat)
        with pytest.raises(
            (SystemExit, ValueError), match="published path changed during capture"
        ):
            if reader_kind == "new_trace":
                study._read_treatment_trace_bytes(trace)
            elif reader_kind == "new_report":
                study._require_completed_report(trace)
            else:
                study._trace_file_fingerprint(
                    trace, max_bytes=study._MAX_TREATMENT_TRACE_BYTES,
                )
    assert relocated_dirs, "test must redirect the parent after descriptor open"
    assert target.read_bytes() == original_bytes

@pytest.mark.parametrize("drift", [
    "before_treatment", "during_treatment", "unattestable_after_treatment",
])
def test_source_drift_fails_closed_and_records_failed_cell(
    tmp_path, monkeypatch, drift,
):
    """Synthetic Git provenance changes never start a second agent treatment."""
    monkeypatch.setattr(study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        study, "TRACE_ROOT", tmp_path / "outputs" / "experiment_traces",
    )
    monkeypatch.setattr(study.sys, "argv", [
        "run_budget_main_study.py", "--noncanonical-replication-ack",
        study.NONCANONICAL_REPLICATION_ACK,
    ])
    for name, value in {
        "OPENAI_API_KEY": "synthetic-nonsecret",
        "SMART_LLM_MODEL": "fake", "FAST_LLM_MODEL": "fake",
        "TEMPERATURE": "1",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(study, "_load_task_file", lambda *_: (
        "test-tasks", [{"id": "main-01", "question": "Synthetic question"}],
        {"path": "test.json", "size_bytes": 2, "sha256": "0" * 64},
    ))
    monkeypatch.setattr(study, "_load_pricing", lambda *_: (
        PRICING, {"path": "rates.json", "size_bytes": 2, "sha256": "0" * 64},
    ))
    monkeypatch.setattr(study, "_execution_environment", lambda: {})
    monkeypatch.setattr(study, "_verify_repository_module_origin", lambda *_: None)

    calls = []
    source_checks = []

    def synthetic_source_state():
        source_checks.append(len(calls))
        if drift == "before_treatment" and len(source_checks) >= 3:
            return {"commit": "f" * 40, "tree": "b" * 40}
        if calls and drift == "during_treatment":
            return {"commit": "a" * 40, "tree": "f" * 40}
        if calls and drift == "unattestable_after_treatment":
            raise SystemExit("synthetic dirty checkout")
        return {"commit": "a" * 40, "tree": "b" * 40}

    monkeypatch.setattr(study, "_git_source_state", synthetic_source_state)

    async def fake_agent(**kwargs):
        calls.append(kwargs["experiment_config"].variant_id)
        _write(study.TRACE_ROOT, _payload())
        return "Synthetic report", "synthetic-report.md"

    original_import = study.importlib.import_module

    def fake_import(name):
        if name == "logic.experiment":
            return SimpleNamespace(ExperimentConfig=ExperimentConfig)
        if name == "logic.run":
            return SimpleNamespace(run_agent=fake_agent)
        return original_import(name)

    monkeypatch.setattr(study.importlib, "import_module", fake_import)
    with pytest.raises(
        SystemExit, match="stopped after D3/main-01 status=failed"
    ):
        asyncio.run(study._run_main_study())

    progress = json.loads(
        (tmp_path / "outputs" / "main_study_progress.json").read_text()
    )
    assert calls == ([] if drift == "before_treatment" else ["D3"])
    assert len(source_checks) >= 3
    assert progress["attempted_runs"] == progress["failed_runs"] == 1
    assert progress["completed_runs"] == progress["timeout_runs"] == 0
    assert progress["current"] is None
    assert progress["events"][0]["status"] == "failed"
    assert (
        "Git source identity changed" in progress["events"][0]["error"]
        if drift != "unattestable_after_treatment"
        else "Cannot attest main-study Git sources" in progress["events"][0]["error"]
    )


def _single_tracked_source_git(monkeypatch, tmp_path, content=b"safe source"):
    """One synthetic clean Git tree without invoking Git or model providers."""
    source = tmp_path / "tracked.py"
    source.write_bytes(content)
    raw_oid = hashlib.sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest().encode("ascii")
    tree_record = b"100644 blob " + raw_oid + b"\ttracked.py\0"

    def fake_check_output(command, **kwargs):
        assert command[0] == "git"
        if command[1:3] == ["rev-parse", "--show-toplevel"]:
            return str(tmp_path) + "\n"
        if command[1:3] == ["rev-parse", "--verify"]:
            return ("a" if command[3] == "HEAD^{commit}" else "b") * 40 + "\n"
        if command[1] == "status":
            return ""
        if command[1] == "ls-files":
            return "H tracked.py\0"
        if command[1] == "ls-tree":
            return tree_record
        raise AssertionError(f"unexpected synthetic Git command: {command!r}")

    monkeypatch.setattr(study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(study.subprocess, "check_output", fake_check_output)
    return source


def test_git_source_gate_streams_attested_clean_blob(tmp_path, monkeypatch):
    _single_tracked_source_git(monkeypatch, tmp_path)
    assert study._git_source_state() == {"commit": "a" * 40, "tree": "b" * 40}


@pytest.mark.skipif(
    not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"),
    reason="requires POSIX nonblocking FIFO open",
)
def test_git_source_gate_rejects_fifo_without_blocking(tmp_path, monkeypatch):
    source = _single_tracked_source_git(monkeypatch, tmp_path)
    source.unlink()
    os.mkfifo(source)
    real_open = os.open
    seen = []

    def require_nonblocking_open(path, flags, *args, **kwargs):
        if Path(path) == source:
            assert flags & os.O_NONBLOCK, "tracked FIFO must not block at open"
            seen.append(True)
        return real_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(study.os, "open", require_nonblocking_open)
        with pytest.raises(SystemExit, match="Cannot attest exact Git source bytes"):
            study._git_source_state()
    assert seen


def test_git_source_gate_rejects_oversized_sparse_tracked_file(tmp_path, monkeypatch):
    source = _single_tracked_source_git(monkeypatch, tmp_path)
    with source.open("wb") as handle:
        handle.truncate(study._MAX_TRACKED_SOURCE_BYTES + 1)
    with pytest.raises(SystemExit, match="Cannot attest exact Git source bytes"):
        study._git_source_state()


def test_git_source_gate_rejects_external_hardlink(tmp_path, monkeypatch):
    source = _single_tracked_source_git(monkeypatch, tmp_path)
    os.link(source, tmp_path / "other_alias.py")
    with pytest.raises(SystemExit, match="Cannot attest exact Git source bytes"):
        study._git_source_state()


def test_git_source_gate_detects_same_bytes_published_path_swap(tmp_path, monkeypatch):
    source = _single_tracked_source_git(monkeypatch, tmp_path)
    real_open = os.open
    swapped = []

    def replace_after_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if Path(path) == source and not swapped:
            old = tmp_path / "removed-original.py"
            os.replace(source, old)
            source.write_bytes(old.read_bytes())
            swapped.append(True)
        return fd

    with monkeypatch.context() as patch:
        patch.setattr(study.os, "open", replace_after_open)
        with pytest.raises(SystemExit, match="Cannot attest exact Git source bytes"):
            study._git_source_state()
    assert swapped


@pytest.mark.parametrize("unlisted_entry", [
    "unknown_variant_directory",
    "loose_root_file",
    "ignored_variant_file",
])
def test_noncanonical_trace_inventory_rejects_unlisted_evidence(
    tmp_path, monkeypatch, unlisted_entry,
):
    """Unpriced leftovers must not disappear from an apparent empty inventory."""
    root = tmp_path / "outputs" / "experiment_traces"
    original = _write(root, _payload())
    monkeypatch.setattr(study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(study, "TRACE_ROOT", root)
    if unlisted_entry == "unknown_variant_directory":
        hidden = root / "ARCHIVED" / "note.txt"
        hidden.parent.mkdir()
    elif unlisted_entry == "loose_root_file":
        hidden = root / "detached.json"
    else:
        hidden = root / "D3" / "hidden-trace.txt"
    hidden.write_text("Synthetic ignored evidence", encoding="utf-8")

    with pytest.raises(SystemExit, match="Unexpected treatment trace"):
        study._treatment_trace_paths()
    with pytest.raises(SystemExit, match="Unexpected treatment trace"):
        study._preflight_new_study_state(PRICING)
    assert original.exists()
    assert not (root.parent / "main_study_manifest.json").exists()


def test_noncanonical_trace_inventory_accepts_only_known_json_cells(
    tmp_path, monkeypatch,
):
    root = tmp_path / "traces"
    d3 = _write(root, _payload())
    d6 = _write(root, _payload(run_id="d6-run", variant="D6"))
    monkeypatch.setattr(study, "TRACE_ROOT", root)
    assert study._treatment_trace_paths() == tuple(sorted((d3, d6)))


def test_post_treatment_unlisted_trace_is_reportable_validation_failure(
    tmp_path, monkeypatch,
):
    root = tmp_path / "traces"
    _write(root, _payload())
    (root / "D3" / "unpriced.tmp").write_text("Synthetic extra file", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid treatment trace inventory after execution"):
        _check(root, monkeypatch)
