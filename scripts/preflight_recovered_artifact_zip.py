"""Read-only, bounded preflight of a candidate recovered VERA artifact ZIP.

This verifies structural safety and computes *present-day* file-byte digests.
It neither extracts nor authenticates historical evidence. In particular, a
digest computed here is NOT a previously retained independent archive pin.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import unicodedata
import zipfile
import zlib

MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 2000
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000
CHUNK_BYTES = 1024 * 1024
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

WINDOWS_FORBIDDEN_CHARS = frozenset('<>:"|?*')
WINDOWS_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul", "conin$", "conout$"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)


class RecoveredArchiveError(ValueError):
    """An archive cannot be trusted even for safe offline inspection."""


def _fingerprint(handle) -> str:
    handle.seek(0)
    digest = hashlib.sha256()
    while True:
        part = handle.read(CHUNK_BYTES)
        if not part:
            break
        digest.update(part)
    return digest.hexdigest()


def _path_key(name: str) -> str:
    """Use one conservative portable path identity, without rewriting entries."""
    if (
        not name or len(name) > 1024
        or name.startswith("/")
        or "\\" in name
        or "\x00" in name
        or unicodedata.normalize("NFC", name) != name
    ):
        raise RecoveredArchiveError(f"unsafe ZIP member name: {name!r}")
    raw = name.rstrip("/")
    parts = raw.split("/")
    if (
        not raw or len(parts) > 32
        or any(part in ("", ".", "..") for part in parts)
        or ":" in parts[0]
        or any(unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in name)
    ):
        raise RecoveredArchiveError(f"unsafe ZIP member name: {name!r}")
    # Compatibility normalization must not *create* dangerous path syntax.
    # Checking only the original ZIP name would allow e.g. FULLWIDTH FULL STOP
    # segments to become "..", or FULLWIDTH SOLIDUS to become "/" downstream.
    normalized = unicodedata.normalize("NFKC", raw).casefold()
    normalized_parts = normalized.split("/")
    if (
        len(normalized_parts) != len(parts)
        or any(part in ("", ".", "..") for part in normalized_parts)
        or "\\" in normalized
        or ":" in normalized_parts[0]
        or any(unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in normalized)
        or any(
            # Windows aliases, devices, and NTFS alternate data streams must
            # not turn a structurally safe member into an unsafe extraction.
            part.endswith((" ", "."))
            or any(char in WINDOWS_FORBIDDEN_CHARS for char in part)
            or part.split(".", 1)[0].rstrip(" ") in WINDOWS_DEVICE_NAMES
            for part in normalized_parts
        )
    ):
        raise RecoveredArchiveError(f"unsafe normalized ZIP member name: {name!r}")
    return normalized


def _inspect_member(info: zipfile.ZipInfo) -> tuple[str, bool]:
    key = _path_key(info.filename)
    is_directory = info.is_dir()
    mode = stat.S_IFMT(info.external_attr >> 16)
    if mode not in (0, stat.S_IFDIR if is_directory else stat.S_IFREG):
        raise RecoveredArchiveError(f"ZIP contains a link or special entry: {info.filename!r}")
    if info.flag_bits & 1:
        raise RecoveredArchiveError(f"encrypted ZIP entry: {info.filename!r}")
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise RecoveredArchiveError(f"unsupported ZIP compression: {info.filename!r}")
    if info.file_size < 0 or info.compress_size < 0:
        raise RecoveredArchiveError("negative ZIP member size")
    if is_directory and info.file_size:
        raise RecoveredArchiveError(f"nonempty directory entry: {info.filename!r}")
    if info.file_size > MAX_MEMBER_BYTES:
        raise RecoveredArchiveError(f"ZIP member exceeds size limit: {info.filename!r}")
    if info.file_size and (
        info.compress_size == 0
        or info.file_size > MAX_COMPRESSION_RATIO * info.compress_size
    ):
        raise RecoveredArchiveError(f"ZIP member exceeds expansion limit: {info.filename!r}")
    return key, is_directory


def _unchanged(original: os.stat_result, current: os.stat_result) -> bool:
    return (
        original.st_dev, original.st_ino, original.st_mode,
        original.st_size, original.st_mtime_ns, original.st_ctime_ns,
    ) == (
        current.st_dev, current.st_ino, current.st_mode,
        current.st_size, current.st_mtime_ns, current.st_ctime_ns,
    )


def audit_recovered_zip(path: Path, *, expected_archive_sha256: str | None = None) -> dict:
    """Inspect one ZIP without extraction, model calls, or archive modifications.

    An optional expected SHA-256 must have been independently recorded before
    this inspection to serve as a historical custody anchor.
    """
    path = Path(path)
    if expected_archive_sha256 is not None and not HEX_SHA256.fullmatch(expected_archive_sha256):
        raise RecoveredArchiveError("expected archive SHA-256 must be lowercase 64-hex")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as handle:
            before = os.fstat(handle.fileno())
            path_before = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or not _unchanged(before, path_before):
                raise RecoveredArchiveError("archive must be a stable regular file, not a link")
            if not 0 < before.st_size <= MAX_ARCHIVE_BYTES:
                raise RecoveredArchiveError("archive file exceeds the bounded ZIP size range")
            archive_sha256 = _fingerprint(handle)
            if expected_archive_sha256 and archive_sha256 != expected_archive_sha256:
                raise RecoveredArchiveError("archive SHA-256 differs from supplied independent pin")

            files = []
            total = 0
            seen: set[str] = set()
            file_keys: set[str] = set()
            with zipfile.ZipFile(handle, mode="r") as archive:
                entries = archive.infolist()
                if not entries or len(entries) > MAX_MEMBERS:
                    raise RecoveredArchiveError("ZIP member count outside permitted bounds")
                # Validate all central-directory entries BEFORE decompressing any bytes.
                for info in entries:
                    key, is_directory = _inspect_member(info)
                    if key in seen:
                        raise RecoveredArchiveError(f"duplicate or nonportable ZIP path: {info.filename!r}")
                    seen.add(key)
                    if not is_directory:
                        file_keys.add(key)
                        total += info.file_size
                        if total > MAX_UNCOMPRESSED_BYTES:
                            raise RecoveredArchiveError("ZIP total uncompressed size exceeds limit")
                if not file_keys:
                    raise RecoveredArchiveError("ZIP contains no regular files")
                for key in seen:
                    ancestors = key.split("/")
                    if any("/".join(ancestors[:n]) in file_keys for n in range(1, len(ancestors))):
                        raise RecoveredArchiveError("ZIP file conflicts with a nested member path")
                for info in entries:
                    if info.is_dir():
                        # ZIP directory members are real entries with local headers,
                        # compressed streams, and CRCs. Skipping archive.open() would
                        # accept corrupt directory metadata or unreadable DEFLATE data.
                        # A one-byte read reaches EOF for a valid empty directory and
                        # makes ZipExtFile validate its stream and CRC.
                        with archive.open(info, mode="r") as directory:
                            if directory.read(1):
                                raise RecoveredArchiveError(
                                    f"ZIP directory contains data: {info.filename!r}"
                                )
                        continue
                    digest = hashlib.sha256()
                    size = 0
                    # ZipFile verifies CRC on reaching EOF; our bounds also
                    # protect against understated central-directory sizes.
                    with archive.open(info, mode="r") as member:
                        while True:
                            part = member.read(CHUNK_BYTES)
                            if not part:
                                break
                            size += len(part)
                            if size > info.file_size or size > MAX_MEMBER_BYTES:
                                raise RecoveredArchiveError("ZIP member expanded beyond declared size")
                            digest.update(part)
                    if size != info.file_size:
                        raise RecoveredArchiveError("ZIP member did not match declared uncompressed size")
                    files.append({
                        "path": info.filename,
                        "uncompressed_bytes": size,
                        "sha256": digest.hexdigest(),
                    })
            # Re-read the same descriptor, and recheck its on-disk pathname:
            # an in-place edit or a path swap must not yield a PASS.
            if (
                not _unchanged(before, os.fstat(handle.fileno()))
                or not _unchanged(before, os.stat(path, follow_symlinks=False))
                or _fingerprint(handle) != archive_sha256
            ):
                raise RecoveredArchiveError("archive changed during inspection")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, RuntimeError,
            NotImplementedError, zlib.error) as exc:
        raise RecoveredArchiveError(f"cannot safely inspect ZIP: {exc}") from exc
    return {
        "schema_version": 1,
        "status": "zip_structurally_verified_not_historically_authenticated",
        "archive_sha256_observed_now": archive_sha256,
        "expected_archive_sha256_matched": expected_archive_sha256 is not None,
        "archive_bytes": before.st_size,
        "file_count": len(files),
        "total_uncompressed_bytes": total,
        "files": files,
        "historical_evidence_authenticated": False,
        "human_evaluation_ready": False,
        "experimental_treatments_rerun": False,
        "human_ratings_generated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="offline ZIP file; never extracted")
    parser.add_argument("--expected-archive-sha256", help="independently retained prior ZIP-byte pin")
    args = parser.parse_args()
    try:
        receipt = audit_recovered_zip(
            args.archive, expected_archive_sha256=args.expected_archive_sha256
        )
    except (RecoveredArchiveError, ValueError) as exc:
        parser.exit(1, f"VERA RECOVERED ZIP PREFLIGHT: FAIL: {exc}\n")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
