"""Synthetic-only checks for the pinned CI runtime and workflow enforcement."""
from pathlib import Path

import pytest
import yaml

from scripts import verify_ci_python_runtime as runtime


VALID = {
    "version": (3, 11, 17),
    "releaselevel": "final",
    "serial": 0,
    "implementation": "cpython",
    "platform_name": "linux",
    "machine": "x86_64",
    "pointer_bits": 64,
}


def test_exact_ci_runtime_is_accepted_without_inspecting_host():
    assert runtime.verify_ci_python_runtime(**VALID).startswith("CPython 3.11.17")


@pytest.mark.parametrize(("override", "reason"), [
    ({"version": (3, 11, 16)}, "version"),
    ({"version": (3, 12, 0)}, "version"),
    ({"version": (3, 11, True)}, "version"),
    ({"version": [3, 11, 17]}, "version"),
    ({"releaselevel": "candidate"}, "version"),
    ({"serial": 1}, "version"),
    ({"implementation": "pypy"}, "implementation"),
    ({"platform_name": "darwin"}, "platform"),
    ({"machine": "aarch64"}, "platform"),
    ({"pointer_bits": 32}, "ABI"),
    ({"pointer_bits": True}, "ABI"),
])
def test_refuses_runtime_drift_even_if_requirement_pins_match(override, reason):
    with pytest.raises(ValueError, match=reason):
        runtime.verify_ci_python_runtime(**{**VALID, **override})


def test_workflow_enforces_actual_runtime_before_and_after_tests():
    workflow = yaml.load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/tests.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["unit-tests"]["steps"]
    names = [s.get("name", "") for s in steps]
    setup = names.index("Set up Python")
    before = names.index("Verify pinned CI Python runtime before tests")
    install = names.index("Install application and test dependencies")
    test = names.index("Run offline unit tests")
    after = names.index("Verify pinned CI Python runtime after tests")
    receipt = names.index("Bind exact-commit offline test evidence")
    assert steps[setup]["with"]["python-version"] == runtime.PINNED_VERSION_TEXT
    assert setup < before < install < test < after < receipt
    for index, phase in ((before, "before-tests"), (after, "after-tests")):
        step = steps[index]
        assert "continue-on-error" not in step
        assert step["run"].strip() == (
            f"python -m scripts.verify_ci_python_runtime --phase {phase}"
        )
