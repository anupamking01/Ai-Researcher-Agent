"""Synthetic output-custody regressions; never rerun the frozen study."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from scripts import run_verified_main_study_analysis as verified


def _output(tmp_path: Path, content: bytes = b'{"frozen": true}\n'):
    parent = tmp_path / "outputs"
    parent.mkdir()
    target = parent / "inference.json"
    target.write_bytes(content)
    return target


def _read(target: Path):
    directory_fd = verified._open_output_directory(target.parent)
    try:
        return verified._read_output_at(directory_fd, target.name, label="inference")
    finally:
        os.close(directory_fd)


def test_bound_output_round_trips_exact_bytes(tmp_path):
    target = _output(tmp_path)
    assert _read(target) == target.read_bytes()


def test_missing_published_output_is_distinct_from_mutation(tmp_path):
    parent = tmp_path / "outputs"
    parent.mkdir()
    fd = verified._open_output_directory(parent)
    try:
        assert verified._read_output_at(fd, "not-present.json", label="inference") is None
    finally:
        os.close(fd)


def test_oversized_sparse_output_rejected_before_read(tmp_path, monkeypatch):
    target = _output(tmp_path)
    with target.open("r+b") as handle:
        handle.truncate(verified.MAX_VERIFIED_OUTPUT_BYTES + 1)

    def forbidden_read(*args):
        raise AssertionError("oversized output was read")

    monkeypatch.setattr(verified.os, "read", forbidden_read)
    with pytest.raises(ValueError, match="16 MiB output safety limit"):
        _read(target)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="requires POSIX FIFO")
def test_fifo_substitution_between_stat_and_open_cannot_block(tmp_path, monkeypatch):
    target = _output(tmp_path)
    original_open = os.open
    swapped = False

    def swap_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == target.name and dir_fd is not None and not swapped:
            swapped = True
            target.unlink()
            os.mkfifo(target)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(verified.os, "open", swap_open)
    with pytest.raises(ValueError, match="changed during capture"):
        _read(target)
    assert swapped


def test_byte_identical_inode_substitution_is_rejected(tmp_path, monkeypatch):
    target = _output(tmp_path)
    original_open = os.open
    swapped = False

    def swap_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == target.name and dir_fd is not None and not swapped:
            swapped = True
            replacement = tmp_path / "replacement.json"
            replacement.write_bytes(target.read_bytes())
            os.replace(replacement, target)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(verified.os, "open", swap_open)
    with pytest.raises(ValueError, match="changed during capture"):
        _read(target)
    assert swapped


def test_concurrent_output_growth_is_detected(tmp_path, monkeypatch):
    target = _output(tmp_path, b"abc")
    original_read = os.read
    mutated = False

    def grow_then_read(fd, size):
        nonlocal mutated
        if not mutated:
            mutated = True
            with target.open("ab") as handle:
                handle.write(b"def")
        return original_read(fd, size)

    monkeypatch.setattr(verified.os, "read", grow_then_read)
    with pytest.raises(ValueError, match="exceeded its original byte count|changed during capture"):
        _read(target)
    assert mutated


def test_post_read_path_substitution_is_detected(tmp_path, monkeypatch):
    target = _output(tmp_path)
    original_read = os.read
    substituted = False

    def replace_after_read(fd, size):
        nonlocal substituted
        chunk = original_read(fd, size)
        if chunk and not substituted:
            substituted = True
            replacement = tmp_path / "replacement.json"
            replacement.write_bytes(chunk)
            os.replace(replacement, target)
        return chunk

    monkeypatch.setattr(verified.os, "read", replace_after_read)
    with pytest.raises(ValueError, match="changed during capture"):
        _read(target)
    assert substituted


def test_candidate_mutation_during_verification_blocks_publication(tmp_path, monkeypatch):
    def stage(manifest, *, root, analyze=None, output_json=None, output_markdown=None):
        candidate_json, candidate_md = Path(output_json), Path(output_markdown)
        candidate_json.parent.mkdir(parents=True)
        candidate_md.parent.mkdir(parents=True)
        candidate_json.write_bytes(b'{"frozen": true}\n')
        candidate_md.write_bytes(b"# Frozen summary\n")
        return 0

    def mutate_after_scoring(*, root, json_path, markdown_path):
        Path(json_path).write_bytes(b'{"frozen": false}\n')

    monkeypatch.setattr(verified, "verify_and_run", stage)
    with pytest.raises(ValueError, match="candidate changed during output verification"):
        verified.verify_run_and_record(
            {"aggregate_sha256": "synthetic"},
            root=tmp_path,
            receipt_builder=lambda manifest, root: {"schema_version": 1},
            output_verifier=mutate_after_scoring,
        )
    assert not (tmp_path / verified.DEFAULT_JSON).exists()
    assert not (tmp_path / verified.DEFAULT_MARKDOWN).exists()


def test_post_verification_candidate_replacement_rejected_before_publish(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    json_path = candidate / "result.json"
    md_path = candidate / "result.md"
    json_path.write_bytes(b'{"observed": 1}\n')
    md_path.write_bytes(b"# Observed\n")
    pinned = verified._candidate_output_digests(json_path, md_path)
    json_path.write_bytes(b'{"observed": 2}\n')

    with pytest.raises(ValueError, match="candidate changed after output verification"):
        verified._publish_verified_outputs(
            json_path,
            md_path,
            root=tmp_path,
            expected_sha256=pinned,
        )
    assert not (tmp_path / verified.DEFAULT_JSON).exists()


def test_candidate_capture_never_uses_unchecked_path_read_bytes(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    json_path = candidate / "result.json"
    md_path = candidate / "result.md"
    json_path.write_bytes(b"verified-json")
    md_path.write_bytes(b"verified-markdown")
    original = Path.read_bytes

    def forbid_candidate_read(path):
        if path in (json_path, md_path):
            raise AssertionError("unchecked candidate Path.read_bytes")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", forbid_candidate_read)
    pinned = {
        "canonical_inference": hashlib.sha256(b"verified-json").hexdigest(),
        "manuscript_rendering": hashlib.sha256(b"verified-markdown").hexdigest(),
    }
    verified._publish_verified_outputs(
        json_path, md_path, root=tmp_path, expected_sha256=pinned
    )
    assert (tmp_path / verified.DEFAULT_JSON).read_bytes() == b"verified-json"
    assert (tmp_path / verified.DEFAULT_MARKDOWN).read_bytes() == b"verified-markdown"
