"""Synthetic-only checks for portable, blinded governing-input archives.

These ratings and packet reports are fixtures, not human annotations or study
findings. No treatment mapping, model, evaluator, or network is used.
"""
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as verify

ARCHIVES = {
    "packet": "governing_inputs/packet.jsonl",
    "protocol": "governing_inputs/HUMAN_EVAL_PROTOCOL.md",
    "assignment_plan": "governing_inputs/HUMAN_EVAL_ASSIGNMENT_PLAN.md",
}
OPTIONS = {"packet": "packet_path", "protocol": "protocol_path",
           "assignment_plan": "assignment_plan_path"}


@pytest.fixture
def inputs(tmp_path):
    packet = tmp_path / "original-packet.jsonl"
    packet.write_bytes(b'{"blind_id":"H001"}\r\n{"blind_id":"H002"}\r\n')
    protocol = tmp_path / "original-protocol.md"
    protocol.write_bytes("# Synthetic rubric — λ\r\n".encode("utf-8"))
    assignment = tmp_path / "original-assignment.md"
    assignment.write_bytes(b"# Synthetic independent assignment\n")
    paths = [tmp_path / "a.csv", tmp_path / "b.csv"]
    for index, path in enumerate(paths):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(freeze.RATING_FIELDS)
            for blind_id in ("H001", "H002"):
                writer.writerow([f"synthetic-{index}", blind_id, "2", "3", "4",
                                 "", "3", "Synthetic missing-dimension reason."])
    return paths, {
        "packet_path": packet, "protocol_path": protocol,
        "assignment_plan_path": assignment, "output_root": tmp_path / "freeze",
    }


def _verify_options(options):
    return {"freeze_root" if key == "output_root" else key: value
            for key, value in options.items()}


def _save_manifest(root, manifest):
    (root / "freeze_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def _declare_archive(options, manifest):
    # Also constructs a declared archive on pre-feature code, so the regression
    # demonstrates that its verifier ignores these governing-input declarations.
    root = options["output_root"]
    (root / "governing_inputs").mkdir(exist_ok=True)
    for role, relative in ARCHIVES.items():
        data = options[OPTIONS[role]].read_bytes()
        (root / relative).write_bytes(data)
        manifest[role].update(archive_path=relative, bytes=len(data),
                              sha256=hashlib.sha256(data).hexdigest())
    _save_manifest(root, manifest)


def test_freeze_archives_exact_pre_validation_governing_bytes(inputs, monkeypatch):
    paths, options = inputs
    captured = {role: options[key].read_bytes() for role, key in OPTIONS.items()}
    original_agreement = freeze.build_agreement

    def remove_originals_after_validation(rows):
        for key in OPTIONS.values():
            options[key].unlink()
        return original_agreement(rows)

    monkeypatch.setattr(freeze, "build_agreement", remove_originals_after_validation)
    manifest = freeze.freeze_ratings(paths, **options)
    for role, relative in ARCHIVES.items():
        archive = options["output_root"] / relative
        assert archive.is_file(), f"missing retained {role}"
        assert archive.read_bytes() == captured[role]
        assert manifest[role]["archive_path"] == relative
        assert manifest[role]["bytes"] == len(captured[role])
        assert manifest[role]["sha256"] == hashlib.sha256(captured[role]).hexdigest()
    assert manifest["frozen_ratings"]["dimension_counts"]["synthesis_reasoning_1_5"] == {
        "rated": 0, "missing": 4,
    }


@pytest.mark.parametrize("role", ARCHIVES)
def test_default_verifier_rejects_declared_governing_archive_drift(inputs, role):
    paths, options = inputs
    manifest = freeze.freeze_ratings(paths, **options)
    _declare_archive(options, manifest)
    (options["output_root"] / ARCHIVES[role]).write_bytes(b"changed retained input\n")
    with pytest.raises(ValueError, match="retained.*fingerprint"):
        verify.verify_frozen_snapshot(**_verify_options(options))


def test_relocated_freeze_verifies_without_any_external_inputs(inputs, tmp_path):
    paths, options = inputs
    freeze.freeze_ratings(paths, **options)
    relocated = tmp_path / "relocated"
    shutil.copytree(options["output_root"], relocated)
    before = {str(p.relative_to(relocated)): p.read_bytes()
              for p in relocated.rglob("*") if p.is_file()}
    for path in [*paths, *(options[key] for key in OPTIONS.values())]:
        path.unlink()
    shutil.rmtree(options["output_root"])
    receipt = verify.verify_frozen_snapshot(freeze_root=relocated, use_retained_inputs=True)
    assert receipt["status"] == "blinded_human_ratings_verified"
    assert receipt["n_rows"] == 4
    assert receipt["n_annotators"] == 2
    assert receipt["blinding_key_used"] is False
    assert before == {str(p.relative_to(relocated)): p.read_bytes()
                      for p in relocated.rglob("*") if p.is_file()}


@pytest.mark.parametrize("role", ARCHIVES)
def test_external_governing_drift_is_not_silently_ignored(inputs, role):
    paths, options = inputs
    freeze.freeze_ratings(paths, **options)
    options[OPTIONS[role]].write_bytes(b"changed working copy\n")
    with pytest.raises(ValueError):
        verify.verify_frozen_snapshot(**_verify_options(options))
    receipt = verify.verify_frozen_snapshot(
        freeze_root=options["output_root"], use_retained_inputs=True,
    )
    assert receipt["n_rows"] == 4


@pytest.mark.parametrize("damage", ["missing", "redirect", "partial", "extra", "symlink", "directory_symlink"])
def test_retained_governing_archive_rejects_missing_or_redirected_inputs(inputs, damage):
    paths, options = inputs
    manifest = freeze.freeze_ratings(paths, **options)
    _declare_archive(options, manifest)
    root = options["output_root"]
    target = root / ARCHIVES["protocol"]
    if damage == "missing":
        target.unlink()
    elif damage == "redirect":
        manifest["protocol"]["archive_path"] = "../original-protocol.md"
    elif damage == "partial":
        del manifest["protocol"]["archive_path"]
    elif damage == "extra":
        (root / "governing_inputs" / "unexpected.csv").write_bytes(b"synthetic extra\n")
    elif damage == "symlink":
        target.unlink()
        target.symlink_to(options["protocol_path"])
    else:
        archive = root / "governing_inputs"
        moved = root.parent / "moved-governing"
        archive.rename(moved)
        archive.symlink_to(moved, target_is_directory=True)
    _save_manifest(root, manifest)
    with pytest.raises(ValueError, match="governing|retained"):
        verify.verify_frozen_snapshot(freeze_root=root, use_retained_inputs=True)


def test_legacy_requires_external_governing_files_and_is_not_backfilled(inputs):
    paths, options = inputs
    manifest = freeze.freeze_ratings(paths, **options)
    root = options["output_root"]
    if (root / "governing_inputs").exists():
        shutil.rmtree(root / "governing_inputs")
    for role in ARCHIVES:
        manifest[role].pop("archive_path", None)
    _save_manifest(root, manifest)
    assert verify.verify_frozen_snapshot(**_verify_options(options))["n_rows"] == 4
    with pytest.raises(ValueError, match="retained governing inputs.*required"):
        verify.verify_frozen_snapshot(freeze_root=root, use_retained_inputs=True)
    assert not (root / "governing_inputs").exists()


def test_retained_mode_rejects_explicit_external_governing_arguments(inputs):
    paths, options = inputs
    freeze.freeze_ratings(paths, **options)
    with pytest.raises(ValueError, match="cannot combine"):
        verify.verify_frozen_snapshot(**_verify_options(options), use_retained_inputs=True)


def test_archive_write_failure_never_publishes_manifest_or_reuses_destination(inputs, monkeypatch):
    paths, options = inputs
    original_open = Path.open

    def fail_archive_write(path, mode="r", *args, **kwargs):
        if path.parent.name == "governing_inputs" and "x" in mode:
            raise OSError("synthetic archive write failure")
        return original_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, "open", fail_archive_write)
        with pytest.raises(OSError, match="synthetic archive write failure"):
            freeze.freeze_ratings(paths, **options)
    assert options["output_root"].is_dir()
    assert not (options["output_root"] / "freeze_manifest.json").exists()
    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.freeze_ratings(paths, **options)


