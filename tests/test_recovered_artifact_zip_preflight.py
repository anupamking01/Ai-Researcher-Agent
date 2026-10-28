"""Synthetic ZIP fixtures only: no historical artifacts or research reruns."""
from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import zipfile

import pytest

from scripts import preflight_recovered_artifact_zip as audit


def _zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name, content in entries.items():
            out.writestr(name, content)
    return path


def test_valid_archive_is_inspected_without_extraction(tmp_path):
    path = _zip(tmp_path / "candidate.zip", {
        "outputs/experiment_traces/D3/sample.json": b'{"state":"synthetic"}',
        "outputs/sample/research_report.md": b"# Synthetic\n",
    })
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = audit.audit_recovered_zip(path, expected_archive_sha256=digest)
    assert receipt["expected_archive_sha256_matched"] is True
    assert receipt["archive_sha256_observed_now"] == digest
    assert receipt["file_count"] == 2
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert {f["path"] for f in receipt["files"]} == {
        "outputs/experiment_traces/D3/sample.json",
        "outputs/sample/research_report.md",
    }
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("name", [
    "../escape.txt", "/absolute.txt", "C:/drive.txt", "a\\b.txt",
    "folder//file.txt", "folder/./file.txt", "folder/../file.txt",
    "a/\u202efile.txt",
])
def test_unsafe_paths_rejected(tmp_path, name):
    path = _zip(tmp_path / "bad.zip", {name: b"x"})
    with pytest.raises(audit.RecoveredArchiveError, match="unsafe ZIP member"):
        audit.audit_recovered_zip(path)


def test_casefold_path_collisions_are_rejected(tmp_path):
    path = _zip(tmp_path / "bad.zip", {"A.txt": b"one", "a.txt": b"two"})
    with pytest.raises(audit.RecoveredArchiveError, match="duplicate or nonportable"):
        audit.audit_recovered_zip(path)


def test_file_as_directory_conflict_is_rejected(tmp_path):
    path = _zip(tmp_path / "bad.zip", {"a": b"one", "a/b": b"two"})
    with pytest.raises(audit.RecoveredArchiveError, match="conflicts"):
        audit.audit_recovered_zip(path)


def test_symbolic_link_member_is_rejected(tmp_path):
    path = tmp_path / "bad.zip"
    entry = zipfile.ZipInfo("link")
    entry.create_system = 3
    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, "w") as out:
        out.writestr(entry, "target")
    with pytest.raises(audit.RecoveredArchiveError, match="link or special"):
        audit.audit_recovered_zip(path)


def test_symlink_archive_is_rejected(tmp_path):
    target = _zip(tmp_path / "real.zip", {"good.txt": b"data"})
    alias = tmp_path / "alias.zip"
    alias.symlink_to(target)
    with pytest.raises(audit.RecoveredArchiveError):
        audit.audit_recovered_zip(alias)


def test_tampered_pin_rejected(tmp_path):
    path = _zip(tmp_path / "bad.zip", {"good.txt": b"data"})
    with pytest.raises(audit.RecoveredArchiveError, match="differs"):
        audit.audit_recovered_zip(path, expected_archive_sha256="0" * 64)


@pytest.mark.parametrize("invalid", ["A" * 64, "sha256:" + "a" * 64, "", "x" * 64])
def test_invalid_pin_format_rejected(tmp_path, invalid):
    path = _zip(tmp_path / "bad.zip", {"good.txt": b"data"})
    with pytest.raises(audit.RecoveredArchiveError, match="lowercase 64-hex"):
        audit.audit_recovered_zip(path, expected_archive_sha256=invalid)


def test_member_limit_rejected_before_decompression(tmp_path, monkeypatch):
    path = _zip(tmp_path / "bad.zip", {"one": b"1", "two": b"2"})
    monkeypatch.setattr(audit, "MAX_MEMBERS", 1)
    with pytest.raises(audit.RecoveredArchiveError, match="member count"):
        audit.audit_recovered_zip(path)


