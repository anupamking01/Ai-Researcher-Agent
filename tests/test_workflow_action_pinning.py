"""Supply-chain regression checks for GitHub Actions workflows.

Research workflow definitions are part of the reproducibility boundary.  A
mutable tag such as ``v4`` can resolve to different action code over time, so
every external action must be locked to an immutable commit SHA.  Local
actions remain allowed because their bytes are already fixed by the repository
commit under test.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
USES_LINE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
FULL_COMMIT_SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)
PIP_INSTALL_COMMAND = re.compile(
    r"\bpip3?\b[^;&|\n]*?\binstall\b(?P<arguments>[^;&|\n]*)",
    re.ASCII,
)
PIP_REQUIREMENT = re.compile(
    r"pip(?:\[[^\]]+\])?(?:[<>=!~].*)?",
    re.ASCII | re.IGNORECASE,
)
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
PINNED_RUNNER = "ubuntu-24.04"
PINNED_PIP_VERSION = "26.2.1"


def _contains_pip_self_install(command: str) -> bool:
    normalized = command.replace("\\\n", " ")
    for match in PIP_INSTALL_COMMAND.finditer(normalized):
        install_arguments = shlex.split(match.group("arguments"), comments=True)
        targets_pip = any(
            PIP_REQUIREMENT.fullmatch(argument) is not None
            for argument in install_arguments
        ) or any(
            argument == "--upgrade=pip" for argument in install_arguments
        )
        if targets_pip:
            return True

    return False


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


def _bootstrap_pin_problems(
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

        document = yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        for job_name, job in document.get("jobs", {}).items():
            runner = job.get("runs-on")
            if runner != PINNED_RUNNER:
                problems.append(f"{workflow_name}:{job_name}: runs-on={runner!r}")

            setup_python_steps = [
                step
                for step in job.get("steps", [])
                if step.get("uses", "").startswith("actions/setup-python@")
            ]
            if not setup_python_steps:
                problems.append(
                    f"{workflow_name}:{job_name}: missing actions/setup-python"
                )
            for step in setup_python_steps:
                pip_version = step.get("with", {}).get("pip-version")
                if pip_version != PINNED_PIP_VERSION:
                    problems.append(
                        f"{workflow_name}:{job_name}: pip-version={pip_version!r}"
                    )

            for step in job.get("steps", []):
                command = step.get("run", "")
                if _contains_pip_self_install(command):
                    problems.append(
                        f"{workflow_name}:{job_name}: unpinned pip upgrade"
                    )

    return problems


def test_research_workflow_bootstrap_environment_is_frozen() -> None:
    problems = _bootstrap_pin_problems(
        WORKFLOWS,
        required_workflows=NODE24_PINNED_WORKFLOWS,
    )
    assert not problems, "mutable workflow bootstrap settings:\n" + "\n".join(problems)


def test_bootstrap_guard_requires_setup_python_in_each_job(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "missing.yml").write_text(
        "jobs:\n"
        "  unit-tests:\n"
        f"    runs-on: {PINNED_RUNNER}\n"
        "    steps: []\n",
        encoding="utf-8",
    )

    assert _bootstrap_pin_problems(
        workflows,
        required_workflows={"missing.yml"},
    ) == ["missing.yml:unit-tests: missing actions/setup-python"]


def test_bootstrap_guard_rejects_pip_upgrade_shorthand(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "mutable.yml").write_text(
        "jobs:\n"
        "  unit-tests:\n"
        f"    runs-on: {PINNED_RUNNER}\n"
        "    steps:\n"
        "      - uses: actions/setup-python@immutable\n"
        "        with:\n"
        f"          pip-version: {PINNED_PIP_VERSION}\n"
        "      - run: pip install -U pip\n",
        encoding="utf-8",
    )

    assert _bootstrap_pin_problems(
        workflows,
        required_workflows={"mutable.yml"},
    ) == ["mutable.yml:unit-tests: unpinned pip upgrade"]


def test_pip_upgrade_detector_handles_shell_prefixes_and_global_options() -> None:
    mutable_commands = [
        "sudo pip install -U pip",
        "env FOO=1 pip install --upgrade pip",
        "cd /tmp && pip install --upgrade pip",
        "pip install pip --upgrade; echo done",
        "pip --disable-pip-version-check install -U pip",
    ]

    undetected = [
        command for command in mutable_commands if not _contains_pip_self_install(command)
    ]
    assert not undetected, "undetected pip self-upgrades:\n" + "\n".join(undetected)


def test_pip_detector_rejects_versioned_self_installs() -> None:
    mutable_commands = [
        "pip install --upgrade pip==27.0",
        'pip install -U "pip>=26"',
        "python -m pip install pip==25.3",
    ]

    undetected = [
        command for command in mutable_commands if not _contains_pip_self_install(command)
    ]
    assert not undetected, "undetected pip self-installs:\n" + "\n".join(undetected)
