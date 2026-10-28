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



@pytest.mark.parametrize("name", [
    "reports/\uFF0E\uFF0E/trace.json",  # FULLWIDTH FULL STOP => ".."
    "reports/\uFF0E/trace.json",        # FULLWIDTH FULL STOP => "."
    "reports\uFF0Ftrace.json",          # FULLWIDTH SOLIDUS => new separator
    "reports/\uFF0F/trace.json",        # new separators/empty components
    "C\uFF1A/trace.json",               # FULLWIDTH COLON => drive prefix
    "reports\uFF3Ctrace.json",          # FULLWIDTH REVERSE SOLIDUS => backslash
])
def test_compatibility_normalization_cannot_create_unsafe_paths(tmp_path, name):
    """Original ZIP spelling can hide traversal/separators after NFKC."""
    path = _zip(tmp_path / "unicode-unsafe.zip", {name: b"synthetic"})
    with pytest.raises(audit.RecoveredArchiveError, match="unsafe normalized ZIP member"):
        audit.audit_recovered_zip(path)


def test_harmless_compatible_unicode_filename_still_valid(tmp_path):
    path = _zip(tmp_path / "unicode-ok.zip", {"reports/\uFF26ullwidth.txt": b"synthetic"})
    receipt = audit.audit_recovered_zip(path)
    assert receipt["file_count"] == 1
    assert receipt["files"][0]["path"] == "reports/\uFF26ullwidth.txt"


@pytest.mark.parametrize("name", [
    "results/report.md:ads",            # NTFS alternate data stream
    "results/report?.md",              # Windows wildcard
    "results/report*2026.md",
    "results/report<old>.md",
    "results/a|b.txt",
    "results/a\"b.txt",
    "results/report.",                 # Win32 trims trailing periods
    "results/report ",                # Win32 trims trailing spaces
    "results/trace. /child.json",     # dangerous intermediate component
    "results/NUL.txt",
    "results/CON",                    # device name without extension
    "results/aux/report.json",        # reserved directory component
    "results/PRN.md",
    "results/COM1.log",
    "results/LPT9.log",
    "results/CONIN$.txt",
    "results/CONOUT$.txt",
    "results/COM\u00B9.md",          # superscript digit becomes 1 under NFKC
    "results/\uFF23\uFF2F\uFF2E.txt", # fullwidth CON becomes device name
    "results/nul .txt",               # Win32 strips spaces before extension
])
def test_nonportable_windows_aliases_devices_and_ads_rejected(tmp_path, name):
    """Reject paths that cannot be carried safely across common filesystems."""
    path = _zip(tmp_path / "windows-unsafe.zip", {name: b"synthetic"})
    with pytest.raises(audit.RecoveredArchiveError, match="unsafe normalized ZIP member"):
        audit.audit_recovered_zip(path)


@pytest.mark.parametrize("name", [
    "results/console.md", "results/com10.txt", "results/trace..md",
    "results/nulled/report.md",
])
def test_similar_but_portable_names_still_allowed(tmp_path, name):
    path = _zip(tmp_path / "windows-ok.zip", {name: b"synthetic"})
    receipt = audit.audit_recovered_zip(path)
    assert [f["path"] for f in receipt["files"]] == [name]


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
    central_header = raw.index(b"PK\x01\x02")
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
    assert raw.startswith(b"PK\x03\x04")
    assert raw[30:37] == b"folder/"
    raw[30:37] = b"foldEr/"  # Same byte count; central entry remains "folder/".
    path.write_bytes(raw)
    with pytest.raises(audit.RecoveredArchiveError, match="cannot safely inspect ZIP"):
        audit.audit_recovered_zip(path)


def test_central_directory_member_limit_checked_before_zipfile_open(tmp_path, monkeypatch):
    """Reject many tiny headers without allocating thousands of ZipInfo objects."""
    path = tmp_path / "too-many-headers.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as out:
        for index in range(audit.MAX_MEMBERS + 1):
            out.writestr(f"synthetic/{index}.txt", b"x")

    def must_not_open(*args, **kwargs):
        raise AssertionError("ZipFile must not parse an overlarge directory")

    monkeypatch.setattr(audit.zipfile, "ZipFile", must_not_open)
    with pytest.raises(audit.RecoveredArchiveError, match="central-directory member count"):
        audit.audit_recovered_zip(path)


def test_false_small_eocd_count_cannot_bypass_preparse_bound(tmp_path, monkeypatch):
    """Do not trust just the EOCD entry count: walk its actual records."""
    path = _zip(tmp_path / "lied-about-count.zip", {"one.txt": b"1", "two.txt": b"2"})
    raw = bytearray(path.read_bytes())
    offset = len(raw) - 22
    assert raw[offset:offset + 4] == b"PK\x05\x06"
    raw[offset + 8:offset + 12] = b"\x01\x00\x01\x00"
    path.write_bytes(raw)

    def must_not_open(*args, **kwargs):
        raise AssertionError("ZipFile must not parse inconsistent directory headers")

    monkeypatch.setattr(audit.zipfile, "ZipFile", must_not_open)
    with pytest.raises(audit.RecoveredArchiveError, match="member count does not match"):
        audit.audit_recovered_zip(path)


def test_oversized_claimed_central_directory_rejected_before_open(tmp_path, monkeypatch):
    path = _zip(tmp_path / "huge-directory.zip", {"good.txt": b"synthetic"})
    raw = bytearray(path.read_bytes())
    offset = len(raw) - 22
    assert raw[offset:offset + 4] == b"PK\x05\x06"
    raw[offset + 12:offset + 16] = (
        audit.MAX_CENTRAL_DIRECTORY_BYTES + 1
    ).to_bytes(4, "little")
    path.write_bytes(raw)

    def must_not_open(*args, **kwargs):
        raise AssertionError("ZipFile must not read an oversized directory")

    monkeypatch.setattr(audit.zipfile, "ZipFile", must_not_open)
    with pytest.raises(audit.RecoveredArchiveError, match="central directory exceeds"):
        audit.audit_recovered_zip(path)


def test_central_directory_overrun_rejected_before_open(tmp_path, monkeypatch):
    path = _zip(tmp_path / "overrun.zip", {"good.txt": b"synthetic"})
    raw = bytearray(path.read_bytes())
    central = raw.index(b"PK\x01\x02")
    # Extra-field length in the fixed central-directory header.
    raw[central + 30:central + 32] = (65535).to_bytes(2, "little")
    path.write_bytes(raw)

    def must_not_open(*args, **kwargs):
        raise AssertionError("ZipFile must not parse an overrun")

    monkeypatch.setattr(audit.zipfile, "ZipFile", must_not_open)
    with pytest.raises(audit.RecoveredArchiveError, match="entry exceeds"):
        audit.audit_recovered_zip(path)


def test_unaccounted_trailing_bytes_rejected(tmp_path):
    """An ambiguous trailer is not part of a canonical GitHub artifact ZIP."""
    path = _zip(tmp_path / "extra-trailer.zip", {"good.txt": b"synthetic"})
    path.write_bytes(path.read_bytes() + b"out-of-band-trailer")
    with pytest.raises(audit.RecoveredArchiveError, match="terminal end-of-central-directory"):
        audit.audit_recovered_zip(path)


def test_ordinary_zip_comment_remains_supported(tmp_path):
    path = tmp_path / "commented.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as out:
        out.writestr("reports/test.md", b"# Synthetic")
        out.comment = b"ordinary ZIP comment"
    receipt = audit.audit_recovered_zip(path)
    assert receipt["file_count"] == 1
    assert receipt["files"][0]["path"] == "reports/test.md"
