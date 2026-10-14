"""Synthetic checks for annotator-safe human-evaluation distribution bundles."""
import hashlib
import json
import os
import shutil
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


def _opened_directory(directory_fd: int) -> Path:
    return Path(os.readlink(f"/proc/self/fd/{directory_fd}"))


def test_repository_annotator_guide_is_frozen_and_treatment_blind():
    guide = getattr(exporter, "DEFAULT_ANNOTATOR_GUIDE", Path("missing-guide"))
    expected_sha256 = getattr(exporter, "FROZEN_ANNOTATOR_GUIDE_SHA256", None)

    assert guide.is_file()
    content = guide.read_bytes()
    assert hashlib.sha256(content).hexdigest() == expected_sha256
    text = content.decode("utf-8")
    for forbidden in ("D3", "D6", "P6", "P6V", "blinding_key.csv"):
        assert forbidden not in text
    for required in (
        "Correctness",
        "Completeness",
        "Source quality",
        "Synthesis / reasoning",
        "Clarity",
    ):
        assert required in text

    protocol = (exporter.REPO_ROOT / "paper" / "HUMAN_EVAL_PROTOCOL.md").read_text(
        encoding="utf-8"
    )
    for rubric_anchor in (
        "major factual errors, contradictions, or misleading conclusions",
        "misses central requirements or leaves major aspects unanswered",
        "relies mainly on weak, irrelevant, unverifiable, or clearly",
        "fragmented, contradictory, or unsupported reasoning",
        "confusing, disorganized, repetitive, or difficult to interpret",
    ):
        assert rubric_anchor in text
        assert rubric_anchor in protocol
    assert "annotator_instructions.md" in protocol


