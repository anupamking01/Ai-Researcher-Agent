"""Deterministic SHA-256 fingerprints for preserved research artifacts.

This utility makes it possible to bind an analysis result or manuscript table to
exact input bytes without modifying the underlying artifacts. It is offline and
uses only Python's standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = (
    REPO_ROOT / "outputs" / "main_study_runs.csv",
    REPO_ROOT / "outputs" / "posthoc_support_runs.csv",
)

_WINDOWS_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
_WINDOWS_FORBIDDEN_CHARS = frozenset('<>:"\\\\|?*')


def portable_manifest_path_identity(relative: str) -> str:
    """Conservatively identify paths that could alias on another filesystem.

    Research artifacts must remain distinguishable after checkout on platforms
    with case-insensitive or Unicode-normalizing names. Windows device names,
    alternate-data-stream separators, and invisible directional controls are
    rejected. This checks path portability, not independent scientific origin.
    """
    if not isinstance(relative, str) or not relative or relative.startswith("/"):
        raise ValueError(f"non-portable research artifact path: {relative!r}")
    normalized_parts = []
    for part in relative.split("/"):
        normalized = unicodedata.normalize("NFKC", part)
        if (
            part in {"", ".", ".."}
            or normalized in {"", ".", ".."}
            or normalized.endswith((" ", "."))
            or any(
                char in _WINDOWS_FORBIDDEN_CHARS
                or char == "/"
                or ord(char) < 32
                or ord(char) == 127
                or unicodedata.category(char) == "Cf"
                for char in normalized
            )
            or normalized.split(".", 1)[0].upper() in _WINDOWS_DEVICE_NAMES
        ):
            raise ValueError(f"non-portable research artifact path: {relative!r}")
        normalized_parts.append(normalized)
    return unicodedata.normalize("NFKC", "/".join(normalized_parts).casefold())


SUPPORTS_DESCRIPTOR_TRAVERSAL = (
    os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
)


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_fingerprint(
    descriptor: int, *, path: Path
) -> tuple[str, int, tuple[int, int, int, int, int]]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"research artifact must be a regular file: {path}")

    digest = hashlib.sha256()
    byte_count = 0
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        byte_count += len(chunk)

    after = os.fstat(descriptor)
    if _identity(before) != _identity(after) or byte_count != after.st_size:
        raise ValueError(f"research artifact changed while it was fingerprinted: {path}")
    return digest.hexdigest(), after.st_size, _identity(after)


def _fingerprint_with_directory_descriptors(path: Path) -> tuple[str, int, tuple[int, int]]:
    """Traverse from the filesystem root without following any path component."""
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    file_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptors: list[int] = []
    directory_bindings: list[tuple[int, str, int]] = []
    try:
        root_descriptor = os.open(path.anchor, directory_flags)
        descriptors.append(root_descriptor)
        parent_descriptor = root_descriptor
        for component in path.parts[1:-1]:
            child_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=parent_descriptor,
            )
            descriptors.append(child_descriptor)
            if not stat.S_ISDIR(os.fstat(child_descriptor).st_mode):
                raise ValueError(
                    f"research artifact must be a regular file: {path}"
                )
            directory_bindings.append(
                (parent_descriptor, component, child_descriptor)
            )
            parent_descriptor = child_descriptor

        leaf = path.parts[-1]
        file_descriptor = os.open(leaf, file_flags, dir_fd=parent_descriptor)
        descriptors.append(file_descriptor)
        digest, byte_count, file_identity = _read_fingerprint(
            file_descriptor,
            path=path,
        )

        current_file = os.stat(
            leaf,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(current_file.st_mode) or _identity(
            current_file
        ) != file_identity:
            raise ValueError(
                f"research artifact changed while it was fingerprinted: {path}"
            )
        for parent, name, child in reversed(directory_bindings):
            current_directory = os.stat(
                name,
                dir_fd=parent,
                follow_symlinks=False,
            )
            bound_directory = os.fstat(child)
            if (
                not stat.S_ISDIR(current_directory.st_mode)
                or (current_directory.st_dev, current_directory.st_ino)
                != (bound_directory.st_dev, bound_directory.st_ino)
            ):
                raise ValueError(
                    f"research artifact changed while it was fingerprinted: {path}"
                )
        return digest, byte_count, file_identity[:2]
    except FileNotFoundError as exc:
        raise ValueError(f"research artifact is missing or not a file: {path}") from exc
    except OSError as exc:
        raise ValueError(f"research artifact must be a regular file: {path}") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _fingerprint_portably(path: Path) -> tuple[str, int, tuple[int, int]]:
    """Portable fallback that rejects symlink components and rechecks identities."""
    components: list[tuple[Path, tuple[int, int, int, int, int], bool]] = []
    current = Path(path.anchor)
    try:
        for component in path.parts[1:]:
            current = current / component
            metadata = os.stat(current, follow_symlinks=False)
            is_leaf = current == path
            expected_type = stat.S_ISREG if is_leaf else stat.S_ISDIR
            if not expected_type(metadata.st_mode):
                raise ValueError(f"research artifact must be a regular file: {path}")
            components.append((current, _identity(metadata), is_leaf))
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0),
        )
    except FileNotFoundError as exc:
        raise ValueError(f"research artifact is missing or not a file: {path}") from exc
    except OSError as exc:
        raise ValueError(f"research artifact must be a regular file: {path}") from exc
    try:
        digest, byte_count, file_identity = _read_fingerprint(descriptor, path=path)
        if not components or components[-1][1] != file_identity:
            raise ValueError(
                f"research artifact changed while it was fingerprinted: {path}"
            )
        for component, identity, is_leaf in components:
            current_metadata = os.stat(component, follow_symlinks=False)
            expected_type = stat.S_ISREG if is_leaf else stat.S_ISDIR
            if (
                not expected_type(current_metadata.st_mode)
                or _identity(current_metadata) != identity
            ):
                raise ValueError(
                    f"research artifact changed while it was fingerprinted: {path}"
                )
        return digest, byte_count, file_identity[:2]
    except OSError as exc:
        raise ValueError(
            f"research artifact changed while it was fingerprinted: {path}"
        ) from exc
    finally:
        os.close(descriptor)


def fingerprint_regular_file_with_identity(
    path: Path,
) -> tuple[str, int, tuple[int, int]]:
    """Return stable bytes and physical file identity from one checked descriptor.

    The filesystem (device, inode) pair is captured during hashing, not from a
    separate path lookup after the file could have been replaced. It identifies
    hard-linked aliases on filesystems exposing meaningful inode identities.
    """
    path = Path(os.path.abspath(path))
    if SUPPORTS_DESCRIPTOR_TRAVERSAL and path.anchor:
        return _fingerprint_with_directory_descriptors(path)
    return _fingerprint_portably(path)


def fingerprint_regular_file(path: Path) -> tuple[str, int]:
    """Return a digest and size from one stable, non-symlink file snapshot."""
    digest, byte_count, _ = fingerprint_regular_file_with_identity(path)
    return digest, byte_count


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one stable, existing regular file."""
    digest, _ = fingerprint_regular_file(path)
    return digest


def build_manifest(paths: list[Path], *, root: Path = REPO_ROOT) -> dict:
    """Build an order-independent manifest and aggregate digest.

    Paths are represented relative to ``root`` so the manifest is portable
    across clones. Duplicate paths are rejected because they can make provenance
    records ambiguous.
    """
    if not paths:
        raise ValueError("at least one research artifact is required")

    root = Path(root).resolve()
    entries = []
    seen: set[str] = set()
    portable_seen: dict[str, str] = {}
    physical_seen: dict[tuple[int, int], str] = {}
    for path in paths:
        candidate = Path(os.path.abspath(path))
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"artifact must be inside repository root: {path}") from exc
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
        digest, byte_count, physical_identity = fingerprint_regular_file_with_identity(
            candidate
        )
        if physical_identity in physical_seen:
            raise ValueError(
                "research artifact hard-link alias: "
                f"{physical_seen[physical_identity]!r} and {relative!r}"
            )
        physical_seen[physical_identity] = relative
        entries.append(
            {
                "path": relative,
                "sha256": digest,
                "bytes": byte_count,
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
