"""Distinguish read-only audit execution from source-change trigger paths.

GitHub Actions trigger path filters may legitimately watch the treatment runner,
but a runnable step or its execution inputs must not invoke treatment or
evaluator code. This lexical guard does not claim to sandbox Actions or
resolve dynamically assembled commands. BaseLoader preserves 'on' as text.
"""
from __future__ import annotations

import yaml


class _UniqueMappingBaseLoader(yaml.BaseLoader):
    """Retain BaseLoader's textual YAML keys without accepting duplicates."""


def _unique_mapping(loader: _UniqueMappingBaseLoader, node: yaml.MappingNode) -> dict:
    """Reject ambiguous executable YAML at every mapping depth."""
    assert isinstance(node, yaml.MappingNode), "audit YAML mapping expected"
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        assert isinstance(key, str), "audit YAML mapping keys must be strings"
        assert key not in result, (
            f"duplicate YAML mapping key {key!r} at line {key_node.start_mark.line + 1}"
        )
        result[key] = loader.construct_object(value_node, deep=True)
    return result


_UniqueMappingBaseLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


FORBIDDEN_EXECUTABLE_MARKERS = (
    "run_budget_main_study",
    "run_pilot",
    "evaluate_posthoc_support",
)


def _assert_no_research_execution(value: object, *, location: str) -> None:
    """Check action inputs/environment recursively, not unrelated trigger paths."""
    if isinstance(value, dict):
        for key, child in value.items():
            assert isinstance(key, str), f"{location}: malformed input name"
            _assert_no_research_execution(child, location=f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_research_execution(child, location=f"{location}[{index}]")
    else:
        assert isinstance(value, str), f"{location}: malformed executable input"
        for forbidden in FORBIDDEN_EXECUTABLE_MARKERS:
            assert forbidden not in value, (
                f"{location}: read-only archive audit must not execute {forbidden}"
            )


def _check_optional_mapping(context: dict, key: str, *, location: str) -> None:
    if key not in context:
        return
    value = context[key]
    assert isinstance(value, dict), f"{location}: malformed {key} mapping"
    _assert_no_research_execution(value, location=f"{location}.{key}")


def _check_optional_shell(context: dict, *, location: str) -> None:
    """A custom Actions shell template can execute code outside its run body."""
    if "shell" not in context:
        return
    shell = context["shell"]
    assert isinstance(shell, str) and shell.strip(), f"{location}: malformed shell"
    _assert_no_research_execution(shell, location=f"{location}.shell")


def _check_default_run_shell(context: dict, *, location: str) -> None:
    """Inspect workflow/job shell defaults, not unrelated source-watch metadata."""
    if "defaults" not in context:
        return
    defaults = context["defaults"]
    assert isinstance(defaults, dict), f"{location}: malformed defaults mapping"
    if "run" not in defaults:
        return
    run = defaults["run"]
    assert isinstance(run, dict), f"{location}: malformed defaults.run mapping"
    _check_optional_shell(run, location=f"{location}.defaults.run")


def assert_read_only_workflow_steps(workflow_text: str) -> None:
    """Reject forbidden research execution in commands, shells, env and inputs."""
    workflow = yaml.load(workflow_text, Loader=_UniqueMappingBaseLoader)
    assert isinstance(workflow, dict), "audit workflow must be a YAML mapping"
    _check_optional_mapping(workflow, "env", location="workflow")
    _check_default_run_shell(workflow, location="workflow")
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict) and jobs, "audit workflow needs jobs"
    for job_name, job in jobs.items():
        assert isinstance(job, dict), f"{job_name}: malformed job"
        _check_optional_mapping(job, "env", location=f"job {job_name}")
        _check_default_run_shell(job, location=f"job {job_name}")
        steps = job.get("steps")
        assert isinstance(steps, list) and steps, f"{job_name}: missing steps"
        for index, step in enumerate(steps):
            label = f"{job_name} step {index}"
            assert isinstance(step, dict), f"{label}: malformed step"
            assert "run" in step or "uses" in step, f"{label}: missing executable"
            for key in ("run", "uses"):
                if key in step:
                    _assert_no_research_execution(step[key], location=f"{label}.{key}")
            _check_optional_shell(step, location=label)
            _check_optional_mapping(step, "env", location=label)
            _check_optional_mapping(step, "with", location=label)