def test_export_contains_only_annotator_safe_artifacts(packet_case):
    receipt = _export(packet_case)

    assert receipt["status"] == "human_eval_annotator_distribution_verified"
    assert receipt["coordinator_artifacts_included"] is False
    assert receipt["source_bound_to_verified_coordinator"] is True
    assert len(receipt["coordinator_manifest_sha256"]) == 64
    assert len(receipt["annotator_guide_sha256"]) == 64
    assert {path.name for path in packet_case["export_root"].iterdir()} == {
        "packet.jsonl",
        "ratings_template.csv",
        "annotator_instructions.md",
        "annotator_manifest.json",
    }
    manifest = json.loads(
        (packet_case["export_root"] / "annotator_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert "blind_seed" not in manifest
    assert "blinding_key" not in manifest
    assert "variant_id" not in manifest
    assert "run_id" not in manifest
    assert manifest["artifacts"]["annotator_instructions"]["path"] == (
        "annotator_instructions.md"
    )
    assert (
        packet_case["export_root"] / "annotator_instructions.md"
    ).read_bytes() == exporter.DEFAULT_ANNOTATOR_GUIDE.read_bytes()


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


def test_export_rejects_coherently_rehashed_output_replacement(packet_case, monkeypatch):
    real_write = exporter._write_exclusive_at

    def replace_after_publication(directory_fd, name, content):
        identity = real_write(directory_fd, name, content)
        if name != "annotator_manifest.json":
            return identity
        staging_root = _opened_directory(directory_fd)
        packet_path = staging_root / "packet.jsonl"
        rows = [
            json.loads(line)
            for line in packet_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        rows[0]["report_markdown"] += "\n\nSynthetic concurrent replacement."
        packet_bytes = (
            "\n".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows
            )
            + "\n"
        ).encode("utf-8")
        packet_path.write_bytes(packet_bytes)
        manifest_path = staging_root / "annotator_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"]["packet"] = {
            "path": "packet.jsonl",
            **exporter._fingerprint(packet_bytes),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return identity

    monkeypatch.setattr(exporter, "_write_exclusive_at", replace_after_publication)

    with pytest.raises(
        ValueError,
        match="annotator manifest does not match the published candidate",
    ):
        _export(packet_case)


def test_export_rejects_output_root_replacement_before_success(
    packet_case, monkeypatch
):
    output_root = packet_case["export_root"]
    detached = output_root.with_name("detached-annotator-distribution")
    replacement = output_root.with_name("replacement-annotator-distribution")
    real_snapshot = exporter._snapshot_annotator_bundle
    swapped = []

    def replace_root_before_snapshot(live_root, snapshot_root):
        if not swapped:
            shutil.copytree(live_root, replacement)
            live_root.rename(detached)
            live_root.symlink_to(replacement, target_is_directory=True)
            swapped.append(True)
        return real_snapshot(live_root, snapshot_root)

    monkeypatch.setattr(
        exporter,
        "_snapshot_annotator_bundle",
        replace_root_before_snapshot,
    )

    with pytest.raises(ValueError, match="annotator bundle output root changed"):
        _export(packet_case)

    assert swapped == [True]
    assert detached.is_dir()
    assert not output_root.exists()


def test_export_rejects_competing_output_created_before_atomic_publish(
    packet_case, monkeypatch
):
    output_root = packet_case["export_root"]
    real_publish = exporter._publish_directory_noreplace
    competed = []

    def create_competing_output(staging_root, destination):
        destination.mkdir()
        (destination / "owner.txt").write_text("competing output\n", encoding="utf-8")
        competed.append(True)
        return real_publish(staging_root, destination)

    monkeypatch.setattr(
        exporter,
        "_publish_directory_noreplace",
        create_competing_output,
    )

    with pytest.raises(ValueError, match="refusing to overwrite annotator bundle output"):
        _export(packet_case)

    assert competed == [True]
    assert (output_root / "owner.txt").read_text(encoding="utf-8") == "competing output\n"


def test_export_preserves_reused_staging_path_after_publish(packet_case, monkeypatch):
    real_publish = exporter._publish_directory_noreplace
    reused = []

    def reuse_staging_path(staging_root, destination):
        real_publish(staging_root, destination)
        staging_root.mkdir()
        (staging_root / "owner.txt").write_text(
            "concurrent owner\n",
            encoding="utf-8",
        )
        reused.append(staging_root)

    monkeypatch.setattr(
        exporter,
        "_publish_directory_noreplace",
        reuse_staging_path,
    )

    _export(packet_case)

    assert len(reused) == 1
    assert (reused[0] / "owner.txt").read_text(encoding="utf-8") == "concurrent owner\n"


def test_export_preserves_replacement_staging_path_after_failure(
    packet_case, monkeypatch
):
    real_snapshot = exporter._snapshot_annotator_bundle
    replacements = []

    def replace_staging_before_snapshot(staging_root, snapshot_root):
        detached = staging_root.with_name(f"{staging_root.name}-detached")
        staging_root.rename(detached)
        staging_root.mkdir()
        (staging_root / "owner.txt").write_text(
            "concurrent owner\n",
            encoding="utf-8",
        )
        replacements.append(staging_root)
        return real_snapshot(staging_root, snapshot_root)

    monkeypatch.setattr(
        exporter,
        "_snapshot_annotator_bundle",
        replace_staging_before_snapshot,
    )

    with pytest.raises(ValueError, match="artifact set mismatch"):
        _export(packet_case)

    assert len(replacements) == 1
    assert (replacements[0] / "owner.txt").read_text(encoding="utf-8") == "concurrent owner\n"


def test_export_preserves_conflicting_expected_file_on_exclusive_create_failure(
    packet_case, monkeypatch
):
    real_write = exporter._write_exclusive_at
    staging_roots = []

    def create_conflict_before_first_write(directory_fd, name, content):
        if not staging_roots:
            staging_root = _opened_directory(directory_fd)
            (staging_root / name).write_text(
                "concurrent owner\n",
                encoding="utf-8",
            )
            staging_roots.append(staging_root)
        return real_write(directory_fd, name, content)

    monkeypatch.setattr(
        exporter,
        "_write_exclusive_at",
        create_conflict_before_first_write,
    )

    with pytest.raises(ValueError, match="refusing to overwrite annotator-bundle artifact"):
        _export(packet_case)

    assert len(staging_roots) == 1
    assert (staging_roots[0] / "packet.jsonl").read_text(encoding="utf-8") == (
        "concurrent owner\n"
    )


def test_export_never_writes_through_a_replaced_output_root(
    packet_case, monkeypatch
):
    output_root = packet_case["export_root"]
    detached = output_root.with_name("detached-mid-publication")
    replacement = output_root.with_name("replacement-mid-publication")
    real_write = exporter._write_exclusive_at
    swapped = []

    def replace_root_after_first_write(directory_fd, name, content):
        identity = real_write(directory_fd, name, content)
        if name == "packet.jsonl" and not swapped:
            staging_root = _opened_directory(directory_fd)
            staging_root.rename(detached)
            replacement.mkdir()
            shutil.copyfile(
                detached / "packet.jsonl",
                replacement / "packet.jsonl",
            )
            staging_root.symlink_to(replacement, target_is_directory=True)
            swapped.append(True)
        return identity

    monkeypatch.setattr(
        exporter,
        "_write_exclusive_at",
        replace_root_after_first_write,
    )

    with pytest.raises(ValueError, match="annotator bundle output root changed"):
        _export(packet_case)

    assert swapped == [True]
    assert {path.name for path in replacement.iterdir()} == {"packet.jsonl"}
    assert not output_root.exists()


def test_export_rejects_semantically_equivalent_manifest_byte_replacement(
    packet_case, monkeypatch
):
    real_snapshot = exporter._snapshot_annotator_bundle
    replaced = []

    def replace_manifest_before_snapshot(output_root, snapshot_root):
        manifest = output_root / "annotator_manifest.json"
        if not replaced:
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            replaced.append(True)
        return real_snapshot(output_root, snapshot_root)

    monkeypatch.setattr(
        exporter,
        "_snapshot_annotator_bundle",
        replace_manifest_before_snapshot,
    )

    with pytest.raises(
        ValueError,
        match="annotator manifest does not match the published candidate",
    ):
        _export(packet_case)

    assert replaced == [True]


def test_export_rejects_output_root_replacement_during_final_verification(
    packet_case, monkeypatch
):
    output_root = packet_case["export_root"]
    real_verify = exporter.verify_annotator_bundle
    swapped = []

    def replace_root_after_verification(snapshot_root):
        receipt = real_verify(snapshot_root)
        output_root.mkdir()
        (output_root / "blinding_key.csv").write_text(
            "blind_id,variant_id\nblind-001,A\n",
            encoding="utf-8",
        )
        swapped.append(True)
        return receipt

    monkeypatch.setattr(
        exporter,
        "verify_annotator_bundle",
        replace_root_after_verification,
    )

    with pytest.raises(ValueError, match="refusing to overwrite annotator bundle output"):
        _export(packet_case)

    assert swapped == [True]
    assert {path.name for path in output_root.iterdir()} == {"blinding_key.csv"}


def test_export_rejects_coordinator_artifact_inserted_before_capture(
    packet_case, monkeypatch
):
    real_write = exporter._write_exclusive_at

    def add_blinding_key_after_publication(directory_fd, name, content):
        identity = real_write(directory_fd, name, content)
        if name == "annotator_manifest.json":
            source = packet_case["packet_root"] / "blinding_key.csv"
            destination = _opened_directory(directory_fd) / "blinding_key.csv"
            destination.write_bytes(source.read_bytes())
        return identity

    monkeypatch.setattr(
        exporter, "_write_exclusive_at", add_blinding_key_after_publication
    )

    with pytest.raises(ValueError, match="artifact set mismatch.*blinding_key.csv"):
        _export(packet_case)


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


def test_bundle_verifier_rejects_coherently_rehashed_guide_tamper(packet_case):
    _export(packet_case)
    guide = packet_case["export_root"] / "annotator_instructions.md"
    guide_bytes = guide.read_bytes() + b"\nSynthetic changed instruction.\n"
    guide.write_bytes(guide_bytes)

    manifest_path = packet_case["export_root"] / "annotator_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["annotator_instructions"] = {
        "path": "annotator_instructions.md",
        **exporter._fingerprint(guide_bytes),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="do not match the frozen guide"):
        exporter.verify_annotator_bundle(packet_case["export_root"])


def test_export_rejects_changed_guide_before_staging(packet_case, tmp_path):
    changed_guide = tmp_path / "changed-guide.md"
    changed_guide.write_bytes(exporter.DEFAULT_ANNOTATOR_GUIDE.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="guide fingerprint mismatch"):
        exporter.export_annotator_bundle(
            packet_root=packet_case["packet_root"],
            output_root=packet_case["export_root"],
            task_manifest_path=packet_case["task_manifest"],
            repo_root=packet_case["repo_root"],
            annotator_guide_path=changed_guide,
        )

    assert not packet_case["export_root"].exists()


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


def test_source_bound_verifier_accepts_untampered_export(packet_case):
    _export(packet_case)

    receipt = exporter.verify_annotator_bundle_against_source(
        packet_root=packet_case["packet_root"],
        output_root=packet_case["export_root"],
        task_manifest_path=packet_case["task_manifest"],
        repo_root=packet_case["repo_root"],
    )

    assert receipt["status"] == "human_eval_annotator_distribution_verified"
    assert receipt["source_bound_to_verified_coordinator"] is True
    assert len(receipt["coordinator_manifest_sha256"]) == 64


def test_source_bound_verifier_rejects_self_consistently_rehashed_tamper(packet_case):
    _export(packet_case)
    packet_path = packet_case["export_root"] / "packet.jsonl"
    rows = [
        json.loads(line)
        for line in packet_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows[0]["report_markdown"] += "\n\nSynthetic post-export tamper."
    packet_bytes = (
        "\n".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True)
            for row in rows
        )
        + "\n"
    ).encode("utf-8")
    packet_path.write_bytes(packet_bytes)

    manifest_path = packet_case["export_root"] / "annotator_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["packet"] = {
        "path": "packet.jsonl",
        **exporter._fingerprint(packet_bytes),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Local consistency alone is intentionally insufficient against a bundle
    # whose content and local checksum were both changed together.
    exporter.verify_annotator_bundle(packet_case["export_root"])

    with pytest.raises(ValueError, match="does not match the verified coordinator source"):
        exporter.verify_annotator_bundle_against_source(
            packet_root=packet_case["packet_root"],
            output_root=packet_case["export_root"],
            task_manifest_path=packet_case["task_manifest"],
            repo_root=packet_case["repo_root"],
        )


