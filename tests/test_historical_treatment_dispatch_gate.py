"""Prevent future manual study reruns from masquerading as frozen original evidence.

This checks the real dispatch workflow statically: no live treatments are run.
The acknowledgement alone is not prospective preregistration or an archive pin.
"""
from pathlib import Path

import pytest
import yaml


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github" / "workflows" / "budget-main-study.yml"
)
ACK = "NONCANONICAL_REPLICATION"
GUARD = "Require explicit noncanonical replication acknowledgement"
ARTIFACT = "noncanonical-replication-budget-study-${{ github.run_id }}"


def dispatch_gate_problems(source: str) -> list[str]:
    try:
        spec = yaml.load(source, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return ["invalid workflow YAML"]
    if not isinstance(spec, dict):
        return ["invalid workflow root"]
    problems = []
    triggers = spec.get("on")
    if not isinstance(triggers, dict) or set(triggers) != {"workflow_dispatch"}:
        return ["historical study must only support intentional manual dispatch"]
    dispatch = triggers.get("workflow_dispatch")
    if not isinstance(dispatch, dict):
        return ["missing manual dispatch inputs"]
    inputs = dispatch.get("inputs")
    ack = inputs.get("replication_ack") if isinstance(inputs, dict) else None
    if not isinstance(ack, dict) or (
        ack.get("required") != "true"
        or ack.get("type") != "string"
        or "default" in ack
    ):
        problems.append("nondefault mandatory acknowledgement missing")
    jobs = spec.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"study"}:
        return problems + ["unexpected study job layout"]
    job = jobs["study"]
    steps = job.get("steps") if isinstance(job, dict) else None
    if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
        return problems + ["missing first-step execution guard"]
    first = steps[0]
    if first.get("name") != GUARD or first.get("if") is not None:
        problems.append("execution acknowledgement must be the unconditional first step")
    if first.get("env") != {
        "VERA_REPLICATION_ACK": "${{ inputs.replication_ack }}"
    }:
        problems.append("acknowledgement must enter through a quoted environment variable")
    code = first.get("run")
    if not isinstance(code, str) or (
        'if [ "$VERA_REPLICATION_ACK" != "' + ACK + '" ]; then' not in code
        or "exit 1" not in code
        or "GITHUB_STEP_SUMMARY" not in code
        or "NONCANONICAL REPLICATION" not in code
    ):
        problems.append("acknowledgement must fail closed and warn in run summary")
    live_steps = [
        step for step in steps if isinstance(step, dict)
        and "run_budget_main_study.py" in str(step.get("run", ""))
    ]
    if len(live_steps) != 1:
        problems.append("expected exactly one unchanged historical treatment entrypoint")
    uploads = [
        step for step in steps if isinstance(step, dict)
        and "actions/upload-artifact@" in str(step.get("uses", ""))
    ]
    if len(uploads) != 1 or not isinstance(uploads[0].get("with"), dict) or (
        uploads[0]["with"].get("name") != ARTIFACT
    ):
        problems.append("future artifacts must be labelled noncanonical replications")
    return problems


def test_real_historical_treatment_dispatch_is_noncanonical_and_gated():
    assert dispatch_gate_problems(WORKFLOW.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("old", "new", "error"),
    [
        ("required: true", "required: false", "mandatory acknowledgement"),
        ("type: string", "type: boolean", "mandatory acknowledgement"),
        ("required: true", "required: true\\n        default: NONCANONICAL_REPLICATION", "mandatory acknowledgement"),
        ("  workflow_dispatch:", "  push:\\n  workflow_dispatch:", "intentional manual dispatch"),
        ("exit 1", "exit 0", "fail closed"),
        ("VERA_REPLICATION_ACK: ${{ inputs.replication_ack }}",
         "VERA_REPLICATION_ACK: NONCANONICAL_REPLICATION", "quoted environment"),
        (ARTIFACT, "budget-main-study-${{ github.run_id }}", "noncanonical replications"),
        ("- name: Require explicit noncanonical replication acknowledgement",
         "- name: Disabled guard", "unconditional first step"),
    ],
)
def test_dispatch_guard_detects_unsafe_mutations(old, new, error):
    source = WORKFLOW.read_text(encoding="utf-8")
    # YAML mutation cases must introduce actual newlines, not a literal \\n.
    updated = source.replace(old, new.replace("\\n", "\n"), 1)
    assert updated != source
    assert any(error in problem for problem in dispatch_gate_problems(updated))


def test_guard_must_run_before_checkout_or_any_live_secret():
    source = WORKFLOW.read_text(encoding="utf-8")
    guard = source.index("- name: " + GUARD)
    checkout = source.index("- name: Checkout research branch")
    assert guard < checkout < source.index("- name: Validate API secret")
    # Inject a structurally valid YAML step without modifying an unrelated
    # literal backslash-n in the workflow's printf format string.
    changed = source.replace(
        "      - name: " + GUARD,
        "      - name: Inserted pre-guard step\n"
        "        run: echo premature\n"
        "      - name: " + GUARD,
        1,
    )
    assert "unconditional first step" in dispatch_gate_problems(changed)
