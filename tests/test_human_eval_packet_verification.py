"""Synthetic checks for human-evaluation packet and blinding-key provenance.

All reports, traces, and identifiers in this module are synthetic fixtures.
No human ratings or experimental results are created.
"""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import build_human_eval_packet as build
from scripts.verify_human_eval_packet import verify_packet


VARIANTS = build.EXPECTED_VARIANTS
KEY_FIELDS = ["blind_id", "variant_id", "task_id", "run_id", "trace_path", "report_path"]


def _write_task_manifest(root: Path) -> Path:
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


def _write_source(root: Path, variant: str, task_id: str, question: str) -> None:
    run_id = f"{variant.lower()}-{task_id}"
    report = root / "outputs" / run_id / "research_report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        f"# Synthetic report\n\n{variant} fixture for {task_id}.\n",
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
    task_manifest = _write_task_manifest(tmp_path)
    tasks = json.loads(task_manifest.read_text(encoding="utf-8"))["tasks"]
    for task in tasks:
        for variant in VARIANTS:
            _write_source(tmp_path, variant, task["id"], task["question"])
    output_root = tmp_path / "outputs" / "human_eval"
    build.build_packet(
        tmp_path / "outputs" / "experiment_traces",
        output_root,
        task_manifest_path=task_manifest,
    )
    return {
        "repo_root": tmp_path,
        "output_root": output_root,
        "task_manifest_path": task_manifest,
    }


def _verify(case):
    return verify_packet(
        output_root=case["output_root"],
        task_manifest_path=case["task_manifest_path"],
        repo_root=case["repo_root"],
    )


def _refresh_artifact(case, key: str):
    manifest_path = case["output_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    filename = manifest[key]
    content = (case["output_root"] / filename).read_bytes()
    manifest["artifacts"][key] = {
        "path": filename,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_packet_verifier_checks_source_mapping_and_artifact_fingerprints(packet_case):
    receipt = _verify(packet_case)
    assert receipt == {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "human_eval_packet_verified",
        "blinding_key_checked": True,
        "human_ratings_read": False,
        "n_reports": 8,
        "n_tasks": 2,
        "n_variants": 4,
    }
    manifest = json.loads(
        (packet_case["output_root"] / "manifest.json").read_text(encoding="utf-8")
    )
    for key in ("packet", "ratings_template", "blinding_key"):
        filename = manifest[key]
        content = (packet_case["output_root"] / filename).read_bytes()
        assert manifest["artifacts"][key] == {
            "path": filename,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }


def test_tampered_key_is_rejected_even_when_manifest_fingerprint_is_refreshed(packet_case):
    key_path = packet_case["output_root"] / "blinding_key.csv"
    with key_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["variant_id"] = "P6V" if rows[0]["variant_id"] != "P6V" else "D3"
    with key_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=KEY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    _refresh_artifact(packet_case, "blinding_key")
    with pytest.raises(ValueError, match="trace variant|duplicate treatment/task"):
        _verify(packet_case)


def test_packet_report_drift_is_rejected_even_when_fingerprint_is_refreshed(packet_case):
    packet_path = packet_case["output_root"] / "packet.jsonl"
    rows = [json.loads(line) for line in packet_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["report_markdown"] += "\nTampered text."
    packet_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    _refresh_artifact(packet_case, "packet")
    with pytest.raises(ValueError, match="report content"):
        _verify(packet_case)


def test_scored_ratings_template_is_rejected_even_when_fingerprint_is_refreshed(packet_case):
    path = packet_case["output_root"] / "ratings_template.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["correctness_1_5"] = "5"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(build.RATING_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    _refresh_artifact(packet_case, "ratings_template")
    with pytest.raises(ValueError, match="must remain unscored"):
        _verify(packet_case)


def test_task_manifest_drift_is_rejected(packet_case):
    path = packet_case["task_manifest_path"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tasks"][0]["question"] = "Changed after packet generation?"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="task-manifest provenance"):
        _verify(packet_case)


def test_artifact_byte_drift_without_manifest_update_is_rejected(packet_case):
    path = packet_case["output_root"] / "blinding_key.csv"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="blinding_key fingerprint"):
        _verify(packet_case)


def test_missing_source_report_is_rejected(packet_case):
    manifest = json.loads(
        (packet_case["output_root"] / "manifest.json").read_text(encoding="utf-8")
    )
    key_path = packet_case["output_root"] / manifest["blinding_key"]
    with key_path.open(encoding="utf-8", newline="") as handle:
        first = next(csv.DictReader(handle))
    (packet_case["repo_root"] / first["report_path"]).unlink()
    with pytest.raises(ValueError, match="report .* regular file"):
        _verify(packet_case)


def test_cli_passes_without_reading_human_ratings(packet_case):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_human_eval_packet",
            "--output-root",
            str(packet_case["output_root"]),
            "--task-manifest",
            str(packet_case["task_manifest_path"]),
            "--repo-root",
            str(packet_case["repo_root"]),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0
    assert "HUMAN EVAL PACKET VERIFY: PASS (no human ratings read)" in result.stdout
    assert '"human_ratings_read": false' in result.stdout.lower()
    assert result.stderr == ""


def test_cli_failure_has_no_success_receipt_or_traceback(packet_case):
    (packet_case["output_root"] / "blinding_key.csv").unlink()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_human_eval_packet",
            "--output-root",
            str(packet_case["output_root"]),
            "--task-manifest",
            str(packet_case["task_manifest_path"]),
            "--repo-root",
            str(packet_case["repo_root"]),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode != 0
    assert "HUMAN EVAL PACKET VERIFY: FAIL" in result.stderr
    assert "Traceback" not in result.stderr
    assert "HUMAN EVAL PACKET VERIFY: PASS" not in result.stdout