def test_member_size_limit_rejected(tmp_path, monkeypatch):
    path = _zip(tmp_path / "bad.zip", {"one": b"12345678"})
    monkeypatch.setattr(audit, "MAX_MEMBER_BYTES", 7)
    with pytest.raises(audit.RecoveredArchiveError, match="member exceeds size"):
        audit.audit_recovered_zip(path)


def test_total_expanded_limit_rejected(tmp_path, monkeypatch):
    path = _zip(tmp_path / "bad.zip", {"one": b"12345", "two": b"12345"})
    monkeypatch.setattr(audit, "MAX_UNCOMPRESSED_BYTES", 9)
    with pytest.raises(audit.RecoveredArchiveError, match="total uncompressed"):
        audit.audit_recovered_zip(path)


def test_expansion_ratio_rejected_before_read(tmp_path, monkeypatch):
    path = _zip(tmp_path / "bad.zip", {"one": b"0" * 3000})
    monkeypatch.setattr(audit, "MAX_COMPRESSION_RATIO", 2)
    with pytest.raises(audit.RecoveredArchiveError, match="expansion limit"):
        audit.audit_recovered_zip(path)


def test_non_zip_fails_closed(tmp_path):
    path = tmp_path / "not-a-zip.zip"
    path.write_bytes(b"not a ZIP")
    with pytest.raises(audit.RecoveredArchiveError, match="cannot safely inspect"):
        audit.audit_recovered_zip(path)


def test_empty_deflated_directory_entry_is_allowed(tmp_path):
    path = tmp_path / "directory.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as out:
        out.writestr("folder/", b"")
        out.writestr("folder/report.md", b"# Synthetic")
    receipt = audit.audit_recovered_zip(path)
    assert receipt["file_count"] == 1
    assert receipt["files"][0]["path"] == "folder/report.md"


def test_directory_crc_mismatch_is_rejected(tmp_path):
    """The ZIP reader must inspect directory CRCs, not just regular files."""
    path = _zip(tmp_path / "bad-directory-crc.zip", {
        "folder/": b"",
        "folder/report.md": b"# Synthetic",
    })
    raw = bytearray(path.read_bytes())
    central_header = raw.index(b"PK\\x01\\x02")
    # Central-directory CRC32 lives 16 bytes after its signature.
    raw[central_header + 16:central_header + 20] = (1).to_bytes(4, "little")
    path.write_bytes(raw)
    with pytest.raises(audit.RecoveredArchiveError, match="cannot safely inspect ZIP"):
        audit.audit_recovered_zip(path)


def test_directory_corrupt_deflate_stream_is_rejected(tmp_path):
    """An empty directory cannot conceal corrupt compressed data."""
    path = _zip(tmp_path / "bad-directory-stream.zip", {
        "folder/": b"",
        "folder/report.md": b"# Synthetic",
    })
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("folder/")
        assert info.compress_type == zipfile.ZIP_DEFLATED
        assert info.compress_size == 2
        offset = info.header_offset + 30 + len(info.filename.encode("utf-8")) + len(info.extra)
    raw = bytearray(path.read_bytes())
    raw[offset] = 0xFF  # Invalid DEFLATE block header; central metadata unchanged.
    path.write_bytes(raw)
    with pytest.raises(audit.RecoveredArchiveError, match="cannot safely inspect ZIP"):
        audit.audit_recovered_zip(path)


def test_directory_local_name_disagreement_is_rejected(tmp_path):
    """Local and central ZIP headers must agree for directories too."""
    path = _zip(tmp_path / "bad-directory-local-header.zip", {
        "folder/": b"",
        "folder/report.md": b"# Synthetic",
    })
    raw = bytearray(path.read_bytes())
    assert raw.startswith(b"PK\\x03\\x04")
    assert raw[30:37] == b"folder/"
    raw[30:37] = b"foldEr/"  # Same byte count; central entry remains "folder/".
    path.write_bytes(raw)
    with pytest.raises(audit.RecoveredArchiveError, match="cannot safely inspect ZIP"):
        audit.audit_recovered_zip(path)
