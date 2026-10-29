"""Synthetic checks for human-evaluation packet and blinding-key provenance.

All reports, traces, and identifiers in this module are synthetic fixtures.
No human ratings or experimental results are created.
"""
import csv
import hashlib
import json
import os
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
        f"# Synthetic report\n\nNeutral fixture for {task_id}.\n",
        encoding="utf-8",
    )
    trace = root / "outputs" / "experiment_traces" / variant / f"{run_id}.json"
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text(
        json.dumps(
            {
                "schema_version": 2,
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


def test_packet_verifier_rejects_artifact_path_replacement_during_capture(
    packet_case, monkeypatch
):
    packet_path = packet_case["output_root"] / "packet.jsonl"
    packet_inode = packet_path.stat().st_ino
    original_os_read = os.read
    replaced = False

    def replace_during_read(fd, size):
        nonlocal replaced
        content = original_os_read(fd, size)
        if not replaced and os.fstat(fd).st_ino == packet_inode:
            packet_path.unlink()
            packet_path.write_bytes(content + b"\n")
            replaced = True
        return content

    monkeypatch.setattr(os, "read", replace_during_read)

    with pytest.raises(ValueError, match="replaced during capture"):
        _verify(packet_case)
    assert replaced is True


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


def _insert_duplicate_json_member(path: Path, needle: str, duplicate: str) -> None:
    """Insert a conflicting member before the one the default decoder would retain."""
    text = path.read_text(encoding="utf-8")
    assert needle in text
    path.write_text(text.replace(needle, f"{duplicate}, {needle}", 1), encoding="utf-8")



def _refresh_source_fingerprint(case, row: dict, kind: str) -> None:
    """Synthetic test only: make a source edit coherent with its packet manifest."""
    manifest_path = case["output_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(
        item for item in manifest["source_artifacts"]
        if item["blind_id"] == row["blind_id"]
    )
    raw = (case["repo_root"] / row[f"{kind}_path"]).read_bytes()
    entry[kind] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("bad_run_id", [None, "", 123, "d3-main-01 ", " d3-main-01"])
def test_packet_verifier_requires_explicit_filename_bound_trace_run_id(
    packet_case, bad_run_id
):
    """Independent verification must not infer or normalize a missing run ID."""
    with (packet_case["output_root"] / "blinding_key.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        row = next(
            item for item in csv.DictReader(handle)
            if item["variant_id"] == "D3" and item["task_id"] == "main-01"
        )
    trace_path = packet_case["repo_root"] / row["trace_path"]
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    if bad_run_id is None:
        payload["trace"].pop("run_id")
    else:
        payload["trace"]["run_id"] = bad_run_id
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    _refresh_source_fingerprint(packet_case, row, "trace")

    with pytest.raises(ValueError, match="explicit run_id.*filename"):
        _verify(packet_case)


def test_packet_verifier_rejects_reused_run_id_with_coherent_packet_hashes(packet_case):
    """Two different treatments cannot claim the same execution after rehashing."""
    key_path = packet_case["output_root"] / "blinding_key.csv"
    with key_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    first = next(row for row in rows if row["variant_id"] == "D3"
                 and row["task_id"] == "main-01")
    second = next(row for row in rows if row["variant_id"] == "D6"
                  and row["task_id"] == "main-01")
    root = packet_case["repo_root"]
    original_trace = root / second["trace_path"]
    payload = json.loads(original_trace.read_text(encoding="utf-8"))
    payload["trace"]["run_id"] = first["run_id"]
    payload["trace"]["report_path"] = f"./outputs/{first['run_id']}/research_report.pdf"
    substitute_trace = (
        root / "outputs" / "experiment_traces" / "D6" / f"{first['run_id']}.json"
    )
    substitute_trace.write_text(json.dumps(payload), encoding="utf-8")
    original_trace.unlink()

    # Both synthetic reports have identical content for the same task; this
    # test uses the same report path, not a change in observed score/content.
    assert (root / first["report_path"]).read_bytes() == (
        root / second["report_path"]
    ).read_bytes()
    second["run_id"] = first["run_id"]
    second["trace_path"] = substitute_trace.relative_to(root).as_posix()
    second["report_path"] = first["report_path"]
    with key_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=KEY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    _refresh_artifact(packet_case, "blinding_key")
    _refresh_source_fingerprint(packet_case, second, "trace")
    _refresh_source_fingerprint(packet_case, second, "report")

    with pytest.raises(ValueError, match="duplicate experiment run_id"):
        _verify(packet_case)


def test_packet_verifier_rejects_coherently_rehashed_treatment_leakage(packet_case):
    packet_path = packet_case["output_root"] / "packet.jsonl"
    rows = [
        json.loads(line)
        for line in packet_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows[0]["report_markdown"] += "\n\nInternal variant_id=P6V."
    packet_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
        + "\n",
        encoding="utf-8",
    )
    _refresh_artifact(packet_case, "packet")

    with pytest.raises(ValueError, match="annotator-facing treatment leakage"):
        _verify(packet_case)


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


def test_packet_manifest_binds_content_validator_source_and_runtime(packet_case):
    manifest = json.loads(
        (packet_case["output_root"] / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["schema_version"] == 2
    assert manifest["content_validator"] == build.content_validator_source_contract()
    assert manifest["content_validator_runtime"] == (
        build.content_validator_runtime_contract()
    )


def test_packet_verifier_rejects_content_validator_source_drift(
    packet_case, monkeypatch
):
    source_contract = {
        "path": "scripts/build_human_eval_packet.py",
        "bytes": 1,
        "sha256": "0" * 64,
    }
    monkeypatch.setattr(
        build,
        "content_validator_source_contract",
        lambda: source_contract,
        raising=False,
    )

    with pytest.raises(ValueError, match="content validator source contract mismatch"):
        _verify(packet_case)


def test_packet_verifier_rejects_content_validator_runtime_drift(
    packet_case, monkeypatch
):
    runtime_contract = {
        **build.content_validator_runtime_contract(),
        "unicode_database_version": "synthetic-drift",
    }
    monkeypatch.setattr(
        build,
        "content_validator_runtime_contract",
        lambda: runtime_contract,
    )

    with pytest.raises(ValueError, match="content validator runtime contract mismatch"):
        _verify(packet_case)


def test_packet_verifier_rejects_disk_source_drift_from_loaded_validator(
    packet_case, monkeypatch
):
    loaded = build.content_validator_source_contract()
    monkeypatch.setattr(
        build,
        "_content_validator_source_contract_now",
        lambda: {**loaded, "sha256": "0" * 64},
        raising=False,
    )

    with pytest.raises(ValueError, match="loaded validator source differs"):
        _verify(packet_case)


def test_packet_verifier_rejects_unknown_manifest_field(packet_case):
    manifest_path = packet_case["output_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["unverified_metadata"] = {"claim": "not part of the frozen schema"}
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="packet manifest schema"):
        _verify(packet_case)


def test_packet_verifier_rejects_unknown_artifact_entry(packet_case):
    manifest_path = packet_case["output_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["unverified"] = {
        "path": "unverified.json",
        "bytes": 0,
        "sha256": hashlib.sha256(b"").hexdigest(),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="artifact table schema"):
        _verify(packet_case)


def test_packet_verifier_rejects_changed_blinding_notice(packet_case):
    manifest_path = packet_case["output_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["blinding_note"] = "The coordinator key may be shared before scoring."
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="blinding notice"):
        _verify(packet_case)


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
    with pytest.raises(ValueError, match="trace variant|duplicate treatment/task|trace source mapping"):
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


def test_packet_verifier_rejects_trace_cross_run_report_reference(packet_case):
    """Changing a persisted trace's report pointer must fail independently of hashes."""
    with (packet_case["output_root"] / "blinding_key.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        key_rows = list(csv.DictReader(handle))
    row = key_rows[0]
    other = next(item for item in key_rows if item["run_id"] != row["run_id"])
    trace_path = packet_case["repo_root"] / row["trace_path"]
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["report_path"] = "./" + other["report_path"].replace(".md", ".pdf")
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Report source is not bound to trace run_id"):
        _verify(packet_case)


def test_packet_verifier_rejects_rehashed_cross_run_report_swap(packet_case):
    """Recomputing manifest hashes cannot legitimise another run's report."""
    key_path = packet_case["output_root"] / "blinding_key.csv"
    with key_path.open(encoding="utf-8", newline="") as handle:
        key_rows = list(csv.DictReader(handle))
    row = key_rows[0]
    other = next(item for item in key_rows if item["run_id"] != row["run_id"])
    row["report_path"] = other["report_path"]
    with key_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=KEY_FIELDS)
        writer.writeheader()
        writer.writerows(key_rows)
    _refresh_artifact(packet_case, "blinding_key")

    packet_path = packet_case["output_root"] / "packet.jsonl"
    packet_rows = [json.loads(line) for line in packet_path.read_text(encoding="utf-8").splitlines()]
    target = next(item for item in packet_rows if item["blind_id"] == row["blind_id"])
    target["report_markdown"] = (
        packet_case["repo_root"] / other["report_path"]
    ).read_text(encoding="utf-8").strip()
    packet_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in packet_rows)
        + "\n",
        encoding="utf-8",
    )
    _refresh_artifact(packet_case, "packet")

    with pytest.raises(ValueError, match="report source mapping"):
        _verify(packet_case)


@pytest.mark.parametrize(
    ("field", "conflicting_value"),
    [("variant_id", "P6V"), ("task_id", "main-02")],
)
def test_packet_verifier_rejects_conflicting_persisted_trace_identity(
    packet_case, field: str, conflicting_value: str
):
    """Even an unchanged packet/hash must not validate contradictory source identities."""
    trace_path = (
        packet_case["repo_root"]
        / "outputs"
        / "experiment_traces"
        / "D3"
        / "d3-main-01.json"
    )
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["experiment"][field] = conflicting_value
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=f"Conflicting {field}"):
        _verify(packet_case)


def test_packet_verifier_rejects_coherently_rehashed_conflicting_task_set_identity(
    packet_case,
):
    trace_path = (
        packet_case["repo_root"]
        / "outputs"
        / "experiment_traces"
        / "D3"
        / "d3-main-01.json"
    )
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["task_set_id"] = "other-task-set"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    manifest_path = packet_case["output_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with (packet_case["output_root"] / "blinding_key.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        source_path_by_blind = {
            row["blind_id"]: row["trace_path"] for row in csv.DictReader(handle)
        }
    source_entry = next(
        entry
        for entry in manifest["source_artifacts"]
        if source_path_by_blind[entry["blind_id"]]
        == trace_path.relative_to(packet_case["repo_root"]).as_posix()
    )
    content = trace_path.read_bytes()
    source_entry["trace"] = {
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Conflicting task_set_id"):
        _verify(packet_case)


def test_packet_verifier_rejects_coherently_rehashed_noncanonical_trace_schema(
    packet_case,
):
    trace_path = (
        packet_case["repo_root"]
        / "outputs"
        / "experiment_traces"
        / "D3"
        / "d3-main-01.json"
    )
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["schema_version"] = True
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    manifest_path = packet_case["output_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with (packet_case["output_root"] / "blinding_key.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        source_path_by_blind = {
            row["blind_id"]: row["trace_path"] for row in csv.DictReader(handle)
        }
    source_entry = next(
        entry
        for entry in manifest["source_artifacts"]
        if source_path_by_blind[entry["blind_id"]]
        == trace_path.relative_to(packet_case["repo_root"]).as_posix()
    )
    content = trace_path.read_bytes()
    source_entry["trace"] = {
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema_version must equal integer 2"):
        _verify(packet_case)


def test_packet_verifier_accepts_experiment_only_identity_for_legacy_traces(packet_case):
    trace_path = (
        packet_case["repo_root"]
        / "outputs"
        / "experiment_traces"
        / "D3"
        / "d3-main-01.json"
    )
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"].pop("variant_id")
    payload["trace"].pop("task_id")
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    manifest_path = packet_case["output_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with (packet_case["output_root"] / "blinding_key.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        key_rows = list(csv.DictReader(handle))
    blind_id = next(
        row["blind_id"]
        for row in key_rows
        if packet_case["repo_root"] / row["trace_path"] == trace_path
    )
    source_entry = next(
        entry for entry in manifest["source_artifacts"] if entry["blind_id"] == blind_id
    )
    content = trace_path.read_bytes()
    source_entry["trace"] = {
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    assert _verify(packet_case)["status"] == "human_eval_packet_verified"


@pytest.mark.parametrize("invalid_completed", ["false", "true", 1, {"done": True}])
def test_packet_verifier_rejects_truthy_non_boolean_completion(packet_case, invalid_completed):
    """A published packet cannot verify against malformed source completion state."""
    trace_path = (
        packet_case["repo_root"]
        / "outputs"
        / "experiment_traces"
        / "D3"
        / "d3-main-01.json"
    )
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["completed"] = invalid_completed
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="trace completed.*JSON boolean true"):
        _verify(packet_case)

def test_packet_verifier_rejects_symlinked_trace_after_packet_freeze(packet_case):
    """Even identical trace bytes must not make a linked source valid."""
    trace_path = (
        packet_case["repo_root"]
        / "outputs"
        / "experiment_traces"
        / "D3"
        / "d3-main-01.json"
    )
    backing = trace_path.with_suffix(".backing")
    trace_path.rename(backing)
    trace_path.symlink_to(backing.name)

    with pytest.raises(ValueError, match="symbolic link"):
        _verify(packet_case)


def test_packet_verifier_rejects_symlinked_variant_directory(packet_case):
    """Path.resolve must not conceal a linked treatment directory."""
    trace_dir = packet_case["repo_root"] / "outputs" / "experiment_traces" / "D3"
    backing = packet_case["repo_root"] / "archived-D3-traces"
    trace_dir.rename(backing)
    trace_dir.symlink_to(backing, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic link"):
        _verify(packet_case)


def _write_seed_test_key(case, rows):
    path = case["output_root"] / "blinding_key.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=KEY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    _refresh_artifact(case, "blinding_key")


def _write_seed_test_template(case, rows):
    path = case["output_root"] / "ratings_template.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(build.RATING_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    _refresh_artifact(case, "ratings_template")


def _write_seed_test_packet(case, rows):
    path = case["output_root"] / "packet.jsonl"
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
        + "\n",
        encoding="utf-8",
    )
    _refresh_artifact(case, "packet")


def test_packet_verifier_checks_manifest_seed_against_blinding_mapping(packet_case):
    """A rehashed unchanged packet cannot attest to a different shuffle seed."""
    manifest_path = packet_case["output_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["blind_seed"] = int(manifest["blind_seed"]) + 1
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="seed-derived blinding"):
        _verify(packet_case)


@pytest.mark.parametrize("invalid_seed", [True, False])
def test_packet_verifier_rejects_boolean_seed_as_non_integer(packet_case, invalid_seed):
    manifest_path = packet_case["output_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["blind_seed"] = invalid_seed
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="blind_seed must be an integer"):
        _verify(packet_case)


def test_packet_verifier_checks_key_row_order_even_after_rehash(packet_case):
    """Blind-ID mapping order is part of the deterministic packet contract."""
    path = packet_case["output_root"] / "blinding_key.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0], rows[1] = rows[1], rows[0]
    _write_seed_test_key(packet_case, rows)
    with pytest.raises(ValueError, match="key blind-ID sequence"):
        _verify(packet_case)


def test_packet_verifier_checks_packet_row_order_even_after_rehash(packet_case):
    packet_path = packet_case["output_root"] / "packet.jsonl"
    rows = [json.loads(line) for line in packet_path.read_text(encoding="utf-8").splitlines()]
    rows[0], rows[1] = rows[1], rows[0]
    _write_seed_test_packet(packet_case, rows)
    with pytest.raises(ValueError, match="packet blind-ID order"):
        _verify(packet_case)


def test_packet_verifier_checks_template_row_order_even_after_rehash(packet_case):
    template = packet_case["output_root"] / "ratings_template.csv"
    with template.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0], rows[1] = rows[1], rows[0]
    _write_seed_test_template(packet_case, rows)
    with pytest.raises(ValueError, match="ratings-template blind-ID order"):
        _verify(packet_case)


def test_packet_verifier_rejects_consistent_blind_id_swap_even_after_rehash(packet_case):
    """All three artifacts can be self-consistent while contradicting the seed."""
    swap = {"H001": "H002", "H002": "H001"}
    key_path = packet_case["output_root"] / "blinding_key.csv"
    with key_path.open(encoding="utf-8", newline="") as handle:
        keys = list(csv.DictReader(handle))
    for row in keys:
        row["blind_id"] = swap.get(row["blind_id"], row["blind_id"])
    _write_seed_test_key(packet_case, keys)

    packet_path = packet_case["output_root"] / "packet.jsonl"
    packet = [json.loads(line) for line in packet_path.read_text(encoding="utf-8").splitlines()]
    for row in packet:
        row["blind_id"] = swap.get(row["blind_id"], row["blind_id"])
    _write_seed_test_packet(packet_case, packet)

    template_path = packet_case["output_root"] / "ratings_template.csv"
    with template_path.open(encoding="utf-8", newline="") as handle:
        template = list(csv.DictReader(handle))
    for row in template:
        row["blind_id"] = swap.get(row["blind_id"], row["blind_id"])
    _write_seed_test_template(packet_case, template)

    with pytest.raises(ValueError, match="key blind-ID sequence"):
        _verify(packet_case)


@pytest.mark.parametrize(
    ("duplicate_name", "duplicate_value"),
    [
        ('"frozen_before_execution"', "false"),
        ('"\\u0066rozen_before_execution"', "false"),
    ],
)
def test_packet_builder_rejects_duplicate_task_manifest_keys(
    packet_case, duplicate_name: str, duplicate_value: str
):
    path = packet_case["task_manifest_path"]
    _insert_duplicate_json_member(
        path,
        '"frozen_before_execution": true',
        f"{duplicate_name}: {duplicate_value}",
    )

    with pytest.raises(ValueError, match="duplicate JSON key 'frozen_before_execution'"):
        build._load_task_manifest(path)


@pytest.mark.parametrize(
    ("duplicate_name", "duplicate_value"),
    [
        ('"completed"', "false"),
        ('"\\u0063ompleted"', "false"),
    ],
)
def test_packet_builder_rejects_duplicate_trace_keys(
    packet_case, duplicate_name: str, duplicate_value: str
):
    trace_path = (
        packet_case["repo_root"]
        / "outputs"
        / "experiment_traces"
        / "D3"
        / "d3-main-01.json"
    )
    _insert_duplicate_json_member(
        trace_path,
        '"completed": true',
        f"{duplicate_name}: {duplicate_value}",
    )

    with pytest.raises(ValueError, match="duplicate JSON key 'completed'"):
        build.build_packet(
            packet_case["repo_root"] / "outputs" / "experiment_traces",
            packet_case["repo_root"] / "outputs" / "human_eval_duplicate_trace",
            task_manifest_path=packet_case["task_manifest_path"],
        )


@pytest.mark.parametrize(
    "duplicate_name",
    ['"study_id"', '"\\u0073tudy_id"'],
)
def test_packet_verifier_rejects_duplicate_manifest_keys(packet_case, duplicate_name: str):
    path = packet_case["output_root"] / "manifest.json"
    _insert_duplicate_json_member(
        path,
        '"study_id": "budget-main-v1"',
        f'{duplicate_name}: "wrong-study"',
    )

    with pytest.raises(ValueError, match="duplicate JSON key 'study_id'"):
        _verify(packet_case)


@pytest.mark.parametrize(
    "duplicate_name",
    ['"blind_id"', '"\\u0062lind_id"'],
)
def test_packet_verifier_rejects_duplicate_packet_record_keys(packet_case, duplicate_name: str):
    path = packet_case["output_root"] / "packet.jsonl"
    _insert_duplicate_json_member(
        path,
        '"blind_id": "H001"',
        f'{duplicate_name}: "forged-blind-id"',
    )
    _refresh_artifact(packet_case, "packet")

    with pytest.raises(ValueError, match="duplicate JSON key 'blind_id'"):
        _verify(packet_case)


@pytest.mark.parametrize(
    "duplicate_name",
    ['"completed"', '"\\u0063ompleted"'],
)
def test_packet_verifier_rejects_duplicate_source_trace_keys(packet_case, duplicate_name: str):
    trace_path = (
        packet_case["repo_root"]
        / "outputs"
        / "experiment_traces"
        / "D3"
        / "d3-main-01.json"
    )
    _insert_duplicate_json_member(
        trace_path,
        '"completed": true',
        f"{duplicate_name}: false",
    )

    with pytest.raises(ValueError, match="duplicate JSON key 'completed'"):
        _verify(packet_case)


def test_packet_manifest_binds_exact_source_trace_and_report_bytes(packet_case):
    manifest = json.loads(
        (packet_case["output_root"] / "manifest.json").read_text(encoding="utf-8")
    )
    with (packet_case["output_root"] / "blinding_key.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        key_rows = list(csv.DictReader(handle))

    assert [entry["blind_id"] for entry in manifest["source_artifacts"]] == [
        row["blind_id"] for row in key_rows
    ]
    for entry, row in zip(manifest["source_artifacts"], key_rows, strict=True):
        for kind, path_field in (("trace", "trace_path"), ("report", "report_path")):
            content = (packet_case["repo_root"] / row[path_field]).read_bytes()
            assert entry[kind] == {
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }


def test_packet_verifier_rejects_semantically_unchanged_trace_byte_drift(packet_case):
    trace_path = (
        packet_case["repo_root"]
        / "outputs"
        / "experiment_traces"
        / "D3"
        / "d3-main-01.json"
    )
    trace_path.write_bytes(trace_path.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="source trace fingerprint"):
        _verify(packet_case)


def test_packet_verifier_rejects_semantically_unchanged_report_byte_drift(packet_case):
    report_path = (
        packet_case["repo_root"] / "outputs" / "d3-main-01" / "research_report.md"
    )
    report_path.write_bytes(report_path.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="source report fingerprint"):
        _verify(packet_case)


def test_packet_verifier_requires_source_fingerprint_manifest(packet_case):
    manifest_path = packet_case["output_root"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("source_artifacts", None)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="source_artifacts"):
        _verify(packet_case)

@pytest.mark.parametrize(
    ("name", "exposed_mode"),
    [
        ("manifest.json", 0o644),
        ("manifest.json", 0o660),
        ("blinding_key.csv", 0o640),
        ("blinding_key.csv", 0o606),
    ],
)
def test_packet_verifier_rejects_exposed_coordinator_files_without_byte_drift(
    packet_case, name, exposed_mode
):
    """A matching SHA-256 cannot certify a publicly accessible blinding secret."""
    path = packet_case["output_root"] / name
    original_bytes = path.read_bytes()
    path.chmod(exposed_mode)

    with pytest.raises(ValueError, match="coordinator-only artifact permissions are unsafe"):
        _verify(packet_case)
    assert path.read_bytes() == original_bytes


def test_packet_verifier_accepts_restrictive_coordinator_file_modes(packet_case):
    for name in ("manifest.json", "blinding_key.csv"):
        (packet_case["output_root"] / name).chmod(0o400)
    assert _verify(packet_case)["status"] == "human_eval_packet_verified"
