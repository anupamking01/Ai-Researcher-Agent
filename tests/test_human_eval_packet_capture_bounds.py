"""Synthetic resource and provenance controls for blinded packet captures."""

import json
import os

import pytest

from scripts import build_human_eval_packet as packet


def test_source_capture_preserves_binary_bytes(tmp_path):
    path = tmp_path / "synthetic-source"
    raw = b"\x00 neutral \r\n\t \xff"
    path.write_bytes(raw)
    assert packet._read_regular_file_captured(path, label="source") == raw


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO not available")
def test_source_capture_rejects_fifo_without_writer(tmp_path):
    path = tmp_path / "substituted-fifo"
    os.mkfifo(path)
    with pytest.raises(ValueError, match="must be a regular file"):
        packet._read_regular_file_captured(path, label="source")


def test_source_capture_rejects_sparse_oversize_before_read(tmp_path, monkeypatch):
    path = tmp_path / "oversize"
    with path.open("wb") as handle:
        handle.truncate(65)
    monkeypatch.setattr(packet, "MAX_PACKET_CAPTURE_BYTES", 64)
    monkeypatch.setattr(packet.os, "read", lambda *args: pytest.fail("read before size check"))
    with pytest.raises(ValueError, match="packet-capture limit"):
        packet._read_regular_file_captured(path, label="source")


def test_source_capture_accepts_exact_size_bound(tmp_path, monkeypatch):
    path = tmp_path / "at-limit"
    path.write_bytes(b"z" * 64)
    monkeypatch.setattr(packet, "MAX_PACKET_CAPTURE_BYTES", 64)
    assert packet._read_regular_file_captured(path, label="source") == b"z" * 64


def test_source_capture_rejects_append_during_read(tmp_path, monkeypatch):
    path = tmp_path / "growing"
    path.write_bytes(b"initial")
    orig_read = os.read
    inode = path.stat().st_ino
    injected = []

    def injected_read(fd, size):
        data = orig_read(fd, size)
        if not injected and os.fstat(fd).st_ino == inode:
            with path.open("ab") as stream:
                stream.write(b"more")
            injected.append(True)
        return data

    monkeypatch.setattr(packet.os, "read", injected_read)
    with pytest.raises(ValueError, match="changed during capture"):
        packet._read_regular_file_captured(path, label="source")
    assert injected == [True]


def test_source_capture_rejects_truncate_during_read(tmp_path, monkeypatch):
    path = tmp_path / "shrinking"
    path.write_bytes(b"initial")
    orig_read = os.read
    inode = path.stat().st_ino
    injected = []

    def injected_read(fd, size):
        data = orig_read(fd, size)
        if not injected and os.fstat(fd).st_ino == inode:
            path.write_bytes(b"")
            injected.append(True)
        return data

    monkeypatch.setattr(packet.os, "read", injected_read)
    with pytest.raises(ValueError, match="replaced during capture"):
        packet._read_regular_file_captured(path, label="source")
    assert injected == [True]


def test_source_capture_rejects_premature_eof(tmp_path, monkeypatch):
    path = tmp_path / "input"
    path.write_bytes(b"not-empty")
    monkeypatch.setattr(packet.os, "read", lambda *args: b"")
    with pytest.raises(ValueError, match="changed during capture"):
        packet._read_regular_file_captured(path, label="source")


def test_aggregate_report_and_trace_budget_is_enforced(tmp_path, monkeypatch):
    trace_root = tmp_path / "outputs" / "experiment_traces"
    trace = trace_root / "D3" / "synthetic-d3-main-01.json"
    trace.parent.mkdir(parents=True)
    report = tmp_path / "outputs" / "synthetic-d3-main-01" / "research_report.md"
    report.parent.mkdir(parents=True)
    report.write_text("Neutral fixture report", encoding="utf-8")
    trace_body = {
        "schema_version": 2,
        "experiment": {"variant_id": "D3", "task_id": "main-01", "task_set_id": "synthetic"},
        "trace": {
            "run_id": "synthetic-d3-main-01", "variant_id": "D3",
            "task_id": "main-01", "task_set_id": "synthetic",
            "question": "Neutral question?", "completed": True,
            "report_path": "./outputs/synthetic-d3-main-01/research_report.pdf",
        },
    }
    source_bytes = json.dumps(trace_body).encode("utf-8")
    trace.write_bytes(source_bytes)
    monkeypatch.setattr(
        packet, "MAX_PACKET_CAPTURE_BYTES",
        len(source_bytes) + len(report.read_bytes()) - 1,
    )
    with pytest.raises(ValueError, match="aggregate packet source evidence"):
        packet._load_records(
            trace_root,
            task_manifest={"task_set_id": "synthetic", "tasks": {"main-01": "Neutral question?"}},
        )


def test_packet_preflight_rejects_unverifiable_output_without_reservation(
    tmp_path, monkeypatch
):
    output = tmp_path / "not-yet-created"
    record = {
        "task_id": "main-01", "variant_id": "D3", "run_id": "synthetic",
        "question": "Neutral question?",
        "report_markdown": "# Neutral report\n\n" + "neutral " * 40,
        "trace_path": "outputs/experiment_traces/D3/synthetic.json",
        "report_path": "outputs/synthetic/research_report.md",
        "trace_fingerprint": {"bytes": 1, "sha256": "0" * 64},
        "report_fingerprint": {"bytes": 1, "sha256": "0" * 64},
    }
    monkeypatch.setattr(
        packet, "_load_task_manifest",
        lambda *args: {
            "task_set_id": "synthetic", "bytes": 1, "sha256": "0" * 64,
            "tasks": {"main-01": "Neutral question?"},
        },
    )
    monkeypatch.setattr(packet, "_load_records", lambda *args, **kwargs: [record])
    monkeypatch.setattr(packet, "MAX_PACKET_CAPTURE_BYTES", 128)
    with pytest.raises(ValueError, match="packet-capture limit"):
        packet.build_packet(tmp_path / "traces", output, task_manifest_path=tmp_path / "tasks")
    assert not output.exists()
