"""Synthetic-only CI environment pin verification (no installs or network)."""
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts import verify_ci_installed_dependencies as installed


def _dist(name, version):
    return SimpleNamespace(metadata={"Name": name}, version=version)


SOURCE = {
    "requirements.txt": b"foo_bar==1.0.0\n",
    "requirements-ci.lock": b"pytest==8.3.2\n",
}
DISTRIBUTIONS = [_dist("foo.bar", "1.0.0"), _dist("pytest", "8.3.2")]


def test_valid_pinned_distributions_are_checked_with_canonical_names():
    assert installed.verify_installed_ci_dependencies(
        SOURCE, [*DISTRIBUTIONS, _dist("unrelated", "9.0")]
    ) == 2


@pytest.mark.parametrize("distributions, message", [
    ([_dist("pytest", "8.3.2")], "missing"),
    ([_dist("foo-bar", "1.0.1"), _dist("pytest", "8.3.2")], "drift"),
    ([*DISTRIBUTIONS, _dist("foo_bar", "1.0.0")], "ambiguous"),
    ([_dist("foo-bar", ""), _dist("pytest", "8.3.2")], "invalid"),
])
def test_missing_changed_duplicate_or_invalid_installed_metadata_fails(distributions, message):
    with pytest.raises(ValueError, match=message):
        installed.verify_installed_ci_dependencies(SOURCE, distributions)


@pytest.mark.parametrize("bad_source, message", [
    ({"requirements.txt": SOURCE["requirements.txt"]}, "both exact"),
    ({**SOURCE, "requirements.txt": b"foo_bar>=1.0.0\n"}, "literal =="),
    ({**SOURCE, "requirements.txt": b"-e ./foo\n"}, "literal =="),
    ({**SOURCE, "requirements.txt": b"foo_bar==1.0.0\r\n"}, "separators"),
    ({**SOURCE, "requirements.txt": b"foo_bar==1.0.0\nfoo-bar==1.0.0\n"}, "duplicate"),
    ({**SOURCE, "requirements-ci.lock": b"FOO.BAR==1.0.0\n"}, "duplicate"),
    ({**SOURCE, "requirements.txt": b"\xff"}, "non-UTF-8"),
])
def test_ambiguous_incomplete_or_nonliteral_pins_are_rejected(bad_source, message):
    with pytest.raises(ValueError, match=message):
        installed.verify_installed_ci_dependencies(bad_source, DISTRIBUTIONS)


def test_workflow_checks_observed_environment_before_and_after_offline_pytest():
    workflow = yaml.load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/tests.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["unit-tests"]["steps"]
    names = [step.get("name", "") for step in steps]
    install = names.index("Install application and test dependencies")
    before = names.index("Verify installed CI dependencies before tests")
    compile_step = names.index("Compile research code")
    test_step = names.index("Run offline unit tests")
    after = names.index("Verify installed CI dependencies after tests")
    evidence = names.index("Bind exact-commit offline test evidence")
    assert install < before < compile_step < test_step < after < evidence
    for index, phase in ((before, "before-tests"), (after, "after-tests")):
        step = steps[index]
        assert "continue-on-error" not in step
        assert step["run"].strip() == (
            f"python -m scripts.verify_ci_installed_dependencies --phase {phase}"
        )
