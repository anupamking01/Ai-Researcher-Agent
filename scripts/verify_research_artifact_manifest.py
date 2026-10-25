"""Fail-closed verification for research-artifact fingerprint manifests.

Use this before re-running analysis or preparing manuscript tables to prove that
preserved inputs still match the exact bytes recorded by
``fingerprint_research_artifacts.py``. The verifier is offline and dependency-free.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from pathlib import PurePosixPath

from scripts.fingerprint_research_artifacts import (
    REPO_ROOT,
    fingerprint_regular_file_with_identity,
    portable_manifest_path_identity,
    require_manifest_capture_coherence,
)


ROOT_FIELDS = {"schema_version", "algorithm", "artifacts", "aggregate_sha256"}
ARTIFACT_FIELDS = {"path", "sha256", "bytes"}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")



# Bound the metadata JSON read, not the size of the research artifacts it names.
# This permits tens of thousands of inputs while avoiding unbounded memory use.
MAX_MANIFEST_BYTES = 16 * 1024 * 1024


def _read_regular_manifest_bytes(path: Path) -> bytes:
    """Capture JSON from one checked regular-file descriptor, never Path.read_bytes.

    In particular, opening a substituted FIFO nonblocking avoids an indefinite
    read; no-follow rejects leaf symlinks where supported. The surrounding
    before/after fingerprints also bind pathname identity and source coherence.
    """
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError("manifest capture requires a regular file") from exc
    try:
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("manifest capture requires a regular file")
            if before.st_size > MAX_MANIFEST_BYTES:
                raise ValueError("manifest exceeds the 16 MiB safety limit")

            parts = []
            total = 0
            while True:
                chunk = os.read(
                    descriptor, min(1024 * 1024, MAX_MANIFEST_BYTES - total + 1)
                )
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_MANIFEST_BYTES:
                    raise ValueError("manifest exceeds the 16 MiB safety limit")
                parts.append(chunk)
            after = os.fstat(descriptor)
            identity = lambda st: (
                st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns
            )
            if identity(before) != identity(after) or total != after.st_size:
                raise ValueError("manifest file changed during descriptor capture")
            return b"".join(parts)
        except OSError as exc:
            raise ValueError("manifest file changed during descriptor capture") from exc
    finally:
        os.close(descriptor)


def parse_manifest_json(content: str) -> object:
    """Parse JSON while rejecting duplicate fields at every object boundary."""
    def reject_duplicates(pairs):
        parsed = {}
        for key, value in pairs:
            if key in parsed:
                raise ValueError(f"duplicate JSON field: {key}")
            parsed[key] = value
        return parsed

    return json.loads(content, object_pairs_hook=reject_duplicates)


def verify_manifest(manifest: dict, *, root: Path = REPO_ROOT) -> list[dict]:
    """Verify manifest structure, repository confinement, size, and SHA-256.

    Returns the validated artifact entries. Any ambiguity or mismatch raises
    ``ValueError`` so downstream analysis can fail closed.
    """
    if not isinstance(manifest, dict) or set(manifest) != ROOT_FIELDS:
        raise ValueError("manifest must contain the exact root fields")
    if (
        type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
    ):
        raise ValueError("unsupported research-artifact manifest schema")
    if manifest.get("algorithm") != "sha256":
        raise ValueError("unsupported research-artifact digest algorithm")

    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest must contain at least one artifact")

    root = root.resolve()
    validated: list[dict] = []
    seen: set[str] = set()
    portable_seen: dict[str, str] = {}
    physical_seen: dict[tuple[int, int], str] = {}
    initial_identities: dict[str, tuple[int, int]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != ARTIFACT_FIELDS:
            raise ValueError("artifact entry must contain the exact fields")
        relative = entry.get("path")
        expected_sha = entry.get("sha256")
        expected_bytes = entry.get("bytes")
        if not isinstance(relative, str) or not relative:
            raise ValueError("artifact path must be a non-empty string")
        relative_path = PurePosixPath(relative)
        if "\\" in relative or re.match(r"^[A-Za-z]:", relative):
            raise ValueError(f"artifact path must be canonical: {relative}")
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"artifact escapes repository root: {relative}")
        if (
            relative_path.as_posix() != relative
            or any(part in {"", ".", ".."} for part in relative_path.parts)
        ):
            raise ValueError(f"artifact path must be canonical: {relative}")
        if relative in seen:
            raise ValueError(f"duplicate research artifact: {relative}")
        seen.add(relative)
        portable_key = portable_manifest_path_identity(relative)
        if portable_key in portable_seen:
            raise ValueError(
                "portable research artifact path collision: "
                f"{portable_seen[portable_key]!r} and {relative!r}"
            )
        portable_seen[portable_key] = relative

        candidate = root.joinpath(*relative_path.parts)
        if type(expected_bytes) is not int or expected_bytes < 0:
            raise ValueError(f"invalid byte count for artifact: {relative}")
        if not isinstance(expected_sha, str) or not SHA256_PATTERN.fullmatch(
            expected_sha
        ):
            raise ValueError(f"invalid SHA-256 digest for artifact: {relative}")
        actual_sha, actual_bytes, physical_identity = (
            fingerprint_regular_file_with_identity(candidate)
        )
        if actual_bytes != expected_bytes:
            raise ValueError(f"artifact byte-size mismatch: {relative}")
        if actual_sha != expected_sha:
            raise ValueError(f"artifact SHA-256 mismatch: {relative}")
        if physical_identity in physical_seen:
            raise ValueError(
                "research artifact hard-link alias: "
                f"{physical_seen[physical_identity]!r} and {relative!r}"
            )
        physical_seen[physical_identity] = relative
        initial_identities[relative] = physical_identity
        validated.append({"path": relative, "sha256": expected_sha, "bytes": expected_bytes})

    canonical_entries = sorted(validated, key=lambda item: item["path"])
    canonical = json.dumps(canonical_entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    aggregate = hashlib.sha256(canonical).hexdigest()
    expected_aggregate = manifest.get("aggregate_sha256")
    if not isinstance(expected_aggregate, str) or not SHA256_PATTERN.fullmatch(
        expected_aggregate
    ):
        raise ValueError("invalid aggregate research-artifact fingerprint")
    if expected_aggregate != aggregate:
        raise ValueError("aggregate research-artifact fingerprint mismatch")
    require_manifest_capture_coherence(
        canonical_entries, root=root, identities=initial_identities
    )
    return canonical_entries


def verify_manifest_file(
    manifest_path: Path,
    *,
    root: Path = REPO_ROOT,
    expected_manifest_sha256: str | None = None,
) -> list[dict]:
    """Verify source files against a stable manifest, optionally externally pinned.

    Without an independently retained expected manifest SHA-256, an adversary
    who replaces both artifact bytes and manifest can recompute every in-band
    hash and still pass. The opt-in pin binds the manifest's exact raw bytes to
    a separately retained reference. Neither check proves original authorship,
    nor provides an atomic cross-file snapshot.
    """
    if expected_manifest_sha256 is not None and (
        not isinstance(expected_manifest_sha256, str)
        or not SHA256_PATTERN.fullmatch(expected_manifest_sha256)
    ):
        raise ValueError("expected manifest SHA-256 must be 64 lowercase hex digits")

    path = Path(manifest_path)
    first_sha, first_size, first_identity = (
        fingerprint_regular_file_with_identity(path)
    )
    if first_size > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds the 16 MiB safety limit")
    raw = _read_regular_manifest_bytes(path)
    observed_sha = hashlib.sha256(raw).hexdigest()
    if len(raw) != first_size or observed_sha != first_sha:
        raise ValueError("manifest file changed during verification")

    # Bind parsed content to the same checked physical file that was hashed.
    # A byte-identical inode replacement is not silently accepted.
    final_sha, final_size, final_identity = (
        fingerprint_regular_file_with_identity(path)
    )
    if (first_sha, first_size, first_identity) != (
        final_sha, final_size, final_identity
    ):
        raise ValueError("manifest file changed during verification")

    if (
        expected_manifest_sha256 is not None
        and observed_sha != expected_manifest_sha256
    ):
        raise ValueError("external manifest SHA-256 pin mismatch")

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("manifest file is not valid UTF-8") from exc
    entries = verify_manifest(parse_manifest_json(content), root=root)
    # Source verification can take much longer than parsing the manifest.
    # Keep the exact manifest bytes and physical identity pinned through the
    # entire artifact scan, not only through the initial manifest capture.
    try:
        closing_sha, closing_size, closing_identity = (
            fingerprint_regular_file_with_identity(path)
        )
    except (ValueError, OSError) as exc:
        raise ValueError(
            "manifest file changed during artifact verification"
        ) from exc
    if (closing_sha, closing_size, closing_identity) != (
        first_sha, first_size, first_identity
    ):
        raise ValueError("manifest file changed during artifact verification")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON fingerprint manifest to verify")
    parser.add_argument(
        "--expected-manifest-sha256",
        help="independently retained lowercase SHA-256 of exact manifest file bytes",
    )
    args = parser.parse_args()
    path = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    try:
        entries = verify_manifest_file(
            path, expected_manifest_sha256=args.expected_manifest_sha256
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"RESEARCH ARTIFACT VERIFICATION: FAIL: {exc}") from exc
    print(f"RESEARCH ARTIFACT VERIFICATION: PASS ({len(entries)} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
