"""Regression guard for the ordinary offline VERA CI token boundary."""

from pathlib import Path

import pytest
import yaml


WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "tests.yml"
)


def _offline_ci_token_problems(source: str) -> list[str]:
    """Reject token escalation and credential persistence in offline CI jobs."""
    document = yaml.load(source, Loader=yaml.BaseLoader)
    if not isinstance(document, dict):
        return ["workflow must be a YAML mapping"]

    problems = []
    if document.get("permissions") != {"contents": "read"}:
        problems.append("workflow token must have only contents: read")
    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return problems + ["offline workflow must declare jobs"]

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            problems.append(f"{job_name}: job must be a mapping")
            continue
        if "permissions" in job:
            problems.append(f"{job_name}: job-level token permissions override forbidden")
        steps = job.get("steps")
        if not isinstance(steps, list):
            problems.append(f"{job_name}: missing steps")
            continue
        checkouts = [
            step for step in steps
            if isinstance(step, dict)
            and step.get("uses", "").startswith("actions/checkout@")
        ]
        if not checkouts:
            problems.append(f"{job_name}: missing explicit checkout")
        for step in checkouts:
            options = step.get("with")
            if not isinstance(options, dict) or options.get("persist-credentials") != "false":
                problems.append(f"{job_name}: checkout must disable persisted credentials")
    return problems


BASE = """name: tests
permissions:
  contents: read
jobs:
  unit-tests:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@0123456789012345678901234567890123456789
        with:
          persist-credentials: false
      - run: python -m pytest -q
"""


def test_offline_workflow_token_boundary():
    assert _offline_ci_token_problems(WORKFLOW.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "permissions", ["", "  contents: write\n", "  contents: read\n  actions: write\n"]
)
def test_token_escalation_is_rejected(permissions):
    modified = BASE.replace("  contents: read\n", permissions, 1)
    assert "workflow token must have only contents: read" in _offline_ci_token_problems(modified)


def test_job_scoped_permissions_override_is_rejected():
    modified = BASE.replace(
        "    runs-on: ubuntu-24.04\n",
        "    permissions:\n      contents: write\n    runs-on: ubuntu-24.04\n",
    )
    assert (
        "unit-tests: job-level token permissions override forbidden"
        in _offline_ci_token_problems(modified)
    )


@pytest.mark.parametrize(
    "replacement", ["persist-credentials: true", "fetch-depth: 1"]
)
def test_checkout_without_explicit_no_persist_is_rejected(replacement):
    modified = BASE.replace("persist-credentials: false", replacement)
    assert (
        "unit-tests: checkout must disable persisted credentials"
        in _offline_ci_token_problems(modified)
    )


def test_missing_checkout_is_rejected():
    modified = BASE.replace(
        "      - uses: actions/checkout@0123456789012345678901234567890123456789\n"
        "        with:\n"
        "          persist-credentials: false\n",
        "",
    )
    assert "unit-tests: missing explicit checkout" in _offline_ci_token_problems(modified)
