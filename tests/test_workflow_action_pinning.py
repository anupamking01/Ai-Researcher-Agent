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
