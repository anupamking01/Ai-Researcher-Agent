"""Deterministic SHA-256 fingerprints for preserved research artifacts.

This utility makes it possible to bind an analysis result or manuscript table to
exact input bytes without modifying the underlying artifacts. It is offline and
uses only Python's standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = (
    REPO_ROOT / "outputs" / "main_study_runs.csv",
    REPO_ROOT / "outputs" / "posthoc_support_runs.csv",
)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of an existing regular file."""
    if not path.is_file():
        raise ValueError(f"research artifact is missing or not a file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(paths: list[Path], *, root: Path = REPO_ROOT) -> dict:
    """Build an order-independent manifest and aggregate digest.

    Paths are represented relative to ``root`` so the manifest is portable
    across clones. Duplicate paths are rejected because they can make provenance
    records ambiguous.
    """
    if not paths:
        raise ValueError("at least one research artifact is required")

    entries = []
    seen: set[str] = set()
    for path in paths:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError(f"artifact must be inside repository root: {path}") from exc
        if relative in seen:
            raise ValueError(f"duplicate research artifact: {relative}")
        seen.add(relative)
        entries.append(
            {
                "path": relative,
                "sha256": sha256_file(resolved),
                "bytes": resolved.stat().st_size,
            }
        )

    entries.sort(key=lambda item: item["path"])
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": 1,
        "algorithm": "sha256",
        "artifacts": entries,
        "aggregate_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="repository-relative artifacts")
    parser.add_argument("--output", type=Path, help="optional JSON manifest destination")
    args = parser.parse_args()

    paths = [REPO_ROOT / path for path in args.paths] if args.paths else list(DEFAULT_ARTIFACTS)
    manifest = build_manifest(paths)
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else REPO_ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
