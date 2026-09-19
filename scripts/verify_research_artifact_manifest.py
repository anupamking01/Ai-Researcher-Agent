"""Fail-closed verification for research-artifact fingerprint manifests.

Use this before re-running analysis or preparing manuscript tables to prove that
preserved inputs still match the exact bytes recorded by
``fingerprint_research_artifacts.py``. The verifier is offline and dependency-free.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.fingerprint_research_artifacts import REPO_ROOT, sha256_file


def verify_manifest(manifest: dict, *, root: Path = REPO_ROOT) -> list[dict]:
    """Verify manifest structure, repository confinement, size, and SHA-256.

    Returns the validated artifact entries. Any ambiguity or mismatch raises
    ``ValueError`` so downstream analysis can fail closed.
    """
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported research-artifact manifest schema")
    if manifest.get("algorithm") != "sha256":
        raise ValueError("unsupported research-artifact digest algorithm")

    entries = manifest.get("artifacts")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest must contain at least one artifact")

    root = root.resolve()
    validated: list[dict] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("artifact entry must be an object")
        relative = entry.get("path")
        expected_sha = entry.get("sha256")
        expected_bytes = entry.get("bytes")
        if not isinstance(relative, str) or not relative:
            raise ValueError("artifact path must be a non-empty string")
        if relative in seen:
            raise ValueError(f"duplicate research artifact: {relative}")
        seen.add(relative)

        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"artifact escapes repository root: {relative}") from exc
        if not candidate.is_file():
            raise ValueError(f"research artifact is missing or not a file: {relative}")
        if not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise ValueError(f"invalid byte count for artifact: {relative}")
        if candidate.stat().st_size != expected_bytes:
            raise ValueError(f"artifact byte-size mismatch: {relative}")
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise ValueError(f"invalid SHA-256 digest for artifact: {relative}")
        actual_sha = sha256_file(candidate)
        if actual_sha != expected_sha:
            raise ValueError(f"artifact SHA-256 mismatch: {relative}")
        validated.append({"path": relative, "sha256": expected_sha, "bytes": expected_bytes})

    canonical_entries = sorted(validated, key=lambda item: item["path"])
    canonical = json.dumps(canonical_entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    aggregate = hashlib.sha256(canonical).hexdigest()
    if manifest.get("aggregate_sha256") != aggregate:
        raise ValueError("aggregate research-artifact fingerprint mismatch")
    return canonical_entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON fingerprint manifest to verify")
    args = parser.parse_args()
    path = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = verify_manifest(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"RESEARCH ARTIFACT VERIFICATION: FAIL: {exc}") from exc
    print(f"RESEARCH ARTIFACT VERIFICATION: PASS ({len(entries)} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
