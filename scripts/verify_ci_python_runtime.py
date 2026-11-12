"""Fail closed when the actual offline-test interpreter drifts from CI's pin.

The workflow requests Python 3.11.17 on ubuntu-24.04 x86_64. The executable
running the test suite and its verification tools must independently match
that runtime before and after pytest, rather than trusting setup-python's
configuration or a syntactically valid receipt field alone.

This is a local interpreter identity check, not binary or runner attestation.
"""
from __future__ import annotations

import argparse
import platform
import struct
import sys

PINNED_VERSION = (3, 11, 17)
PINNED_VERSION_TEXT = ".".join(str(component) for component in PINNED_VERSION)
PINNED_IMPLEMENTATION = "cpython"
PINNED_PLATFORM = "linux"
PINNED_MACHINE = "x86_64"
PINNED_POINTER_BITS = 64


def verify_ci_python_runtime(
    *, version: tuple[int, int, int], releaselevel: str, serial: int,
    implementation: str, platform_name: str, machine: str, pointer_bits: int,
) -> str:
    """Validate the actual interpreter/ABI platform, without importing project code."""
    if (
        type(version) is not tuple or len(version) != 3
        or any(type(component) is not int for component in version)
        or version != PINNED_VERSION
        or releaselevel != "final" or type(serial) is not int or serial != 0
    ):
        raise ValueError(
            f"CI Python runtime version drift: expected final {PINNED_VERSION_TEXT}"
        )
    if implementation != PINNED_IMPLEMENTATION:
        raise ValueError("CI Python implementation drift: expected CPython")
    if platform_name != PINNED_PLATFORM or machine != PINNED_MACHINE:
        raise ValueError("CI Python host platform drift: expected Linux x86_64")
    if type(pointer_bits) is not int or pointer_bits != PINNED_POINTER_BITS:
        raise ValueError("CI Python ABI drift: expected 64-bit pointers")
    return f"CPython {PINNED_VERSION_TEXT} / Linux x86_64 / 64-bit"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("before-tests", "after-tests"), required=True)
    args = parser.parse_args()
    try:
        observed = verify_ci_python_runtime(
            version=tuple(sys.version_info[:3]),
            releaselevel=sys.version_info.releaselevel,
            serial=sys.version_info.serial,
            implementation=sys.implementation.name,
            platform_name=sys.platform,
            machine=platform.machine(),
            pointer_bits=struct.calcsize("P") * 8,
        )
    except ValueError as exc:
        parser.exit(1, f"VERA CI PYTHON RUNTIME ({args.phase}): FAIL: {exc}\n")
    print(f"VERA CI PYTHON RUNTIME ({args.phase}): PASS ({observed}; local runner only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
