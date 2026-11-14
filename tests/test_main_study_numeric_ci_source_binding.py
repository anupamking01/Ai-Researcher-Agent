"""Require frozen published-input identity before standalone numeric CI certification.

Synthetic/structural CI assertions only; no treatment, evaluation or inference reruns.
"""
from __future__ import annotations

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/main-study-numeric-input-integrity.yml"
BOUND_RUNNER = "scripts/audit_main_study_bound_inputs.py"


def _load_workflow() -> dict:
    return yaml.load((ROOT / WORKFLOW).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _static_script_dependencies(entrypoint: str) -> set[str]:
    visited = set()
    pending = [entrypoint]
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                if node.module == "scripts":
                    modules = [alias.name for alias in node.names]
                elif node.module and node.module.startswith("scripts."):
                    modules = [node.module.split(".")[1]]
            elif isinstance(node, ast.Import):
                modules = [
                    alias.name.split(".")[1] for alias in node.names
                    if alias.name.startswith("scripts.")
                ]
            for module in modules:
                path = f"scripts/{module}.py"
                if (ROOT / path).is_file() and path not in visited:
                    pending.append(path)
    return visited


def test_numeric_ci_requires_single_source_bound_receipt_and_fails_closed():
    data = _load_workflow()
    assert data["permissions"] == {"contents": "read"}
    jobs = data["jobs"]
    assert list(jobs) == ["offline-numeric-audit"]
    steps = [step for step in jobs["offline-numeric-audit"]["steps"] if "run" in step]
    assert len(steps) == 1
    step = steps[0]
    assert not step.get("if") and not step.get("continue-on-error")
    assert step.get("shell") in (None, "bash")
    commands = [line.strip() for line in step["run"].splitlines() if line.strip()]
    runner = "python -m scripts.audit_main_study_bound_inputs"
    assert commands.count(runner) == 1
    # Separate processes could pass on different CSV generations.
    assert "python -m scripts.verify_published_main_study_inputs" not in commands
    assert "python -m scripts.audit_main_study_numeric_inputs" not in commands
    assert all("|| true" not in command and "; true" not in command for command in commands)


def test_numeric_ci_both_event_filters_cover_source_anchor_and_dependencies():
    data = _load_workflow()
    required = {
        WORKFLOW, "scripts/audit_main_study_numeric_inputs.py",
        "outputs/main_study_runs.csv", "outputs/posthoc_support_runs.csv",
        "outputs/main_study_analysis_inputs_manifest.json",
        "tests/test_main_study_numeric_integrity.py",
        "tests/test_main_study_csv_export_safety.py",
        "tests/test_main_study_numeric_ci_source_binding.py",
        "tests/test_main_study_bound_input_receipt.py",
    } | _static_script_dependencies(BOUND_RUNNER)
    for event in ("push", "pull_request"):
        paths = data["on"][event]["paths"]
        assert len(paths) == len(set(paths))
        assert required <= set(paths), (
            f"{event} skips source-verification changes: {sorted(required - set(paths))}"
        )
