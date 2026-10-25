"""Synthetic checked-snapshot capture regressions; no treatments or evaluator calls."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from scripts import run_verified_main_study_analysis as verified
from scripts.fingerprint_research_artifacts import build_manifest


def _inputs(root: Path):
    output = root / "outputs"
    output.mkdir()
    main = output / "main_study_runs.csv"
    support = output / "posthoc_support_runs.csv"
    main.write_bytes(b"variant_id,task_id\\nD3,main-01\\n")
    support.write_bytes(b"claims_checked,supported\\n1,1\\n")
    manifest = build_manifest([main, support], root=root)
    return main, support, manifest["artifacts"]


def test_snapshot_capture_round_trips_exact_pinned_bytes(tmp_path):
    main, support, entries = _inputs(tmp_path)
    snapshot_root = tmp_path / "snapshot"
    snapshots = verified._capture_verified_inputs(
        entries, root=tmp_path, snapshot_root=snapshot_root
    )
    assert snapshots[verified.CANONICAL_MAIN].read_bytes() == main.read_bytes()
    assert snapshots[verified.CANONICAL_SUPPORT].read_bytes() == support.read_bytes()


def test_snapshot_source_never_uses_unchecked_path_read_bytes(tmp_path, monkeypatch):
    main, support, entries = _inputs(tmp_path)
    original = Path.read_bytes

    def forbidden_live_read(path):
        if path in {main, support}:
            raise AssertionError("unchecked live-source Path.read_bytes")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", forbidden_live_read)
    snapshots = verified._capture_verified_inputs(
        entries, root=tmp_path, snapshot_root=tmp_path / "snapshot"
    )
    assert snapshots[verified.CANONICAL_MAIN].read_bytes().startswith(b"variant_id")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="requires POSIX FIFO")
def test_fifo_substitution_between_fingerprint_and_capture_cannot_block(
    tmp_path, monkeypatch
):
    main, _, entries = _inputs(tmp_path)
    original = verified.fingerprint_regular_file_with_identity
    swapped = False

    def substitute(candidate):
        nonlocal swapped
        result = original(candidate)
        if Path(candidate) == main and not swapped:
            swapped = True
            main.unlink()
            os.mkfifo(main)
        return result

    monkeypatch.setattr(verified, "fingerprint_regular_file_with_identity", substitute)
    with pytest.raises(ValueError, match="changed while capturing verified analysis input"):
        verified._capture_verified_inputs(
            entries, root=tmp_path, snapshot_root=tmp_path / "snapshot"
        )
    assert swapped


def test_byte_identical_inode_replacement_before_capture_is_rejected(
    tmp_path, monkeypatch
):
    main, _, entries = _inputs(tmp_path)
    original = verified.fingerprint_regular_file_with_identity
    swapped = False

    def substitute(candidate):
        nonlocal swapped
        result = original(candidate)
        if Path(candidate) == main and not swapped:
            swapped = True
            new_path = tmp_path / "byte-identical-replacement"
            new_path.write_bytes(main.read_bytes())
            os.replace(new_path, main)
        return result

    monkeypatch.setattr(verified, "fingerprint_regular_file_with_identity", substitute)
    with pytest.raises(ValueError, match="changed while capturing verified analysis input"):
        verified._capture_verified_inputs(
            entries, root=tmp_path, snapshot_root=tmp_path / "snapshot"
        )
    assert swapped


def test_concurrent_growth_is_rejected_with_manifest_bounded_read(
    tmp_path, monkeypatch
):
    main, _, _ = _inputs(tmp_path)
    source = main.read_bytes()
    st = main.stat()
    pinned = (hashlib.sha256(source).hexdigest(), len(source), (st.st_dev, st.st_ino))
    monkeypatch.setattr(
        verified, "fingerprint_regular_file_with_identity", lambda _: pinned
    )
    original_read = os.read
    appended = False

    def grow_before_read(descriptor, count):
        nonlocal appended
        if not appended:
            appended = True
            with main.open("ab") as handle:
                handle.write(b"extra")
        return original_read(descriptor, count)

    monkeypatch.setattr(verified.os, "read", grow_before_read)
    with pytest.raises(ValueError, match="exceeded declared size|changed during capture"):
        verified._capture_manifest_pinned_regular_bytes(
            main, expected_sha256=pinned[0], expected_size=pinned[1]
        )
    assert appended


def test_pinned_capture_rejects_wrong_declared_size_before_read(tmp_path):
    main, _, _ = _inputs(tmp_path)
    content = main.read_bytes()
    with pytest.raises(ValueError, match="changed before capture"):
        verified._capture_manifest_pinned_regular_bytes(
            main,
            expected_sha256=hashlib.sha256(content).hexdigest(),
            expected_size=len(content) + 1,
        )


def test_validator_capture_does_not_use_unchecked_path_read_bytes(
    tmp_path, monkeypatch
):
    validator = tmp_path / verified.INPUT_VALIDATOR
    validator.parent.mkdir(parents=True)
    validator.write_text("SOURCE_MARKER = 'pinned'\\n", encoding="utf-8")
    original_read = Path.read_bytes

    def forbid_validator_path_read(path):
        if path == validator:
            raise AssertionError("unchecked validator Path.read_bytes")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", forbid_validator_path_read)
    binding = verified._capture_input_validator_binding(root=tmp_path)
    assert binding.module.SOURCE_MARKER == "pinned"
    assert binding.sha256 == hashlib.sha256(
        b"SOURCE_MARKER = 'pinned'\\n"
    ).hexdigest()
