"""Prevent accidental paid live-app smoke runs from routine code pushes.

The frozen automated study, archive recovery, and human-evaluation workflows
are separate. This checks YAML without dispatching a provider or using secrets.
"""

from pathlib import Path

import pytest
import yaml


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github" / "workflows" / "live-app-smoke.yml"
)
ACK = "NONCANONICAL_LIVE_SMOKE"
GUARD = "Require explicit noncanonical live-smoke acknowledgement"
SMOKE = "Run live WebSocket research smoke test"


def dispatch_problems(source: str) -> list[str]:
    try:
        document = yaml.load(source, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return ["invalid workflow YAML"]
    if not isinstance(document, dict):
        return ["invalid workflow"]
    triggers = document.get("on")
    if not isinstance(triggers, dict) or set(triggers) != {"workflow_dispatch"}:
        return ["manual-only dispatch required for paid live smoke"]
    dispatch = triggers.get("workflow_dispatch")
    inputs = dispatch.get("inputs") if isinstance(dispatch, dict) else None
    ack = inputs.get("smoke_ack") if isinstance(inputs, dict) else None
    faults = []
    if not isinstance(ack, dict) or (
        ack.get("required") != "true"
        or ack.get("type") != "string"
        or "default" in ack
    ):
        faults.append("mandatory, nondefault live-smoke acknowledgement missing")

    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"live-smoke"}:
        return faults + ["unexpected live-smoke job layout"]
    job = jobs["live-smoke"]
    steps = job.get("steps") if isinstance(job, dict) else None
    if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
        return faults + ["first-step execution gate missing"]
    first = steps[0]
    if (
        first.get("name") != GUARD
        or first.get("if") is not None
        or first.get("continue-on-error") is not None
        or first.get("shell") != "bash"
    ):
        faults.append("guard must be unconditional, failure-enforcing first step")
    if first.get("env") != {"VERA_LIVE_SMOKE_ACK": "${{ inputs.smoke_ack }}"}:
        faults.append("guard must take dispatch input via environment")
    script = first.get("run")
    if not isinstance(script, str) or (
        'if [ "$VERA_LIVE_SMOKE_ACK" != "' + ACK + '" ]; then' not in script
        or "exit 1" not in script
        or "NONCANONICAL LIVE SMOKE" not in script
        or "$GITHUB_STEP_SUMMARY" not in script
    ):
        faults.append("guard must fail closed and label diagnostic execution")

    actual_smoke = [
        step
        for step in steps
        if isinstance(step, dict)
        and "scripts/smoke_test_app.py" in str(step.get("run", ""))
    ]
    if len(actual_smoke) != 1 or actual_smoke[0].get("name") != SMOKE:
        faults.append("expected one explicit live smoke entrypoint")
    return faults


def test_live_smoke_requires_deliberate_dispatch_before_paid_work():
    assert dispatch_problems(WORKFLOW.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("original", "replacement", "expected"),
    [
        ("  workflow_dispatch:", "  push:\n  workflow_dispatch:", "manual-only"),
        ("required: true", "required: false", "mandatory"),
        ("type: string", "type: boolean", "mandatory"),
        ("type: string", "type: string\n        default: NONCANONICAL_LIVE_SMOKE", "mandatory"),
        ("exit 1", "exit 0", "fail closed"),
        ("VERA_LIVE_SMOKE_ACK: ${{ inputs.smoke_ack }}",
         "VERA_LIVE_SMOKE_ACK: NONCANONICAL_LIVE_SMOKE", "dispatch input"),
        ("- name: " + GUARD, "- name: Bypassed guard", "first step"),
        ("- name: " + SMOKE, "- name: Changed smoke step", "live smoke entrypoint"),
    ],
)
def test_rejects_unsafe_dispatch_regressions(original, replacement, expected):
    current = WORKFLOW.read_text(encoding="utf-8")
    modified = current.replace(original, replacement, 1)
    assert modified != current
    assert any(expected in error for error in dispatch_problems(modified))


def test_rejects_early_or_non_failing_acknowledgement_step():
    current = WORKFLOW.read_text(encoding="utf-8")
    early = current.replace(
        "      - name: " + GUARD,
        "      - name: Unexpected early step\n"
        "        run: echo before-consent\n"
        "      - name: " + GUARD,
        1,
    )
    assert any("first step" in e for e in dispatch_problems(early))
    bypass = current.replace(
        "      - name: " + GUARD,
        "      - name: " + GUARD + "\n        continue-on-error: true",
        1,
    )
    assert any("failure-enforcing" in e for e in dispatch_problems(bypass))
