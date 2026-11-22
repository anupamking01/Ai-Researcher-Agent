"""Synthetic research-audit safety regressions; never run treatments."""
from pathlib import Path

import pytest

from scripts.audit_workflow_read_only import assert_read_only_workflow_steps


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_AUDITS = (
    ".github/workflows/retained-canonical-archive-audit.yml",
    ".github/workflows/preserved-canonical-package-audit.yml",
)
BASE = """name: synthetic-read-only-audit
on:
  push:
    paths:
      - scripts/run_budget_main_study.py
      - scripts/evaluate_posthoc_support.py
jobs:
  audit:
    runs-on: ubuntu-24.04
    steps:
      - name: inspect retained artifact
        uses: actions/checkout@pinned
        with:
          persist-credentials: false
      - name: replay receipt
        run: echo verified
"""


def _injected(scope: str, command: str) -> str:
    if scope == "workflow-env":
        return BASE.replace(
            "jobs:\n", f"env:\n  AUDIT_COMMAND: {command}\njobs:\n"
        ).replace("run: echo verified", "run: $AUDIT_COMMAND")
    if scope == "job-env":
        return BASE.replace(
            "    runs-on: ubuntu-24.04\n",
            f"    env:\n      AUDIT_COMMAND: {command}\n    runs-on: ubuntu-24.04\n",
        ).replace("run: echo verified", "run: $AUDIT_COMMAND")
    if scope == "step-env":
        return BASE.replace(
            "        run: echo verified\n",
            f"        env:\n          AUDIT_COMMAND: {command}\n"
            "        run: $AUDIT_COMMAND\n",
        )
    if scope == "action-with":
        return BASE.replace(
            "          persist-credentials: false\n",
            f"          persist-credentials: false\n          command: {command}\n",
        ).replace("uses: actions/checkout@pinned", "uses: example/execute-command@pinned")
    raise AssertionError("unknown synthetic scope")


@pytest.mark.parametrize("scope", (
    "workflow-env", "job-env", "step-env", "action-with",
))
@pytest.mark.parametrize("command", (
    "python -m scripts.run_budget_main_study",
    "python -m scripts.run_pilot",
    "python -m scripts.evaluate_posthoc_support",
))
def test_guard_rejects_delegated_research_execution(scope, command):
    # A safe-looking run of an env variable or executable action may consume
    # a forbidden command invisible to the old run/uses-only guard.
    with pytest.raises(AssertionError, match="must not execute"):
        assert_read_only_workflow_steps(_injected(scope, command))


@pytest.mark.parametrize("field", ("env", "with"))
def test_guard_fails_closed_on_malformed_executable_mapping(field):
    source = BASE.replace(
        "        run: echo verified\n",
        f"        {field}: ignored-scalar\n        run: echo verified\n",
    )
    with pytest.raises(AssertionError, match="malformed"):
        assert_read_only_workflow_steps(source)


def test_source_watch_filters_are_not_execution():
    assert "scripts/run_budget_main_study.py" in BASE
    assert_read_only_workflow_steps(BASE)


@pytest.mark.parametrize("workflow", ARCHIVE_AUDITS)
def test_actual_archive_audit_execution_contexts_remain_read_only(workflow):
    assert_read_only_workflow_steps((ROOT / workflow).read_text(encoding="utf-8"))
