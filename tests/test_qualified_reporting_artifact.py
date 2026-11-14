"""Consumer-side verification of the *retained pair*, not only its producer."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts.assemble_qualified_main_study_report import ROOT, assemble_qualified_report
from scripts.verify_qualified_reporting_copy import verify_qualified_copy
from scripts.verify_qualified_reporting_artifact import (
    main, verify_distributed_artifact,
)


@pytest.fixture
def artifact(tmp_path: Path) -> tuple[Path, Path]:
    report = tmp_path / "qualified_main_study.md"
    receipt = tmp_path / "verification_receipt.json"
    report.write_text(assemble_qualified_report(), encoding="utf-8")
    validated = verify_qualified_copy(report_path=report)
    receipt.write_text(
        json.dumps(validated, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    return report, receipt


def test_genuine_producer_pair_is_reverified_without_rewriting_files(artifact):
    report, receipt = artifact
    before = (report.read_bytes(), receipt.read_bytes())
    result = verify_distributed_artifact(report_path=report, receipt_path=receipt)
    assert result["status"] == "downloaded_pair_matches_checkout_local_source_bound_receipt"
    assert result["qualified_copy_sha256"] == hashlib.sha256(before[0]).hexdigest()
    assert result["verification_receipt_sha256"] == hashlib.sha256(before[1]).hexdigest()
    assert result["original_reports_and_traces_independently_authenticated"] is False
    assert result["human_validation_performed"] is False
    assert (report.read_bytes(), receipt.read_bytes()) == before


@pytest.mark.parametrize("mutate", [
    lambda b: b.replace(b"false", b"true", 1),
    lambda b: b.replace(b"false", b"0", 1),
    lambda b: b.replace(b'"schema_version": 1', b'"schema_version": true', 1),
    lambda b: b.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1', 1),
    lambda b: b.replace(b'"schema_version": 1', b'"schema_version": 1, "human_verified": true', 1),
    lambda b: b[:-1],
    lambda b: b + b'{"human_validation_performed": true}\n',
], ids=[
    "false-claim", "boolean-numeric-spoof", "schema-type-spoof",
    "duplicate-key", "undisclosed-extra-key", "lost-final-newline",
    "appended-json-document",
])
def test_modified_receipt_cannot_be_accepted_with_intact_report(artifact, mutate):
    report, receipt = artifact
    original = receipt.read_bytes()
    changed = mutate(original)
    assert changed != original
    receipt.write_bytes(changed)
    with pytest.raises(ValueError, match="receipt differs"):
        verify_distributed_artifact(report_path=report, receipt_path=receipt)


def test_changed_report_fails_despite_untouched_companion_receipt(artifact):
    report, receipt = artifact
    report.write_bytes(report.read_bytes() + b"\nNew unsupported claim.\n")
    with pytest.raises(ValueError, match="does not match source-verified assembly"):
        verify_distributed_artifact(report_path=report, receipt_path=receipt)


def test_symlinked_receipt_is_rejected(artifact, tmp_path):
    report, receipt = artifact
    alias = tmp_path / "receipt-link.json"
    alias.symlink_to(receipt)
    with pytest.raises(ValueError, match="unsafe"):
        verify_distributed_artifact(report_path=report, receipt_path=alias)


def test_cli_verifies_existing_artifact_without_creating_a_new_receipt(
    artifact, monkeypatch, capsys,
):
    report, receipt = artifact
    before = (report.read_bytes(), receipt.read_bytes())
    monkeypatch.setattr("sys.argv", [
        "verify_qualified_reporting_artifact",
        "--report", str(report), "--receipt", str(receipt),
    ])
    assert main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["human_validation_performed"] is False
    assert (report.read_bytes(), receipt.read_bytes()) == before


def test_ci_reverifies_existing_pair_before_upload_and_triggers_on_guard_changes():
    path = ROOT / ".github/workflows/qualified-main-study-report.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    for event in ("push", "pull_request"):
        paths = set(workflow["on"][event]["paths"])
        assert {
            "scripts/verify_qualified_reporting_artifact.py",
            "tests/test_qualified_reporting_artifact.py",
        } <= paths
    steps = workflow["jobs"]["verify-qualified-report"]["steps"]
    run = steps[2]["run"]
    assert "python -m scripts.verify_qualified_reporting_copy" in run
    assert "python -m scripts.verify_qualified_reporting_artifact" in run
    assert run.index("python -m scripts.verify_qualified_reporting_copy") < (
        run.index("python -m scripts.verify_qualified_reporting_artifact")
    )
    assert steps[3]["uses"].startswith("actions/upload-artifact@")
