"""Fail closed when CI's *installed* Python dependencies differ from pinned inputs.

requirements.txt and requirements-ci.lock are source pins, not an observation
of the runner's environment. Verify installed distribution metadata before
and after offline pytest without invoking pip, importing app code, or network.
This is a pinned-distribution check, not a full environment attestation.
"""
from __future__ import annotations

import argparse
from importlib import metadata
from pathlib import Path
import re
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_FILES = ("requirements.txt", "requirements-ci.lock")
PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.+!_-]*)\Z")


def _normalise_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_exact_pins(source_bytes: dict[str, bytes]) -> dict[str, str]:
    """Reject omissions, ambiguous pins and nonliteral requirement syntax."""
    if type(source_bytes) is not dict or set(source_bytes) != set(REQUIREMENT_FILES):
        raise ValueError("both exact CI requirement files are required")
    pins: dict[str, str] = {}
    for filename in REQUIREMENT_FILES:
        raw = source_bytes[filename]
        if type(raw) is not bytes or not raw:
            raise ValueError(f"missing or invalid requirement bytes: {filename}")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"non-UTF-8 requirement file: {filename}") from exc
        if "\r" in content or "\x00" in content:
            raise ValueError(f"ambiguous requirement line separators: {filename}")
        for line_number, line in enumerate(content.split("\n"), 1):
            if not line or line.startswith("#"):
                continue
            match = PIN.fullmatch(line)
            if not match:
                raise ValueError(
                    f"CI dependency must have one literal == pin: {filename}:{line_number}"
                )
            name, version = match.groups()
            canonical = _normalise_name(name)
            if canonical in pins:
                raise ValueError(f"duplicate CI dependency pin: {canonical}")
            pins[canonical] = version
    if not pins:
        raise ValueError("CI requirements have no pinned distributions")
    return pins


def verify_installed_ci_dependencies(
    source_bytes: dict[str, bytes],
    distributions: Iterable[object],
) -> int:
    """Require exactly one installed distribution with each pinned version.

    Extra runner packages are not treated as pinned and are outside this
    deliberately narrow guarantee; a full lock/environment attestation would
    require separately capturing *all* installed distributions and artifacts.
    """
    pins = parse_exact_pins(source_bytes)
    observed: dict[str, list[str]] = {name: [] for name in pins}
    for distribution in distributions:
        name = distribution.metadata.get("Name")
        if not isinstance(name, str) or not name:
            continue
        canonical = _normalise_name(name)
        if canonical in observed:
            version = distribution.version
            if not isinstance(version, str) or not version:
                raise ValueError(f"invalid installed version metadata: {canonical}")
            observed[canonical].append(version)
    for name, expected in sorted(pins.items()):
        versions = observed[name]
        if not versions:
            raise ValueError(f"pinned CI distribution missing: {name}=={expected}")
        if len(versions) != 1:
            raise ValueError(f"ambiguous installed CI distributions for {name}: {versions}")
        if versions[0] != expected:
            raise ValueError(
                f"installed CI dependency drift: {name} expected {expected}, got {versions[0]}"
            )
    return len(pins)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("before-tests", "after-tests"))
    args = parser.parse_args()
    try:
        source = {name: (ROOT / name).read_bytes() for name in REQUIREMENT_FILES}
        count = verify_installed_ci_dependencies(source, metadata.distributions())
    except (OSError, ValueError) as exc:
        parser.exit(1, f"VERA INSTALLED CI DEPENDENCIES ({args.phase}): FAIL: {exc}\n")
    print(
        f"VERA INSTALLED CI DEPENDENCIES ({args.phase}): PASS "
        f"({count} exact pinned distributions observed; local runner only)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
