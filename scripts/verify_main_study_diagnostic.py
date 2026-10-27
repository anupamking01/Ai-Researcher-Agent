"""Read-only consistency verification for locally captured VERA diagnostics.

This checks retained CSV scientific validity, declared byte fingerprints, and
local code/config versions. It does NOT establish external artifact provenance,
recompute inference, authenticate source files, or validate human ratings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
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


def _read_regular(path: Path, *, limit: int) -> bytes:
    if path.is_symlink():
        raise ValueError(f"diagnostic file is a symlink: {path.name}")
    before = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
        raise ValueError(f"diagnostic file type/size invalid: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
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
        named = os.stat(path, follow_symlinks=False)

        def identity(value):
            return (
                value.st_dev, value.st_ino, value.st_mode, value.st_size,
                value.st_mtime_ns, value.st_ctime_ns,
            )

        if (
            len(raw) != opened.st_size
            or identity(before) != identity(opened)
            or identity(before) != identity(after)
            or identity(after) != identity(named)
        ):
            raise ValueError(f"diagnostic file changed during verification: {path.name}")
        return bytes(raw)
    finally:
        os.close(fd)


def _unique_pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate diagnostic manifest key: {name}")
        result[name] = value
    return result


def _fingerprint(raw: bytes) -> dict:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def verify_diagnostic_bundle(directory: Path) -> dict:
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("diagnostic directory must exist and not be a symlink")
    names = {entry.name for entry in directory.iterdir()}
    required = set(ARTIFACTS) | {diagnostic.DIAGNOSTIC_MANIFEST}
    if names != required:
        raise ValueError(f"diagnostic bundle file set mismatch: {sorted(names ^ required)}")

    raw_manifest = _read_regular(
        directory / diagnostic.DIAGNOSTIC_MANIFEST, limit=MAX_MANIFEST_BYTES
    )
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
    if receipt["analysis_config"] != expected_config:
        raise ValueError("diagnostic inference configuration differs from verifier")
    if not isinstance(receipt["sources"], dict) or set(receipt["sources"]) != set(SOURCES):
        raise ValueError("diagnostic source fingerprint schema mismatch")
    for name, path in SOURCES.items():
        if receipt["sources"][name] != _fingerprint(_read_regular(path, limit=1024 * 1024)):
            raise ValueError(f"diagnostic analysis source drift: {name}")

    if not isinstance(receipt["artifacts"], dict) or set(receipt["artifacts"]) != set(ARTIFACTS):
        raise ValueError("diagnostic artifact fingerprint schema mismatch")
    contents = {}
    for name in ARTIFACTS:
        limit = (
            diagnostic.MAX_DIAGNOSTIC_INPUT_BYTES
            if name in (diagnostic.DIAGNOSTIC_MAIN_INPUT, diagnostic.DIAGNOSTIC_SUPPORT_INPUT)
            else diagnostic.DIAGNOSTIC_MAX_FILE_BYTES
        )
        raw = _read_regular(directory / name, limit=limit)
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
    return {
        "status": "verified_local_diagnostic_bytes_not_canonical_provenance",
        "study_id": "budget-main-v1",
        "retained_input_cells": len(treatment),
        "files_verified": len(ARTIFACTS),
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Verify locally retained VERA diagnostic inputs and output bytes"
    )
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_diagnostic_bundle(args.directory), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
