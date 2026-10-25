"""Synthetic regression tests for whole-window blinded-packet evidence custody.

All records are constructed locally and contain no human ratings or real runs.
"""

import csv
import json
import os
from pathlib import Path

import pytest

from scripts import build_human_eval_packet as build
from scripts import verify_human_eval_packet as verifier


@pytest.fixture
def packet_case(tmp_path):
    manifest_path = tmp_path / "experiments" / "main_budget_tasks.json"
    manifest_path.parent.mkdir(parents=True)
    task_set = "synthetic-packet-custody"
    question = "What is a synthetic test fixture?"
    manifest_path.write_text(
        json.dumps({
            "task_set_id": task_set,
            "frozen_before_execution": True,
            "tasks": [{"id": "main-01", "question": question}],
        }) + "\n",
        encoding="utf-8",
    )
    trace_root = tmp_path / "outputs" / "experiment_traces"
    for variant in build.EXPECTED_VARIANTS:
        run_id = f"{variant.lower()}-main-01"
        report = tmp_path / "outputs" / run_id / "research_report.md"
        report.parent.mkdir(parents=True)
        report.write_text("# Synthetic test report\n\nNeutral content.\n", encoding="utf-8")
        trace = trace_root / variant / f"{run_id}.json"
        trace.parent.mkdir(parents=True)
        trace.write_text(json.dumps({
            "schema_version": 2,
            "experiment": {
                "variant_id": variant, "task_id": "main-01",
                "task_set_id": task_set,
            },
            "trace": {
                "run_id": run_id, "variant_id": variant,
                "task_id": "main-01", "task_set_id": task_set,
                "question": question, "completed": True,
                "report_path": f"./outputs/{run_id}/research_report.pdf",
            },
        }), encoding="utf-8")
    output = tmp_path / "outputs" / "human_eval"
    build.build_packet(trace_root, output, task_manifest_path=manifest_path)
    with (output / "blinding_key.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(build.EXPECTED_VARIANTS)
    return tmp_path, manifest_path, output, rows


def _verify(case):
    root, task_manifest, output, _ = case
    return verifier.verify_packet(
        repo_root=root, task_manifest_path=task_manifest, output_root=output
    )


def _inject_after_source(monkeypatch, trigger: Path, action):
    original = verifier._require_regular_file
    fired = []

    def monitored(path, *, label):
        content = original(path, label=label)
        if Path(path) == trigger and not fired:
            fired.append(True)
            action()
        return content

    monkeypatch.setattr(verifier, "_require_regular_file", monitored)
    return fired


def test_unmodified_synthetic_packet_still_verifies(packet_case):
    result = _verify(packet_case)
    assert result["status"] == "human_eval_packet_verified"
    assert result["human_ratings_read"] is False


def test_earlier_trace_appended_after_its_check_is_rejected(packet_case, monkeypatch):
    root, _, _, rows = packet_case
    first = root / rows[0]["trace_path"]
    second = root / rows[1]["trace_path"]
    fired = _inject_after_source(
        monkeypatch, second, lambda: first.write_bytes(first.read_bytes() + b"\n")
    )
    with pytest.raises(ValueError, match="packet evidence changed during verification"):
        _verify(packet_case)
    assert fired == [True]


def test_earlier_trace_same_byte_inode_replacement_is_rejected(packet_case, monkeypatch):
    root, _, _, rows = packet_case
    first = root / rows[0]["trace_path"]
    second = root / rows[1]["trace_path"]

    def replace_same_bytes():
        temporary = first.with_suffix(".replacement")
        temporary.write_bytes(first.read_bytes())
        os.replace(temporary, first)

    fired = _inject_after_source(monkeypatch, second, replace_same_bytes)
    with pytest.raises(ValueError, match="packet evidence changed during verification"):
        _verify(packet_case)
    assert fired == [True]


def test_previously_checked_report_drift_is_rejected(packet_case, monkeypatch):
    root, _, _, rows = packet_case
    first_report = root / rows[0]["report_path"]
    second_trace = root / rows[1]["trace_path"]
    fired = _inject_after_source(
        monkeypatch, second_trace,
        lambda: first_report.write_bytes(first_report.read_bytes() + b"\n"),
    )
    with pytest.raises(ValueError, match="packet evidence changed during verification"):
        _verify(packet_case)
    assert fired == [True]


def test_task_manifest_change_after_parse_is_rejected(packet_case, monkeypatch):
    root, task_manifest, _, rows = packet_case
    trigger = root / rows[0]["trace_path"]
    fired = _inject_after_source(
        monkeypatch, trigger,
        lambda: task_manifest.write_bytes(task_manifest.read_bytes() + b"\n"),
    )
    with pytest.raises(ValueError, match="packet evidence changed during verification"):
        _verify(packet_case)
    assert fired == [True]


def test_packet_manifest_same_byte_replacement_is_rejected(packet_case, monkeypatch):
    root, _, output, rows = packet_case
    manifest = output / "manifest.json"
    trigger = root / rows[0]["trace_path"]

    def replace_same_bytes():
        replacement = output / "replacement.tmp"
        replacement.write_bytes(manifest.read_bytes())
        os.replace(replacement, manifest)

    fired = _inject_after_source(monkeypatch, trigger, replace_same_bytes)
    with pytest.raises(ValueError, match="packet evidence changed during verification"):
        _verify(packet_case)
    assert fired == [True]
