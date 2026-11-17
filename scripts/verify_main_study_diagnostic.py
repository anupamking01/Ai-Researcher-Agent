"""Read-only consistency verification for locally captured VERA diagnostics.

This checks retained CSV scientific validity, declared byte fingerprints, and
local code/config versions. It does NOT establish external artifact provenance,
recompute inference by default, authenticate source files, or validate human ratings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from contextlib import ExitStack, contextmanager, redirect_stdout
from pathlib import Path

from scripts import analyze_main_study as frozen
from scripts import analyze_main_study_with_preflight as diagnostic
from scripts import validate_main_study_inputs as preflight


MAX_MANIFEST_BYTES = 64 * 1024
ARTIFACTS = (
    diagnostic.DIAGNOSTIC_MAIN_INPUT,
    diagnostic.DIAGNOSTIC_SUPPORT_INPUT,
    diagnostic.DIAGNOSTIC_JSON,
    diagnostic.DIAGNOSTIC_MD,
)
from scripts import validate_numeric_inputs as numeric


SOURCES = {
    "scripts/analyze_main_study.py": Path(frozen.__file__),
    "scripts/analyze_main_study_with_preflight.py": Path(diagnostic.__file__),
    "scripts/validate_main_study_inputs.py": Path(preflight.__file__),
    "scripts/validate_numeric_inputs.py": Path(numeric.__file__),
}


def _member_generation(st: os.stat_result) -> tuple:
    """Identity and write generation of one retained bundle member."""
    return (
        st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size,
        st.st_mtime_ns, st.st_ctime_ns,
    )


def _directory_identity(st: os.stat_result) -> tuple:
    """Stable directory identity; unrelated sibling writes need not fail."""
    return st.st_dev, st.st_ino, st.st_mode


def _require_exact_bundle_inventory(directory_fd: int, required: set[str], failure: str) -> None:
    """Fail closed on a fixed bundle inventory without unbounded os.listdir().

    Accept at most the five declared names. Encountering an undeclared entry
    stops enumeration immediately rather than materializing an attacker-sized
    directory listing in memory. This is an observed inventory check, not an
    atomic filesystem snapshot.
    """
    seen: set[str] = set()
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            if entry.name not in required or entry.name in seen:
                raise ValueError(failure)
            seen.add(entry.name)
    if seen != required:
        raise ValueError(failure)


@contextmanager
def _bound_diagnostic_bundle(directory: Path):
    """Pin all five members and each ancestor for the entire verification.

    This checks local pathname/file continuity only. It is not an atomic
    snapshot or independent historical custody authentication.
    """
    directory = Path(directory)
    if ".." in directory.parts:
        raise ValueError("diagnostic bundle path must not contain parent traversal")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("diagnostic bundle requires no-follow directory opens")
    absolute = Path(os.path.abspath(directory))
    flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
             | getattr(os, "O_CLOEXEC", 0))
    required = set(ARTIFACTS) | {diagnostic.DIAGNOSTIC_MANIFEST}
    try:
        with ExitStack() as stack:
            parent_fd = os.open(absolute.anchor, flags)
            stack.callback(os.close, parent_fd)
            chain = []
            for component in absolute.parts[1:]:
                child_fd = os.open(component, flags, dir_fd=parent_fd)
                stack.callback(os.close, child_fd)
                named = os.stat(
                    component, dir_fd=parent_fd, follow_symlinks=False
                )
                if _directory_identity(named) != _directory_identity(
                    os.fstat(child_fd)
                ):
                    raise ValueError(
                        "diagnostic bundle ancestor changed before verification"
                    )
                chain.append((parent_fd, component, child_fd))
                parent_fd = child_fd

            _require_exact_bundle_inventory(
                parent_fd, required, "diagnostic bundle file set mismatch"
            )
            pinned = {}
            for name in sorted(required):
                st = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if stat.S_ISLNK(st.st_mode):
                    raise ValueError(f"diagnostic file is a symlink: {name}")
                if not stat.S_ISREG(st.st_mode):
                    raise ValueError(f"diagnostic file type invalid: {name}")
                if st.st_nlink != 1:
                    raise ValueError(f"diagnostic bundle member is hardlinked: {name}")
                pinned[name] = _member_generation(st)

            yield parent_fd, pinned

            _require_exact_bundle_inventory(
                parent_fd, required, "diagnostic bundle file set changed during verification"
            )
            for name, original in pinned.items():
                try:
                    observed = os.stat(
                        name, dir_fd=parent_fd, follow_symlinks=False
                    )
                except OSError as exc:
                    raise ValueError(
                        f"diagnostic bundle member changed during verification: {name}"
                    ) from exc
                if _member_generation(observed) != original:
                    raise ValueError(
                        f"diagnostic bundle member changed during verification: {name}"
                    )
            for holder_fd, component, child_fd in chain:
                try:
                    visible = os.stat(
                        component, dir_fd=holder_fd, follow_symlinks=False
                    )
                except OSError as exc:
                    raise ValueError(
                        "diagnostic bundle ancestor changed during verification"
                    ) from exc
                if _directory_identity(visible) != _directory_identity(
                    os.fstat(child_fd)
                ):
                    raise ValueError(
                        "diagnostic bundle ancestor changed during verification"
                    )
    except OSError as exc:
        raise ValueError("diagnostic bundle cannot be opened safely") from exc


def _read_regular(path: Path, *, limit: int, directory_fd: int | None = None,
                  expected_generation: tuple | None = None) -> bytes:
    # Bundle members are opened relative to the held directory, not via the
    # mutable caller pathname. Source-code files retain their existing reads.
    target = path if directory_fd is None else path.name
    options = {} if directory_fd is None else {"dir_fd": directory_fd}
    before = os.stat(target, follow_symlinks=False, **options)
    if stat.S_ISLNK(before.st_mode):
        raise ValueError(f"diagnostic file is a symlink: {path.name}")
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
        raise ValueError(f"diagnostic file type/size invalid: {path.name}")
    if before.st_nlink != 1:
        raise ValueError(f"diagnostic file is hardlinked: {path.name}")
    if (expected_generation is not None
            and _member_generation(before) != expected_generation):
        raise ValueError(f"diagnostic bundle member changed before read: {path.name}")
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(target, flags, **options)
    try:
        opened = os.fstat(fd)
        raw = bytearray()
        while True:
            block = os.read(fd, min(1024 * 1024, limit + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
            if len(raw) > limit:
                raise ValueError(f"diagnostic file exceeds size limit: {path.name}")
        after = os.fstat(fd)
        named = os.stat(target, follow_symlinks=False, **options)
        if (
            len(raw) != opened.st_size
            or _member_generation(before) != _member_generation(opened)
            or _member_generation(before) != _member_generation(after)
            or _member_generation(after) != _member_generation(named)
            or (expected_generation is not None
                and _member_generation(after) != expected_generation)
        ):
            raise ValueError(f"diagnostic file changed during verification: {path.name}")
        return bytes(raw)
    finally:
        os.close(fd)


@contextmanager
def _bound_diagnostic_sources():
    """Retain exact source file and ancestor identities across verification.

    A source digest obtained through a symlinked or replaced directory does
    not establish which local code checkout was examined. This still does
    not independently authenticate the checkout or loaded Python bytecode.
    """
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("diagnostic source requires no-follow directory opens")
    flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
             | getattr(os, "O_CLOEXEC", 0))
    try:
        with ExitStack() as stack:
            pinned = []
            fingerprints = {}
            for name, source_path in sorted(SOURCES.items()):
                path = Path(source_path)
                if ".." in path.parts:
                    raise ValueError("diagnostic source path contains parent traversal")
                absolute = Path(os.path.abspath(path))
                parent_fd = os.open(absolute.anchor, flags)
                stack.callback(os.close, parent_fd)
                ancestors = []
                for component in absolute.parts[1:-1]:
                    child_fd = os.open(component, flags, dir_fd=parent_fd)
                    stack.callback(os.close, child_fd)
                    visible = os.stat(
                        component, dir_fd=parent_fd, follow_symlinks=False
                    )
                    if _directory_identity(visible) != _directory_identity(
                        os.fstat(child_fd)
                    ):
                        raise ValueError(
                            "diagnostic source ancestor changed before verification"
                        )
                    ancestors.append((parent_fd, component, child_fd))
                    parent_fd = child_fd
                before = os.stat(
                    absolute.name, dir_fd=parent_fd, follow_symlinks=False
                )
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError(f"diagnostic source is not regular: {name}")
                if before.st_nlink != 1:
                    raise ValueError(f"diagnostic source is hardlinked: {name}")
                generation = _member_generation(before)
                raw = _read_regular(
                    absolute, limit=1024 * 1024, directory_fd=parent_fd,
                    expected_generation=generation,
                )
                fingerprints[name] = _fingerprint(raw)
                pinned.append((name, absolute.name, parent_fd, generation, ancestors))

            yield fingerprints

            for name, basename, parent_fd, generation, ancestors in pinned:
                try:
                    visible = os.stat(
                        basename, dir_fd=parent_fd, follow_symlinks=False
                    )
                except OSError as exc:
                    raise ValueError(
                        f"diagnostic source changed during verification: {name}"
                    ) from exc
                if _member_generation(visible) != generation:
                    raise ValueError(
                        f"diagnostic source changed during verification: {name}"
                    )
                for holder_fd, component, child_fd in ancestors:
                    try:
                        directory = os.stat(
                            component, dir_fd=holder_fd, follow_symlinks=False
                        )
                    except OSError as exc:
                        raise ValueError(
                            "diagnostic source ancestor changed during verification"
                        ) from exc
                    if _directory_identity(directory) != _directory_identity(
                        os.fstat(child_fd)
                    ):
                        raise ValueError(
                            "diagnostic source ancestor changed during verification"
                        )
    except OSError as exc:
        raise ValueError("diagnostic source cannot be opened safely") from exc


def _unique_pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate diagnostic manifest key: {name}")
        result[name] = value
    return result


def _fingerprint(raw: bytes) -> dict:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _check_fingerprint_table(table: object, names, *, kind: str) -> None:
    """Require exact JSON types, not Python's numerically equal float/int values."""
    if type(table) is not dict or set(table) != set(names):
        raise ValueError(f"diagnostic {kind} fingerprint schema mismatch")
    for value in table.values():
        if (
            type(value) is not dict
            or set(value) != {"bytes", "sha256"}
            or type(value["bytes"]) is not int
            or value["bytes"] <= 0
            or type(value["sha256"]) is not str
        ):
            raise ValueError(f"diagnostic {kind} fingerprint schema mismatch")