def test_cli_retained_inputs_mode_is_offline_and_read_only(inputs):
    paths, options = inputs
    freeze.freeze_ratings(paths, **options)
    for path in [*paths, *(options[key] for key in OPTIONS.values())]:
        path.unlink()
    result = subprocess.run([
        sys.executable, "-m", "scripts.verify_human_eval_freeze", "--freeze-root",
        str(options["output_root"]), "--retained-inputs",
    ], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
       timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    assert "HUMAN EVAL VERIFY: PASS" in result.stdout
    assert '"blinding_key_used": false' in result.stdout


@pytest.mark.parametrize("tampered", [False, True])
def test_analysis_carries_governing_archive_through_real_blinded_gate(inputs, monkeypatch, tampered):
    # Import here so the standalone archival tests only require the freezer and
    # verifier. Repository CI exercises this with the real analysis module too.
    from scripts import human_eval_analysis_core as core

    paths, options = inputs
    freeze.freeze_ratings(paths, **options)
    root = options["output_root"]
    if tampered:
        (root / ARCHIVES["protocol"]).write_bytes(b"tampered synthetic rubric")
    plan = root.parent / "analysis-plan.md"
    plan.write_text("Synthetic analysis-plan fixture\n", encoding="utf-8")
    real_verify = verify.verify_frozen_snapshot
    read_bytes = Path.read_bytes

    class BlindedGatePassed(Exception):
        pass

    def forbid_mapping_reads(path):
        assert path.name != "blinding_key.csv", "treatment identity opened before blinded gate"
        return read_bytes(path)

    def stop_after_real_verification(*args, **kwargs):
        receipt = real_verify(*args, **kwargs)
        assert receipt["n_rows"] == 4
        for relative in ARCHIVES.values():
            assert (kwargs["freeze_root"] / relative).read_bytes() == (root / relative).read_bytes()
        raise BlindedGatePassed

    monkeypatch.setattr(Path, "read_bytes", forbid_mapping_reads)
    monkeypatch.setattr(core.blind_verify, "verify_frozen_snapshot", stop_after_real_verification)
    expected = ValueError if tampered else BlindedGatePassed
    with pytest.raises(expected, match="retained protocol fingerprint" if tampered else None):
        core.analyze(
            [], freeze_root=root, packet_root=root.parent,
            packet_path=options["packet_path"], protocol_path=options["protocol_path"],
            assignment_plan_path=options["assignment_plan_path"], analysis_plan_path=plan,
        )
