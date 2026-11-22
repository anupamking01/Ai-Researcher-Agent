"""Distinguish read-only audit commands from source-change trigger paths.

Audit workflows must *watch* treatment/evaluator source for drift, but cannot
execute treatments or evaluators. Interpret actual job steps rather than
searching a complete workflow for a substring; a watched filename is not a
shell command. Use BaseLoader to preserve GitHub's 'on' key as a string.
"""
from __future__ import annotations

import yaml


FORBIDDEN_EXECUTABLE_MARKERS = (
    "run_budget_main_study",
    "run_pilot",
    "evaluate_posthoc_support",
)


def assert_read_only_workflow_steps(workflow_text: str) -> None:
    """Fail closed if any executable job step invokes research generation."""
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict), "audit workflow must be a YAML mapping"
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict) and jobs, "audit workflow needs jobs"
    for job_name, job in jobs.items():
        assert isinstance(job, dict), f"{job_name}: malformed job"
        steps = job.get("steps")
        assert isinstance(steps, list) and steps, f"{job_name}: missing steps"
        for index, step in enumerate(steps):
            assert isinstance(step, dict), f"{job_name} step {index}: malformed step"
            assert "run" in step or "uses" in step, (
                f"{job_name} step {index}: missing executable"
            )
            for key in ("run", "uses"):
                executable = step.get(key, "")
                assert isinstance(executable, str), (
                    f"{job_name} step {index}: malformed {key}"
                )
                for forbidden in FORBIDDEN_EXECUTABLE_MARKERS:
                    assert forbidden not in executable, (
                        f"{job_name} step {index}: read-only archive audit "
                        f"must not execute {forbidden}"
                    )
