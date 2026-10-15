"""Checks for provenance binding of the verified analysis execution layer."""
import hashlib
import sys
from pathlib import Path

import pytest

from scripts import verify_main_study_execution as execution


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt(root: Path) -> dict:
    runner = root / execution.RUNNER_PATH
    verifier = root / execution.EXECUTION_VERIFIER_PATH
    runner.parent.mkdir(parents=True, exist_ok=True)
    runner.write_text("# synthetic snapshot runner\n", encoding="utf-8")
    verifier.write_text("# synthetic execution verifier\n", encoding="utf-8")
    return {
        "schema_version": 1,
        "verified_execution": {
            "runner": {"path": execution.RUNNER_PATH, "sha256": _sha(runner)},
            "execution_verifier": {
                "path": execution.EXECUTION_VERIFIER_PATH,
                "sha256": _sha(verifier),
            },
        },
    }


def test_execution_receipt_binds_runner_and_independent_verifier(tmp_path, monkeypatch):
    receipt = _receipt(tmp_path)
    legacy_calls = []
    monkeypatch.setattr(
        execution,
        "verify_receipt",
        lambda payload, root: legacy_calls.append((payload, root)),
    )

    execution.verify_execution_receipt(receipt, root=tmp_path)

    assert legacy_calls == [(receipt, tmp_path)]


def test_execution_receipt_rejects_runner_drift(tmp_path, monkeypatch):
    receipt = _receipt(tmp_path)
    monkeypatch.setattr(execution, "verify_receipt", lambda payload, root: None)
    (tmp_path / execution.RUNNER_PATH).write_text(
        "# changed snapshot runner\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="runner SHA-256 mismatch"):
        execution.verify_execution_receipt(receipt, root=tmp_path)


def test_execution_receipt_requires_complete_exact_binding(tmp_path, monkeypatch):
    receipt = _receipt(tmp_path)
    monkeypatch.setattr(execution, "verify_receipt", lambda payload, root: None)
    del receipt["verified_execution"]["execution_verifier"]

    with pytest.raises(ValueError, match="complete execution provenance"):
        execution.verify_execution_receipt(receipt, root=tmp_path)


def test_execution_cli_rejects_duplicate_receipt_fields(tmp_path, monkeypatch):
    receipt = tmp_path / "duplicate.json"
    receipt.write_text(
        '{"schema_version": 1, "schema_version": 2}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["verify_main_study_execution", str(receipt)])

    with pytest.raises(SystemExit, match="duplicate JSON field: schema_version"):
        execution.main()


def test_execution_receipt_rejects_matching_tools_through_symlinked_parent(
    tmp_path, monkeypatch
):
    receipt = _receipt(tmp_path)
    monkeypatch.setattr(execution, "verify_receipt", lambda payload, root: None)
    scripts = tmp_path / "scripts"
    retained = tmp_path / "retained-scripts"
    scripts.rename(retained)
    scripts.symlink_to(retained, target_is_directory=True)

    with pytest.raises(ValueError, match="regular file"):
        execution.verify_execution_receipt(receipt, root=tmp_path)
