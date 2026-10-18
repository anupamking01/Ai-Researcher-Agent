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
SHELL_CONTROL_TOKENS = {";", "&", "&&", "|", "||"}
PINNED_PIP_BOOTSTRAP = [
    ["python", "-m", "pip", "install", "-r", "requirements.txt"],
    ["python", "-m", "pip", "install", "-r", "requirements-dev.txt"],
    ["python", "-m", "pip", "check"],
]
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
PINNED_PYTHON_VERSION = "3.11.17"
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

        document = yaml.load(
            workflow.read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
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
                setup_options = step.get("with", {})
                python_version = setup_options.get("python-version")
                if python_version != PINNED_PYTHON_VERSION:
                    problems.append(
                        f"{workflow_name}:{job_name}: "
                        f"python-version={python_version!r}"
                    )

                pip_version = setup_options.get("pip-version")
                if pip_version != PINNED_PIP_VERSION:
                    problems.append(
                        f"{workflow_name}:{job_name}: pip-version={pip_version!r}"
                    )

                update_environment = setup_options.get("update-environment", "true")
                if update_environment != "true":
                    problems.append(
                        f"{workflow_name}:{job_name}: "
                        f"update-environment={update_environment!r}"
                    )

            for step in job.get("steps", []):
                command = step.get("run", "")
                if _contains_pip_self_install(command):
                    problems.append(
                        f"{workflow_name}:{job_name}: unpinned pip upgrade"
                    )

    return problems


def _pip_environment_problems(
    workflows: Path,
    *,
    required_workflows: set[str],
    enforce_bootstrap_contract: bool = False,
) -> list[str]:
    problems: list[str] = []

    for workflow_name in sorted(required_workflows):
        workflow = workflows / workflow_name
        if not workflow.is_file():
            problems.append(f"{workflow_name}: missing workflow")
            continue

        document = yaml.load(
            workflow.read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        if (
            enforce_bootstrap_contract
            and document.get("defaults", {}).get("run")
        ):
            problems.append(
                f"{workflow_name}: workflow-level run defaults are not allowed "
                "for dependency bootstrap"
            )
        for job_name, job in document.get("jobs", {}).items():
            if enforce_bootstrap_contract:
                contract_problem = _pip_bootstrap_contract_problem(job)
                if contract_problem is not None:
                    problems.append(
                        f"{workflow_name}:{job_name}: {contract_problem}"
                    )

            commands = "\n".join(
                step.get("run", "") for step in job.get("steps", [])
            )
            installs: list[tuple[int, str]] = []
            checks: list[int] = []
            for line_index, tokens in enumerate(_shell_command_lines(commands)):
                invocations = _pip_invocations(tokens)
                for token_index, launcher, arguments in invocations:
                    if "install" in arguments:
                        installs.append((line_index, launcher))
                        if launcher != "python -m pip":
                            problems.append(
                                f"{workflow_name}:{job_name}: "
                                f"dependency install uses {launcher!r}"
                            )
                        elif (
                            token_index != 0
                            or arguments[0] != "install"
                            or len(invocations) != 1
                            or any(token in SHELL_CONTROL_TOKENS for token in tokens)
                        ):
                            problems.append(
                                f"{workflow_name}:{job_name}: dependency install "
                                "is not standalone 'python -m pip'"
                            )

                    if tokens == ["python", "-m", "pip", "check"]:
                        checks.append(line_index)

            if installs and not any(
                check_index > installs[-1][0] for check_index in checks
            ):
                problems.append(
                    f"{workflow_name}:{job_name}: missing post-install python -m pip check"
                )

    return problems


def _pip_bootstrap_contract_problem(job: dict[str, object]) -> str | None:
    if job.get("defaults", {}).get("run"):
        return "inherited run defaults are not allowed for dependency bootstrap"

    steps = job.get("steps", [])
    setup_indices = [
        index
        for index, step in enumerate(steps)
        if step.get("uses", "").startswith("actions/setup-python@")
        and not step.get("if")
        and not step.get("continue-on-error")
    ]
    exact_bootstrap_indices: list[int] = []
    for index, step in enumerate(steps):
        commands = _shell_command_lines(step.get("run", ""))
        if commands != PINNED_PIP_BOOTSTRAP:
            continue
        if step.get("if"):
            return "dependency bootstrap must be unconditional"
        if step.get("continue-on-error"):
            return "dependency bootstrap must be failure-enforcing"
        if step.get("shell") not in {None, "bash"}:
            return "dependency bootstrap must use bash shell semantics"
        exact_bootstrap_indices.append(index)

    if len(exact_bootstrap_indices) != 1:
        return (
            "dependency bootstrap must contain exact requirements installs "
            "and pip check"
        )
    bootstrap_index = exact_bootstrap_indices[0]
    if not any(setup_index < bootstrap_index for setup_index in setup_indices):
        setup_steps = [
            step
            for step in steps
            if step.get("uses", "").startswith("actions/setup-python@")
        ]
        if any(step.get("continue-on-error") for step in setup_steps):
            return (
                "setup-python must be failure-enforcing and precede "
                "dependency bootstrap"
            )
        return "setup-python must precede dependency bootstrap"

    for index, step in enumerate(steps):
        if index == bootstrap_index:
            continue
        if PIP_INSTALL_COMMAND.search(step.get("run", "")):
            return "dependency installs must be confined to the pinned bootstrap"
    return None


def _shell_command_lines(script: str) -> list[list[str]]:
    commands: list[list[str]] = []
    normalized = script.replace("\\\n", " ")
    for line in normalized.splitlines():
        tokens = shlex.split(line, comments=True, posix=True)
        if tokens:
            commands.append(tokens)
    return commands


def _pip_invocations(tokens: list[str]) -> list[tuple[int, str, list[str]]]:
    invocations: list[tuple[int, str, list[str]]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        executable = Path(token).name
        if (
            re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable)
            and tokens[index + 1 : index + 3] == ["-m", "pip"]
        ):
            invocations.append(
                (index, f"{token} -m pip", tokens[index + 3 :])
            )
            index += 3
            continue
        if executable in {"pip", "pip3"}:
            invocations.append((index, token, tokens[index + 1 :]))
        index += 1
    return invocations


def test_research_workflow_bootstrap_environment_is_frozen() -> None:
    problems = _bootstrap_pin_problems(
        WORKFLOWS,
        required_workflows=NODE24_PINNED_WORKFLOWS,
    )
    assert not problems, "mutable workflow bootstrap settings:\n" + "\n".join(problems)


def test_workflow_dependencies_use_and_validate_the_pinned_interpreter() -> None:
    problems = _pip_environment_problems(
        WORKFLOWS,
        required_workflows=NODE24_PINNED_WORKFLOWS,
        enforce_bootstrap_contract=True,
    )
    assert not problems, "unsafe workflow dependency bootstrap:\n" + "\n".join(
        problems
    )


def test_pip_environment_guard_rejects_bare_install_and_early_check(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "unsafe.yml").write_text(
        "jobs:\n"
        "  unit-tests:\n"
        "    steps:\n"
        "      - run: |\n"
        "          python -m pip check\n"
        "          pip install -r requirements.txt\n",
        encoding="utf-8",
    )

    assert _pip_environment_problems(
        workflows,
        required_workflows={"unsafe.yml"},
    ) == [
        "unsafe.yml:unit-tests: dependency install uses 'pip'",
        "unsafe.yml:unit-tests: missing post-install python -m pip check",
    ]


def test_pip_environment_guard_rejects_bare_pip_global_options(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "bare.yml").write_text(
        "jobs:\n"
        "  unit-tests:\n"
        "    steps:\n"
        "      - run: |\n"
        "          pip3 --no-cache-dir install -r requirements.txt\n"
        "          python -m pip check\n",
        encoding="utf-8",
    )
    (workflows / "wrong-python.yml").write_text(
        "jobs:\n"
        "  unit-tests:\n"
        "    steps:\n"
        "      - run: |\n"
        "          python3 -m pip install -r requirements.txt\n"
        "          python -m pip check\n",
        encoding="utf-8",
    )

    assert _pip_environment_problems(
        workflows,
        required_workflows={"bare.yml", "wrong-python.yml"},
    ) == [
        "bare.yml:unit-tests: dependency install uses 'pip3'",
        "wrong-python.yml:unit-tests: dependency install uses 'python3 -m pip'",
    ]


def test_pip_environment_guard_ignores_comments_and_echoes(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for workflow_name, false_check in {
        "comment.yml": "# python -m pip check",
        "echo.yml": "echo python -m pip check",
    }.items():
        (workflows / workflow_name).write_text(
            "jobs:\n"
            "  unit-tests:\n"
            "    steps:\n"
            "      - run: |\n"
            "          python -m pip install -r requirements.txt\n"
            f"          {false_check}\n",
            encoding="utf-8",
        )

    assert _pip_environment_problems(
        workflows,
        required_workflows={"comment.yml", "echo.yml"},
    ) == [
        "comment.yml:unit-tests: missing post-install python -m pip check",
        "echo.yml:unit-tests: missing post-install python -m pip check",
    ]


def test_pip_environment_guard_requires_exact_check_command(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for workflow_name, false_check in {
        "argument.yml": "python -m pip --log check list",
        "masked.yml": "python -m pip check || true",
        "conditional.yml": "python -m pip install -r requirements.txt || python -m pip check",
    }.items():
        install = "" if workflow_name == "conditional.yml" else (
            "          python -m pip install -r requirements.txt\n"
        )
        (workflows / workflow_name).write_text(
            "jobs:\n"
            "  unit-tests:\n"
            "    steps:\n"
            "      - run: |\n"
            f"{install}"
            f"          {false_check}\n",
            encoding="utf-8",
        )

    assert _pip_environment_problems(
        workflows,
        required_workflows={"argument.yml", "conditional.yml", "masked.yml"},
    ) == [
        "argument.yml:unit-tests: missing post-install python -m pip check",
        "conditional.yml:unit-tests: dependency install is not standalone 'python -m pip'",
        "conditional.yml:unit-tests: missing post-install python -m pip check",
        "masked.yml:unit-tests: missing post-install python -m pip check",
    ]


def test_pip_environment_guard_rejects_wrapped_or_absolute_interpreters(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for workflow_name, install in {
        "absolute.yml": "/usr/bin/python3.11 -m pip install -r requirements.txt",
        "path.yml": "env PATH=/other python -m pip install -r requirements.txt",
    }.items():
        (workflows / workflow_name).write_text(
            "jobs:\n"
            "  unit-tests:\n"
            "    steps:\n"
            "      - run: |\n"
            f"          {install}\n"
            "          python -m pip check\n",
            encoding="utf-8",
        )

    assert _pip_environment_problems(
        workflows,
        required_workflows={"absolute.yml", "path.yml"},
    ) == [
        "absolute.yml:unit-tests: dependency install uses '/usr/bin/python3.11 -m pip'",
        "path.yml:unit-tests: dependency install is not standalone 'python -m pip'",
    ]


def test_pip_environment_guard_requires_setup_before_bootstrap(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "unsafe.yml").write_text(
        "jobs:\n"
        "  unit-tests:\n"
        "    steps:\n"
        "      - run: |\n"
        "          python -m pip install -r requirements.txt\n"
        "          python -m pip install -r requirements-dev.txt\n"
        "          python -m pip check\n"
        "      - uses: actions/setup-python@immutable\n",
        encoding="utf-8",
    )

    assert _pip_environment_problems(
        workflows,
        required_workflows={"unsafe.yml"},
        enforce_bootstrap_contract=True,
    ) == ["unsafe.yml:unit-tests: setup-python must precede dependency bootstrap"]


def test_pip_environment_guard_requires_complete_unconditional_bootstrap(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    cases = {
        "missing-dev.yml": (
            "      - run: |\n"
            "          python -m pip install -r requirements.txt\n"
            "          python -m pip check\n"
        ),
        "shell-conditional.yml": (
            "      - run: |\n"
            "          if false; then\n"
            "            python -m pip install -r requirements.txt\n"
            "            python -m pip install -r requirements-dev.txt\n"
            "            python -m pip check\n"
            "          fi\n"
        ),
        "step-conditional.yml": (
            "      - if: ${{ false }}\n"
            "        run: |\n"
            "          python -m pip install -r requirements.txt\n"
            "          python -m pip install -r requirements-dev.txt\n"
            "          python -m pip check\n"
        ),
    }
    for workflow_name, bootstrap in cases.items():
        (workflows / workflow_name).write_text(
            "jobs:\n"
            "  unit-tests:\n"
            "    steps:\n"
            "      - uses: actions/setup-python@immutable\n"
            f"{bootstrap}",
            encoding="utf-8",
        )

    assert _pip_environment_problems(
        workflows,
        required_workflows=set(cases),
        enforce_bootstrap_contract=True,
    ) == [
        "missing-dev.yml:unit-tests: dependency bootstrap must contain exact requirements installs and pip check",
        "shell-conditional.yml:unit-tests: dependency bootstrap must contain exact requirements installs and pip check",
        "step-conditional.yml:unit-tests: dependency bootstrap must be unconditional",
    ]


def test_pip_environment_guard_rejects_failure_masking_step_metadata(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    setup = "      - uses: actions/setup-python@immutable\n"
    bootstrap = (
        "        run: |\n"
        "          python -m pip install -r requirements.txt\n"
        "          python -m pip install -r requirements-dev.txt\n"
        "          python -m pip check\n"
    )
    cases = {
        "bootstrap-ignore.yml": setup
        + "      - continue-on-error: true\n"
        + bootstrap,
        "bootstrap-shell.yml": setup
        + "      - shell: python\n"
        + bootstrap,
        "setup-ignore.yml": (
            "      - uses: actions/setup-python@immutable\n"
            "        continue-on-error: true\n"
            "      - name: Install dependencies\n"
            + bootstrap
        ),
    }
    for workflow_name, steps in cases.items():
        (workflows / workflow_name).write_text(
            "jobs:\n"
            "  unit-tests:\n"
            "    steps:\n"
            f"{steps}",
            encoding="utf-8",
        )

    assert _pip_environment_problems(
        workflows,
        required_workflows=set(cases),
        enforce_bootstrap_contract=True,
    ) == [
        "bootstrap-ignore.yml:unit-tests: dependency bootstrap must be failure-enforcing",
        "bootstrap-shell.yml:unit-tests: dependency bootstrap must use bash shell semantics",
        "setup-ignore.yml:unit-tests: setup-python must be failure-enforcing and precede dependency bootstrap",
    ]


def test_pip_environment_guard_rejects_installs_outside_bootstrap(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "unsafe.yml").write_text(
        "jobs:\n"
        "  unit-tests:\n"
        "    steps:\n"
        "      - run: python -m pip install other-package\n"
        "      - uses: actions/setup-python@immutable\n"
        "      - run: |\n"
        "          python -m pip install -r requirements.txt\n"
        "          python -m pip install -r requirements-dev.txt\n"
        "          python -m pip check\n",
        encoding="utf-8",
    )

    assert _pip_environment_problems(
        workflows,
        required_workflows={"unsafe.yml"},
        enforce_bootstrap_contract=True,
    ) == [
        "unsafe.yml:unit-tests: dependency installs must be confined to the pinned bootstrap"
    ]


def test_pip_environment_guard_rejects_inherited_run_defaults(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    bootstrap = (
        "      - uses: actions/setup-python@immutable\n"
        "      - run: |\n"
        "          python -m pip install -r requirements.txt\n"
        "          python -m pip install -r requirements-dev.txt\n"
        "          python -m pip check\n"
    )
    (workflows / "job.yml").write_text(
        "jobs:\n"
        "  unit-tests:\n"
        "    defaults:\n"
        "      run:\n"
        "        shell: bash {0} || true\n"
        "    steps:\n"
        f"{bootstrap}",
        encoding="utf-8",
    )
    (workflows / "workflow.yml").write_text(
        "defaults:\n"
        "  run:\n"
        "    shell: bash {0} || true\n"
        "jobs:\n"
        "  unit-tests:\n"
        "    steps:\n"
        f"{bootstrap}",
        encoding="utf-8",
    )

    assert _pip_environment_problems(
        workflows,
        required_workflows={"job.yml", "workflow.yml"},
        enforce_bootstrap_contract=True,
    ) == [
        "job.yml:unit-tests: inherited run defaults are not allowed for dependency bootstrap",
        "workflow.yml: workflow-level run defaults are not allowed for dependency bootstrap",
    ]


def test_pip_environment_guard_rejects_nested_installs_outside_bootstrap(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "unsafe.yml").write_text(
        "jobs:\n"
        "  unit-tests:\n"
        "    steps:\n"
        "      - uses: actions/setup-python@immutable\n"
        "      - run: bash -c 'pip install other-package'\n"
        "      - run: |\n"
        "          python -m pip install -r requirements.txt\n"
        "          python -m pip install -r requirements-dev.txt\n"
        "          python -m pip check\n",
        encoding="utf-8",
    )

    assert _pip_environment_problems(
        workflows,
        required_workflows={"unsafe.yml"},
        enforce_bootstrap_contract=True,
    ) == [
        "unsafe.yml:unit-tests: dependency installs must be confined to the pinned bootstrap"
    ]


def test_bootstrap_guard_rejects_python_patch_drift(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    setup_options = {
        "major-minor.yml": "          python-version: 3.11\n",
        "other-patch.yml": "          python-version: 3.11.18\n",
        "version-file.yml": "          python-version-file: .python-version\n",
    }
    for workflow_name, python_option in setup_options.items():
        (workflows / workflow_name).write_text(
            "jobs:\n"
            "  unit-tests:\n"
            f"    runs-on: {PINNED_RUNNER}\n"
            "    steps:\n"
            "      - uses: actions/setup-python@immutable\n"
            "        with:\n"
            f"{python_option}"
            f"          pip-version: {PINNED_PIP_VERSION}\n",
            encoding="utf-8",
        )

    assert _bootstrap_pin_problems(
        workflows,
        required_workflows=set(setup_options),
    ) == [
        "major-minor.yml:unit-tests: python-version='3.11'",
        "other-patch.yml:unit-tests: python-version='3.11.18'",
        "version-file.yml:unit-tests: python-version=None",
    ]


def test_bootstrap_guard_rejects_hidden_setup_python_environment(
    tmp_path: Path,
) -> None:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "hidden.yml").write_text(
        "jobs:\n"
        "  unit-tests:\n"
        f"    runs-on: {PINNED_RUNNER}\n"
        "    steps:\n"
        "      - uses: actions/setup-python@immutable\n"
        "        with:\n"
        f"          python-version: {PINNED_PYTHON_VERSION}\n"
        f"          pip-version: {PINNED_PIP_VERSION}\n"
        "          update-environment: false\n",
        encoding="utf-8",
    )

    assert _bootstrap_pin_problems(
        workflows,
        required_workflows={"hidden.yml"},
    ) == ["hidden.yml:unit-tests: update-environment='false'"]


def test_live_smoke_workflow_change_requires_manual_dispatch() -> None:
    workflow = WORKFLOWS / "live-app-smoke.yml"
    document = yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    automatic_paths = document["on"]["push"]["paths"]

    assert ".github/workflows/live-app-smoke.yml" not in automatic_paths


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
        f"          python-version: {PINNED_PYTHON_VERSION}\n"
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
