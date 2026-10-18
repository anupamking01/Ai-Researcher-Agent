"""Supply-chain regression checks for GitHub Actions workflows.

Research workflow definitions are part of the reproducibility boundary.  A
mutable tag such as ``v4`` can resolve to different action code over time, so
every external action must be locked to an immutable commit SHA.  Local
actions remain allowed because their bytes are already fixed by the repository
commit under test.
"""

from __future__ import annotations

import re
from pathlib import Path


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
USES_LINE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
FULL_COMMIT_SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)
NODE24_ACTION_PINS = {
    "actions/checkout": "d23441a48e516b6c34aea4fa41551a30e30af803",
    "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
}
NODE24_PINNED_WORKFLOWS = {
    "budget-main-study.yml",
    "canonical-main-study-analysis.yml",
    "evaluator-recovery.yml",
    "live-app-smoke.yml",
    "live-pilot.yml",
    "tests.yml",
}


def _mutable_action_references(workflows: Path) -> list[str]:
    mutable: list[str] = []

    workflow_files = [*workflows.glob("*.yml"), *workflows.glob("*.yaml")]
    for workflow in sorted(workflow_files):
        text = workflow.read_text(encoding="utf-8")
        for action in USES_LINE.findall(text):
            if action.startswith("./"):
                continue
            _name, separator, revision = action.rpartition("@")
            if not separator or FULL_COMMIT_SHA.fullmatch(revision) is None:
                mutable.append(f"{workflow.name}: {action}")

    return mutable


def test_external_workflow_actions_are_pinned_to_full_commit_shas() -> None:
    mutable = _mutable_action_references(WORKFLOWS)
    assert not mutable, "mutable external action references:\n" + "\n".join(mutable)


def test_guard_scans_yaml_workflows_with_sequence_shorthand(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "shorthand.yaml").write_text(
        "steps:\n  - uses: owner/action@mutable\n",
        encoding="utf-8",
    )

    assert _mutable_action_references(workflows) == [
        "shorthand.yaml: owner/action@mutable"
    ]


def _runtime_action_pin_problems(
    workflows: Path,
    *,
    required_workflows: set[str],
) -> list[str]:
    problems: list[str] = []

    for workflow_name in sorted(required_workflows):
        workflow = workflows / workflow_name
        if not workflow.is_file():
            problems.append(f"{workflow_name}: missing workflow")
            continue

        revisions: dict[str, list[str]] = {name: [] for name in NODE24_ACTION_PINS}
        for action in USES_LINE.findall(workflow.read_text(encoding="utf-8")):
            name, separator, revision = action.rpartition("@")
            if separator and name in revisions:
                revisions[name].append(revision)

        for name, expected_revision in NODE24_ACTION_PINS.items():
            if not revisions[name]:
                problems.append(f"{workflow_name}: missing {name}")
                continue
            for revision in revisions[name]:
                if revision != expected_revision:
                    problems.append(f"{workflow_name}: {name}@{revision}")

    return problems


def test_runtime_actions_use_reviewed_node24_revisions() -> None:
    problems = _runtime_action_pin_problems(
        WORKFLOWS,
        required_workflows=NODE24_PINNED_WORKFLOWS,
    )
    assert not problems, "missing or deprecated runtime action pins:\n" + "\n".join(
        problems
    )


def test_guard_requires_each_runtime_action_in_every_target_workflow(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "complete.yml").write_text(
        "steps:\n"
        f"  - uses: actions/checkout@{NODE24_ACTION_PINS['actions/checkout']}\n"
        f"  - uses: actions/setup-python@{NODE24_ACTION_PINS['actions/setup-python']}\n",
        encoding="utf-8",
    )
    (workflows / "missing.yml").write_text("steps: []\n", encoding="utf-8")

    assert _runtime_action_pin_problems(
        workflows,
        required_workflows={"complete.yml", "missing.yml"},
    ) == [
        "missing.yml: missing actions/checkout",
        "missing.yml: missing actions/setup-python",
    ]