def _verify_recomputed_inference(
    treatment_rows: list[dict[str, str]],
    evaluator_rows: list[dict[str, str]],
    retained: dict[str, bytes],
) -> None:
    """Compare both archived outputs to offline inference from retained rows.

    This is an opt-in local consistency check, not a second independent
    statistical implementation or authentication of original input sources.
    The historical analyzer is executed without editing its pinned source,
    with output paths confined to a private temporary directory. Its global
    reader/output bindings are restored even when recomputation fails.
    Do not invoke concurrently in a shared Python process.
    """
    main_reference = Path(frozen.MAIN_CSV)
    support_reference = Path(frozen.SUPPORT_CSV)
    if main_reference == support_reference:
        raise ValueError("diagnostic recomputation input references must be distinct")

    original_reader = frozen._read_csv
    original_json, original_md = frozen.OUT_JSON, frozen.OUT_MD

    def retained_reader(path: Path) -> list[dict[str, str]]:
        reference = Path(path)
        if reference == main_reference:
            return [dict(row) for row in treatment_rows]
        if reference == support_reference:
            return [dict(row) for row in evaluator_rows]
        raise ValueError(f"unexpected diagnostic recomputation input: {reference}")

    with tempfile.TemporaryDirectory(prefix=".vera-diagnostic-recompute-") as scratch:
        root = Path(scratch)
        recomputed_paths = {
            diagnostic.DIAGNOSTIC_JSON: root / diagnostic.DIAGNOSTIC_JSON,
            diagnostic.DIAGNOSTIC_MD: root / diagnostic.DIAGNOSTIC_MD,
        }
        try:
            frozen._read_csv = retained_reader
            frozen.OUT_JSON = recomputed_paths[diagnostic.DIAGNOSTIC_JSON]
            frozen.OUT_MD = recomputed_paths[diagnostic.DIAGNOSTIC_MD]
            # The frozen analyzer emits its complete result payload. A
            # StringIO sink retains that potentially large payload in memory
            # despite it not being used by the byte-consistency check.
            # Discard stdout through a real file descriptor instead.
            with open(os.devnull, "w", encoding="utf-8") as discarded_stdout:
                with redirect_stdout(discarded_stdout):
                    status = frozen.main()
        finally:
            frozen._read_csv = original_reader
            frozen.OUT_JSON, frozen.OUT_MD = original_json, original_md

        if status != 0:
            raise ValueError("diagnostic offline inference recomputation failed")
        for name, path in recomputed_paths.items():
            regenerated = _read_regular(
                path, limit=diagnostic.DIAGNOSTIC_MAX_FILE_BYTES
            )
            if regenerated != retained[name]:
                raise ValueError(f"diagnostic recomputed inference byte mismatch: {name}")


