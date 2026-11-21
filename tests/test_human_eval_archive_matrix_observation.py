"""Synthetic offline tests of cross-window recovered-candidate stability."""
import os

import pytest

from scripts import audit_human_eval_archive_readiness as audit


def test_unchanged_pair_remains_locally_consistent(tmp_path):
    trace = tmp_path / "trace.json"
    report = tmp_path / "research_report.md"
    trace.write_bytes(b'{"synthetic": true}')
    report.write_bytes(b"# Synthetic report\n")
    trace_bytes, trace_pin = audit._capture_recovery_candidate(
        trace, label="synthetic trace"
    )
    report_bytes, report_pin = audit._capture_recovery_candidate(
        report, label="synthetic report"
    )
    assert trace_bytes == trace.read_bytes()
    assert report_bytes == report.read_bytes()
    assert audit._verify_recovery_candidate_window([trace_pin, report_pin]) is None


def test_same_size_rewrite_with_restored_mtime_is_rejected(tmp_path):
    source = tmp_path / "trace.json"
    source.write_bytes(b"syntheticA")
    _, pin = audit._capture_recovery_candidate(source, label="synthetic trace")
    before = source.stat()
    source.write_bytes(b"syntheticB")
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(ValueError, match="changed"):
        audit._verify_recovery_candidate_window([pin])


def test_byte_identical_atomic_replacement_is_rejected(tmp_path):
    source = tmp_path / "research_report.md"
    source.write_bytes(b"synthetic only")
    _, pin = audit._capture_recovery_candidate(source, label="synthetic report")
    replacement = tmp_path / "other-inode"
    replacement.write_bytes(b"synthetic only")
    replacement.replace(source)
    with pytest.raises(ValueError, match="changed"):
        audit._verify_recovery_candidate_window([pin])


def test_redirected_parent_is_rejected(tmp_path):
    parent = tmp_path / "archive"
    parent.mkdir()
    source = parent / "trace.json"
    source.write_bytes(b"synthetic")
    _, pin = audit._capture_recovery_candidate(source, label="synthetic trace")
    original = tmp_path / "original-archive"
    parent.rename(original)
    parent.symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe|redirected|changed"):
        audit._verify_recovery_candidate_window([pin])
