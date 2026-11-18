"""Preserve a complete, nonduplicated research PR CI trigger boundary.

Synthetic workflow-policy mutations only. No provider or treatment execution.
"""

from pathlib import Path

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/tests.yml"

BASE = """name: tests
on:
  push:
    branches:
      - main
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
jobs: {}
"""


def _event_policy_problems(source: str) -> list[str]:
    try:
        workflow = yaml.load(source, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return ["invalid workflow YAML"]
    if not isinstance(workflow, dict) or not isinstance(workflow.get("on"), dict):
        return ["missing workflow event mapping"]
    events = workflow["on"]
    problems = []
    if set(events) != {"push", "pull_request", "workflow_dispatch"}:
        problems.append("unexpected or missing full-suite events")
    if events.get("push") != {"branches": ["main"]}:
        problems.append("full suite push must target only main")
    if "pull_request" not in events or events["pull_request"] != "":
        problems.append("full suite must run for every pull request")
    if "workflow_dispatch" not in events or events["workflow_dispatch"] != "":
        problems.append("full suite must permit manual research-branch dispatch")
    return problems


def test_full_suite_has_one_automatic_research_pr_route() -> None:
    # PR CI is mandatory even when independent specialist jobs are green.
    assert _event_policy_problems(WORKFLOW.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("altered", "problem"),
    [
        (
            BASE.replace("      - main\n", '      - main\n      - "research-*"\n'),
            "full suite push must target only main",
        ),
        (
            BASE.replace("  pull_request:\n", ""),
            "full suite must run for every pull request",
        ),
        (
            BASE.replace("  pull_request:\n", "  pull_request:\n    paths: [tests/**]\n"),
            "full suite must run for every pull request",
        ),
        (
            BASE.replace("  pull_request:\n", "  pull_request:\n    branches: [main]\n"),
            "full suite must run for every pull request",
        ),
        (
            BASE.replace("  workflow_dispatch:\n", ""),
            "full suite must permit manual research-branch dispatch",
        ),
        (
            BASE.replace("  push:\n    branches:\n      - main\n", "  push:\n"),
            "full suite push must target only main",
        ),
    ],
)
def test_mutated_full_suite_triggers_fail_closed(altered: str, problem: str) -> None:
    assert problem in _event_policy_problems(altered)


def test_trigger_contract_accepts_only_explicit_safe_route() -> None:
    assert _event_policy_problems(BASE) == []
    assert "unexpected or missing full-suite events" in _event_policy_problems(
        BASE.replace("  workflow_dispatch:\n", "  schedule:\n    - cron: '0 0 * * *'\n")
    )