def verify_diagnostic_bundle(
    directory: Path, *, recompute: bool = False,
    expected_manifest_sha256: str | None = None,
) -> dict:
    """Optionally bind a diagnostic receipt to a separately retained digest.

    The caller is responsible for establishing that the supplied pin predates
    any potential modification. An arbitrary locally computed pin is not
    independent archive custody.
    """
    if expected_manifest_sha256 is not None and (
        type(expected_manifest_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256) is None
    ):
        raise ValueError("expected diagnostic manifest SHA-256 must be 64 lowercase hex digits")
    directory = Path(directory)
    with _bound_diagnostic_sources() as source_fingerprints:
        with _bound_diagnostic_bundle(directory) as (bundle_fd, pinned):
            return _verify_bound_diagnostic_bundle(
                directory, bundle_fd, pinned, recompute=recompute,
                expected_manifest_sha256=expected_manifest_sha256,
                source_fingerprints=source_fingerprints,
            )


def _verify_bound_diagnostic_bundle(
    directory: Path, bundle_fd: int, pinned: dict, *, recompute: bool,
    expected_manifest_sha256: str | None,
    source_fingerprints: dict[str, dict],
) -> dict:
    raw_manifest = _read_regular(
        directory / diagnostic.DIAGNOSTIC_MANIFEST, limit=MAX_MANIFEST_BYTES,
        directory_fd=bundle_fd,
        expected_generation=pinned[diagnostic.DIAGNOSTIC_MANIFEST],
    )
    # Compare the exact captured manifest bytes *before* interpreting its
    # self-declared fingerprints. JSON reformatting is not equivalent custody.
    if (expected_manifest_sha256 is not None
            and hashlib.sha256(raw_manifest).hexdigest() != expected_manifest_sha256):
        raise ValueError("diagnostic manifest differs from supplied external SHA-256 pin")
    try:
        receipt = json.loads(
            raw_manifest.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite diagnostic manifest value: {value}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid diagnostic manifest JSON") from exc
    if not isinstance(receipt, dict) or set(receipt) != {
        "schema_version", "study_id", "scope", "sources",
        "analysis_config", "artifacts",
    }:
        raise ValueError("diagnostic manifest schema mismatch")
    if (
        type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 1
        or receipt["study_id"] != "budget-main-v1"
        or receipt["scope"] != "local_diagnostic_not_canonical"
    ):
        raise ValueError("diagnostic manifest study/scope mismatch")
    expected_config = {
        "bootstrap_draws": frozen.BOOTSTRAP_DRAWS,
        "bootstrap_seed": frozen.BOOTSTRAP_SEED,
        "expected_tasks": frozen.EXPECTED_TASKS,
    }
    config = receipt["analysis_config"]
    if (
        type(config) is not dict
        or set(config) != set(expected_config)
        or any(
            type(config[name]) is not int or config[name] != expected
            for name, expected in expected_config.items()
        )
    ):
        raise ValueError("diagnostic inference configuration differs from verifier")
    _check_fingerprint_table(receipt["sources"], SOURCES, kind="source")
    for name, path in SOURCES.items():
        if receipt["sources"][name] != source_fingerprints[name]:
            raise ValueError(f"diagnostic analysis source drift: {name}")

    _check_fingerprint_table(receipt["artifacts"], ARTIFACTS, kind="artifact")
    contents = {}
    for name in ARTIFACTS:
        limit = (
            diagnostic.MAX_DIAGNOSTIC_INPUT_BYTES
            if name in (diagnostic.DIAGNOSTIC_MAIN_INPUT, diagnostic.DIAGNOSTIC_SUPPORT_INPUT)
            else diagnostic.DIAGNOSTIC_MAX_FILE_BYTES
        )
        raw = _read_regular(
            directory / name, limit=limit, directory_fd=bundle_fd,
            expected_generation=pinned[name],
        )
        if receipt["artifacts"][name] != _fingerprint(raw):
            raise ValueError(f"diagnostic retained artifact byte mismatch: {name}")
        contents[name] = raw

    # Verify precisely the input bytes fingerprinted above, not a mutable
    # second read from a directory that can change during validation.
    with tempfile.TemporaryDirectory(prefix=".vera-verify-diagnostic-") as scratch:
        main = Path(scratch) / diagnostic.DIAGNOSTIC_MAIN_INPUT
        support = Path(scratch) / diagnostic.DIAGNOSTIC_SUPPORT_INPUT
        main.write_bytes(contents[diagnostic.DIAGNOSTIC_MAIN_INPUT])
        support.write_bytes(contents[diagnostic.DIAGNOSTIC_SUPPORT_INPUT])
        treatment = preflight.read_csv_rows(main)
        evaluator = preflight.read_csv_rows(support)
        preflight.validate_rows(treatment, evaluator, require_canonical_matrix=True)
    if recompute:
        _verify_recomputed_inference(treatment, evaluator, contents)
    result = {
        "status": "verified_local_diagnostic_bytes_not_canonical_provenance",
        "study_id": "budget-main-v1",
        "retained_input_cells": len(treatment),
        "files_verified": len(ARTIFACTS),
        "supplied_manifest_pin_matched": expected_manifest_sha256 is not None,
    }
    if recompute:
        result["offline_inference_recomputed"] = True
    return result


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Verify locally retained VERA diagnostic inputs and output bytes"
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--expected-manifest-sha256",
        help="optional previously and independently retained SHA-256 of exact manifest bytes",
    )
    parser.add_argument(
        "--recompute", action="store_true",
        help="also regenerate local inference offline from retained CSV rows and compare exact output bytes",
    )
    args = parser.parse_args()
    print(json.dumps(verify_diagnostic_bundle(
        args.directory, recompute=args.recompute,
        expected_manifest_sha256=args.expected_manifest_sha256,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