def test_source_bound_verifier_rejects_different_valid_coordinator_packet(packet_case):
    _export(packet_case)
    alternate_root = packet_case["repo_root"] / "outputs" / "human_eval_alternate"
    build.build_packet(
        packet_case["repo_root"] / "outputs" / "experiment_traces",
        alternate_root,
        seed=20260926,
        task_manifest_path=packet_case["task_manifest"],
    )

    assert (
        alternate_root / "packet.jsonl"
    ).read_bytes() != (
        packet_case["packet_root"] / "packet.jsonl"
    ).read_bytes()

    with pytest.raises(ValueError, match="does not match the verified coordinator source"):
        exporter.verify_annotator_bundle_against_source(
            packet_root=alternate_root,
            output_root=packet_case["export_root"],
            task_manifest_path=packet_case["task_manifest"],
            repo_root=packet_case["repo_root"],
        )


def test_source_bound_verifier_uses_captured_coordinator_snapshot(packet_case, monkeypatch):
    _export(packet_case)
    live_packet = packet_case["packet_root"] / "packet.jsonl"
    original = live_packet.read_bytes()
    real_verify = exporter.verify_packet

    def verify_snapshot(**kwargs):
        receipt = real_verify(**kwargs)
        live_packet.write_text("post-capture coordinator drift\n", encoding="utf-8")
        return receipt

    monkeypatch.setattr(exporter, "verify_packet", verify_snapshot)
    receipt = exporter.verify_annotator_bundle_against_source(
        packet_root=packet_case["packet_root"],
        output_root=packet_case["export_root"],
        task_manifest_path=packet_case["task_manifest"],
        repo_root=packet_case["repo_root"],
    )

    assert receipt["source_bound_to_verified_coordinator"] is True
    assert live_packet.read_bytes() != original


def test_verify_against_source_cli(packet_case):
    _export(packet_case)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.export_human_eval_annotator_bundle",
            "--packet-root",
            str(packet_case["packet_root"]),
            "--output-root",
            str(packet_case["export_root"]),
            "--task-manifest",
            str(packet_case["task_manifest"]),
            "--repo-root",
            str(packet_case["repo_root"]),
            "--verify-against-source",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0
    assert "HUMAN EVAL ANNOTATOR EXPORT: PASS" in result.stdout
    assert '"source_bound_to_verified_coordinator": true' in result.stdout.lower()
    assert result.stderr == ""
