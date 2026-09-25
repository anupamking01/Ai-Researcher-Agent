"""Synthetic checks for annotator-safe human-evaluation distribution bundles."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import build_human_eval_packet as build
from scripts import export_human_eval_annotator_bundle as exporter


def _task_manifest(root: Path) -> Path:
    path = root / "experiments" / "main_budget_tasks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_set_id": "main-budget-v1-test",
        "frozen_before_execution": True,
        "tasks": [
            {"id": "main-01", "question": "Synthetic question one?"},
            {"id": "main-02", "question": "Synthetic question two?"},
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _source(root: Path, variant: str, task_id: str, question: str) -> None:
    run_id = f"{variant.lower()}-{task_id}"
    report = root / "outputs" / run_id / "research_report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        f"# Synthetic report\n\nNeutral fixture for {task_id}.\n",
        encoding="utf-8",
    )
    trace = root / "outputs" / "experiment_traces" / variant / f"{run_id}.json"
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text(
        json.dumps(
            {
                "experiment": {
                    "variant_id": variant,
                    "task_id": task_id,
                    "task_set_id": "main-budget-v1-test",
                },
                "trace": {
                    "run_id": run_id,
                    "variant_id": variant,
                    "task_id": task_id,
                    "question": question,
                    "completed": True,
                    "report_path": f"./outputs/{run_id}/research_report.pdf",
                },
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def packet_case(tmp_path: Path):
    task_manifest = _task_manifest(tmp_path)
    tasks = json.loads(task_manifest.read_text(encoding="utf-8"))["tasks"]
    for task in tasks:
        for variant in build.EXPECTED_VARIANTS:
            _source(tmp_path, variant, task["id"], task["question"])
    packet_root = tmp_path / "outputs" / "human_eval"
    build.build_packet(
        tmp_path / "outputs" / "experiment_traces",
        packet_root,
        seed=20260925,
        task_manifest_path=task_manifest,
    )
    return {
        "repo_root": tmp_path,
        "packet_root": packet_root,
        "task_manifest": task_manifest,
        "export_root": tmp_path / "annotator-distribution",
    }


def _export(case):
    return exporter.export_annotator_bundle(
        packet_root=case["packet_root"],
        output_root=case["export_root"],
        task_manifest_path=case["task_manifest"],
        repo_root=case["repo_root"],
    )


def test_export_contains_only_annotator_safe_artifacts(packet_case):
    receipt = _export(packet_case)

    assert receipt["status"] == "human_eval_annotator_distribution_verified"
    assert receipt["coordinator_artifacts_included"] is False
    assert {path.name for path in packet_case["export_root"].iterdir()} == {
        "packet.jsonl",
        "ratings_template.csv",
        "annotator_manifest.json",
    }
    manifest_text = (packet_case["export_root"] / "annotator_manifest.json").read_text(
        encoding="utf-8"
    )
    assert "blind_seed" not in manifest_text
    assert "blinding_key.csv" not in manifest_text
    assert "variant_id" not in manifest_text
    assert "run_id" not in manifest_text


def test_exported_bytes_come_from_same_snapshot_that_was_verified(packet_case, monkeypatch):
    live_packet = packet_case["packet_root"] / "packet.jsonl"
    original = live_packet.read_bytes()
    real_verify = exporter.verify_packet
    saw_snapshot = []

    def verify_snapshot(**kwargs):
        assert Path(kwargs["output_root"]) != packet_case["packet_root"]
        receipt = real_verify(**kwargs)
        live_packet.write_text("post-verification live drift\n", encoding="utf-8")
        saw_snapshot.append(True)
        return receipt

    monkeypatch.setattr(exporter, "verify_packet", verify_snapshot)
    _export(packet_case)

    assert saw_snapshot == [True]
    assert (packet_case["export_root"] / "packet.jsonl").read_bytes() == original
    assert live_packet.read_bytes() != original


def test_tampered_coordinator_packet_is_rejected_before_export(packet_case):
    packet = packet_case["packet_root"] / "packet.jsonl"
    packet.write_text(packet.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="packet fingerprint"):
        _export(packet_case)

    assert not packet_case["export_root"].exists()


def test_existing_export_root_is_never_reused(packet_case):
    packet_case["export_root"].mkdir()
    marker = packet_case["export_root"] / "keep.txt"
    marker.write_text("keep\n", encoding="utf-8")

    with pytest.raises(ValueError, match="refusing to overwrite"):
        _export(packet_case)

    assert marker.read_text(encoding="utf-8") == "keep\n"


def test_bundle_verifier_rejects_coordinator_artifact_added_later(packet_case):
    _export(packet_case)
    source = packet_case["packet_root"] / "blinding_key.csv"
    (packet_case["export_root"] / "blinding_key.csv").write_bytes(source.read_bytes())

    with pytest.raises(ValueError, match="artifact set mismatch"):
        exporter.verify_annotator_bundle(packet_case["export_root"])


def test_bundle_verifier_rejects_manifest_fingerprint_drift(packet_case):
    _export(packet_case)
    packet = packet_case["export_root"] / "packet.jsonl"
    packet.write_text(packet.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        exporter.verify_annotator_bundle(packet_case["export_root"])


def test_verify_only_cli_reports_no_coordinator_artifacts(packet_case):
    _export(packet_case)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.export_human_eval_annotator_bundle",
            "--output-root",
            str(packet_case["export_root"]),
            "--verify-only",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0
    assert "HUMAN EVAL ANNOTATOR EXPORT: PASS" in result.stdout
    assert '"coordinator_artifacts_included": false' in result.stdout.lower()
    assert result.stderr == ""
