"""Fail-closed verification for research-artifact fingerprint manifests.

Use this before re-running analysis or preparing manuscript tables to prove that
preserved inputs still match the exact bytes recorded by
``fingerprint_research_artifacts.py``. The verifier is offline and dependency-free.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON fingerprint manifest to verify")
    args = parser.parse_args()
    path = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    try:
        payload = parse_manifest_json(path.read_text(encoding="utf-8"))
        entries = verify_manifest(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"RESEARCH ARTIFACT VERIFICATION: FAIL: {exc}") from exc
    print(f"RESEARCH ARTIFACT VERIFICATION: PASS ({len(entries)} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
