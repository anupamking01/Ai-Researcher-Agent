"""Verify the original downloaded GitHub Actions qualified-report ZIP, without extracting it.

The existing two-file verifier checks a pair *after* unpacking; this gate also
checks the archive container, its complete member inventory, and byte continuity.
It does not establish independent custody or authenticate missing experiment data.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile

from scripts.assemble_qualified_main_study_report import ROOT, MAX_MARKDOWN_BYTES
from scripts.preflight_recovered_artifact_zip import audit_recovered_zip
from scripts.verify_qualified_reporting_artifact import verify_distributed_artifact

MAX_DOWNLOAD_ZIP_BYTES = 1024 * 1024
EXPECTED_FILES = frozenset({"qualified_main_study.md", "verification_receipt.json"})


def _capture_zip(path: Path) -> bytes:
    """Capture one bounded, single-link regular ZIP generation from a descriptor."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 0 < before.st_size <= MAX_DOWNLOAD_ZIP_BYTES
        ):
            raise ValueError("qualified reporting ZIP is not a bounded single-link regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(MAX_DOWNLOAD_ZIP_BYTES + 1)
        after = os.fstat(descriptor)
        visible = os.stat(path, follow_symlinks=False)
        def identity(info: os.stat_result) -> tuple[int, ...]:
            return (
                info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            )
        if (
            len(raw) != before.st_size
            or identity(before) != identity(after)
            or identity(after) != identity(visible)
        ):
            raise ValueError("qualified reporting ZIP changed during capture")
        return raw
    finally:
        os.close(descriptor)


def verify_qualified_zip(*, zip_path: Path, repo_root: Path = ROOT) -> dict:
    """Fail closed on changed/ambiguous archives and on noncanonical source-bound pairs.

    Preflight checks the complete archive structure, members, CRCs and bounds.
    Only two trusted *fixed filenames* are ever materialized, in an automatically
    deleted private temporary directory; ZIP paths themselves are never extracted.
    """
    zip_path = Path(zip_path)
    metadata = os.stat(zip_path, follow_symlinks=False)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not 0 < metadata.st_size <= MAX_DOWNLOAD_ZIP_BYTES
    ):
        raise ValueError("qualified reporting ZIP exceeds the dedicated archive safety contract")
    inventory = audit_recovered_zip(zip_path)
    members = inventory["files"]
    if len(members) != 2 or {member["path"] for member in members} != EXPECTED_FILES:
        raise ValueError("qualified reporting ZIP must contain exactly the two published files")
    if any(not 0 < member["uncompressed_bytes"] <= MAX_MARKDOWN_BYTES for member in members):
        raise ValueError("qualified reporting ZIP member exceeds its bounded reporting contract")

    raw = _capture_zip(zip_path)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != inventory["archive_sha256_observed_now"] or len(raw) != inventory["archive_bytes"]:
        raise ValueError("qualified reporting ZIP changed after structural preflight")

    # Use the captured archive generation, not a second pathname open. Refuse
    # even innocuous extra directory entries: only the two published files exist.
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) != 2 or {entry.filename for entry in entries} != EXPECTED_FILES:
            raise ValueError("qualified reporting ZIP contains undisclosed ZIP members")
        contents = {}
        for member in members:
            with archive.open(member["path"]) as source:
                value = source.read(MAX_MARKDOWN_BYTES + 1)
            if (
                len(value) != member["uncompressed_bytes"]
                or hashlib.sha256(value).hexdigest() != member["sha256"]
            ):
                raise ValueError("qualified reporting ZIP member differs from structural preflight")
            contents[member["path"]] = value

    # Reuse the existing source-bound consumer verifier without asking users to
    # extract a potentially hostile ZIP. Temporary names are constants, not
    # archive-supplied paths, and the temporary directory is removed on exit.
    with tempfile.TemporaryDirectory(prefix="vera-qualified-zip-") as directory:
        root = Path(directory)
        for name in EXPECTED_FILES:
            (root / name).write_bytes(contents[name])
        verified = verify_distributed_artifact(
            report_path=root / "qualified_main_study.md",
            receipt_path=root / "verification_receipt.json",
            repo_root=repo_root,
        )
    if _capture_zip(zip_path) != raw:
        raise ValueError("qualified reporting ZIP changed during source-bound verification")
    return {
        **verified,
        "status": "downloaded_zip_matches_source_bound_qualified_reporting_pair",
        "downloaded_zip_sha256": digest,
        "downloaded_zip_bytes": len(raw),
        "zip_regular_member_count": 2,
        "independent_archive_custody_established": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = verify_qualified_zip(zip_path=args.zip, repo_root=args.repo_root)
    except (OSError, ValueError, UnicodeError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"qualified reporting ZIP verification blocked: {exc}\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
