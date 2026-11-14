"""Select complete ordinary pytest modules into deterministic offline CI shards.

Only test-module paths are partitioned; nothing is selected by research outcome.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARDS = 8
PATTERNS = ("test_*.py", "*_test.py")


def discover_modules(root: Path = ROOT) -> tuple[str, ...]:
    root = Path(root)
    tests = root / "tests"
    if tests.is_symlink() or not tests.is_dir():
        raise ValueError("offline test root must be a real tests/ directory")
    paths = set()
    for pattern in PATTERNS:
        for path in tests.rglob(pattern):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"offline test module must be a regular file: {path}")
            paths.add(path.relative_to(root).as_posix())
    if not paths:
        raise ValueError("offline test discovery returned no modules")
    return tuple(sorted(paths))


def select_shard(modules: tuple[str, ...], *, shard: int, shards: int = SHARDS) -> tuple[str, ...]:
    if type(shards) is not int or not 1 <= shards <= 64:
        raise ValueError("shards must be an integer between 1 and 64")
    if type(shard) is not int or not 0 <= shard < shards:
        raise ValueError("shard index outside declared matrix")
    if not modules or len(modules) != len(set(modules)):
        raise ValueError("offline test modules must be nonempty and unique")
    if any(type(path) is not str or not path.startswith("tests/") or
           not (Path(path).name.startswith("test_") or Path(path).name.endswith("_test.py")) or
           not path.endswith(".py") for path in modules):
        raise ValueError("unexpected offline test module path")
    selected = tuple(sorted(modules)[shard::shards])
    if not selected:
        raise ValueError("empty shard cannot prove full-suite coverage")
    return selected


def verify_partition(modules: tuple[str, ...], *, shards: int = SHARDS) -> None:
    grouped = [select_shard(modules, shard=i, shards=shards) for i in range(shards)]
    found = [path for group in grouped for path in group]
    if len(found) != len(modules) or sorted(found) != sorted(modules):
        raise ValueError("offline test partition has missing/duplicate modules")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards", type=int, default=SHARDS)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--shard", type=int)
    group.add_argument("--verify-partition", action="store_true")
    args = parser.parse_args()
    try:
        modules = discover_modules()
        verify_partition(modules, shards=args.shards)
        if args.verify_partition:
            print(f"VERA FULL CI MODULE PARTITION: PASS ({len(modules)} modules / {args.shards} shards)")
        else:
            for name in select_shard(modules, shard=args.shard, shards=args.shards):
                print(name)
    except ValueError as exc:
        parser.exit(1, f"VERA FULL CI MODULE PARTITION: FAIL: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
