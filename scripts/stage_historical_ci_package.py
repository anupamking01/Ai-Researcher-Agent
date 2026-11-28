"""Stage the separately retained original CI package; do not certify replay."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

PACKAGE_SIZE = 246104
PACKAGE_SHA256 = "13406729cbbdda8d4acf71885ac4acd9d50c65c8f58349f05bd3cc48c85673b1"
RECEIPT_SHA256 = "f2f678dc5e8baeed09b62c882d02cccf08374b70a3e53e65059561049e693a73"
INVENTORY_SIZE = 24830
INVENTORY_SHA256 = "52d74984e07d78b912e179bafc34d352895412f1aa74572da6d58e7e32596e16"
SUFFIX = "45526533438-1"
EARLY = ("vera-stdlib-evaluation.log", "vera-stdlib-evaluation-receipt.json")
PYTEST = ("vera-offline-tests.log", "vera-offline-test-receipt.json",
          "vera-offline-test-modules.txt")
AGGREGATE = ("vera-full-shard-replay.json",)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def expected_layout() -> dict:
    layout = {}
    for index in range(16):
        layout[f"vera-stdlib-evaluation-shard-{index}-{SUFFIX}"] = (
            Path("early") / f"shard-{index}", EARLY)
        layout[f"vera-offline-tests-shard-{index}-{SUFFIX}"] = (
            Path("pytest") / f"shard-{index}", PYTEST)
    layout[f"vera-full-shard-replay-{SUFFIX}"] = (Path("aggregate"), AGGREGATE)
    return layout


def require_members(bundle: ZipFile, names: set[str]) -> None:
    actual = bundle.namelist()
    if len(actual) != len(names) or set(actual) != names:
        raise ValueError("unexpected, missing or duplicate ZIP member")


def stage_package(package: Path, output: Path) -> None:
    # Pin the bounded outer bytes before interpreting any ZIP metadata.
    with package.open("rb") as stream:
        raw = stream.read(PACKAGE_SIZE + 1)
    if len(raw) != PACKAGE_SIZE or sha(raw) != PACKAGE_SHA256:
        raise ValueError("historical preservation package size or SHA-256 mismatch")
    files = {}
    layout = expected_layout()
    with ZipFile(io.BytesIO(raw)) as outer:
        receipt_raw = outer.read("external-archive-receipt.json")
        if sha(receipt_raw) != RECEIPT_SHA256:
            raise ValueError("external archive receipt SHA-256 mismatch")
        rows = json.loads(receipt_raw)["artifacts"]
        if len(rows) != len(layout) or {r["name"] for r in rows} != set(layout):
            raise ValueError("historical artifact inventory mismatch")
        if any(type(r["artifact_id"]) is not int or r["artifact_id"] <= 0 for r in rows):
            raise ValueError("invalid historical artifact ID")
        ids = {r["artifact_id"] for r in rows}
        if len(ids) != len(layout):
            raise ValueError("duplicate historical artifact ID")
        require_members(outer, {f"archives/{i}.zip" for i in ids} |
                        {"external-archive-receipt.json"})
        files[Path("external-archive-receipt.json")] = receipt_raw
        for row in rows:
            folder, names = layout[row["name"]]
            archive = outer.read(f'archives/{row["artifact_id"]}.zip')
            if (len(archive) != row["archive_bytes"] or
                    sha(archive) != row["provider_sha256"]):
                raise ValueError("original archive size or SHA-256 mismatch")
            files[Path("archives") / f'{row["artifact_id"]}.zip'] = archive
            with ZipFile(io.BytesIO(archive)) as inner:
                require_members(inner, set(names))
                for name in names:
                    data = inner.read(name)
                    if sha(data) != row["members"][name]:
                        raise ValueError("original member SHA-256 mismatch")
                    files[folder / name] = data
    _publish(files, output)


def stage_archives(archives_dir: Path, inventory: Path, output: Path) -> None:
    """Recover staging from original ID-named ZIPs, without the outer package."""
    with inventory.open("rb") as stream:
        raw = stream.read(INVENTORY_SIZE + 1)
    if len(raw) != INVENTORY_SIZE or sha(raw) != INVENTORY_SHA256:
        raise ValueError("historical provider inventory size or SHA-256 mismatch")
    snapshot = json.loads(raw)
    rows = snapshot["artifacts"]
    layout = expected_layout()
    if (snapshot["total_count"] != len(layout) or len(rows) != len(layout) or
            {r["name"] for r in rows} != set(layout)):
        raise ValueError("historical artifact inventory mismatch")
    ids = [r["id"] for r in rows]
    if any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("invalid or duplicate historical artifact ID")
    files = {Path("artifacts.json"): raw}
    for row in rows:
        filename = f'{row["id"]}.zip'
        size = row["size_in_bytes"]
        with (archives_dir / filename).open("rb") as stream:
            archive = stream.read(size + 1)
        if len(archive) != size or "sha256:" + sha(archive) != row["digest"]:
            raise ValueError(f"original archive size or SHA-256 mismatch: {filename}")
        files[Path("archives") / filename] = archive
        folder, names = layout[row["name"]]
        with ZipFile(io.BytesIO(archive)) as inner:
            require_members(inner, set(names))
            for name in names:
                # The pinned archive digest authenticates member bytes relative
                # to the saved inventory; ZipFile.read additionally checks CRC.
                files[folder / name] = inner.read(name)
    _publish(files, output)


def _publish(files: dict[Path, bytes], output: Path) -> None:
    # All checks precede publication. Only fixed paths are used, never ZIP paths.
    # Use a trusted private parent directory; partial outputs must not be reused.
    output.mkdir()
    for relative, data in files.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--package", type=Path)
    source.add_argument("--archives-dir", type=Path)
    parser.add_argument("--artifact-inventory", type=Path,
                        help="exact Git-preserved artifacts.json for --archives-dir")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if (args.archives_dir is None) != (args.artifact_inventory is None):
        parser.error("--archives-dir and --artifact-inventory must be supplied together")
    try:
        if args.package is not None:
            stage_package(args.package, args.output)
        else:
            stage_archives(args.archives_dir, args.artifact_inventory, args.output)
    except (OSError, ValueError, BadZipFile) as exc:
        parser.exit(1, f"Historical CI staging failed: {exc}\n")
    print("33 original archives matched and staged; exact-checkout replay not performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
