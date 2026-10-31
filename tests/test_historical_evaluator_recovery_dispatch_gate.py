"""Fail closed before repeating a frozen evaluator or publishing replacement evidence.

The real workflow is examined without running any model or evaluator.
"""
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/evaluator-recovery.yml"
ACK = "NONCANONICAL_EVALUATOR_RECOVERY"
GUARD = "Require explicit noncanonical evaluator-recovery acknowledgement"
NAME = "noncanonical-evaluator-recovery-${{ github.run_id }}"
CONDITION = "${{ always() && steps.recovery_guard.outcome == 'success' }}"


def problems(source):
    try:
        workflow = yaml.load(source, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return ["invalid YAML"]
    if not isinstance(workflow, dict):
        return ["invalid workflow"]
    trigger = workflow.get("on")
    if not isinstance(trigger, dict) or set(trigger) != {"workflow_dispatch"}:
        return ["manual-only dispatch required"]
    opts = trigger["workflow_dispatch"]
    inputs = opts.get("inputs") if isinstance(opts, dict) else None
    ack = inputs.get("recovery_ack") if isinstance(inputs, dict) else None
    faults = []
    if not isinstance(ack, dict) or (
        ack.get("required") != "true" or ack.get("type") != "string"
        or "default" in ack
    ):
        faults.append("mandatory nondefault acknowledgement missing")
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"recover-evaluator"}:
        return faults + ["unexpected jobs"]
    job = jobs["recover-evaluator"]
    steps = job.get("steps") if isinstance(job, dict) else None
    if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
        return faults + ["missing first step"]
    first = steps[0]
    if (first.get("name") != GUARD or first.get("id") != "recovery_guard"
        or first.get("if") is not None or first.get("continue-on-error") is not None):
        faults.append("unconditional first guard step missing")
    if first.get("env") != {"VERA_RECOVERY_ACK": "${{ inputs.recovery_ack }}"}:
        faults.append("guard must use dispatch environment input")
    code = first.get("run")
    if not isinstance(code, str) or (
        'if [ "$VERA_RECOVERY_ACK" != "' + ACK + '" ]; then' not in code
        or "exit 1" not in code or "$GITHUB_STEP_SUMMARY" not in code
        or "NONCANONICAL EVALUATOR RECOVERY" not in code
    ):
        faults.append("acknowledgement must fail closed and warn")
    downloads = [s for s in steps if isinstance(s, dict)
                 and str(s.get("uses", "")).startswith("actions/download-artifact@")]
    if len(downloads) != 1 or not isinstance(downloads[0].get("with"), dict) or (
        downloads[0]["with"].get("run-id") != "34620917346"
        or downloads[0]["with"].get("name") != "budget-main-study-34620917346"
    ):
        faults.append("historical input identity must remain pinned")
    live = [s for s in steps if isinstance(s, dict)
            and "scripts/evaluate_posthoc_support.py" in str(s.get("run", ""))]
    if len(live) != 1 or live[0].get("name") != "Resume common post-hoc evaluator only":
        faults.append("expected exactly one evaluator step")
    elif ("--noncanonical-evaluator-replay-ack " + ACK
          not in str(live[0].get("run", ""))):
        faults.append("live evaluator bypasses direct replay acknowledgement")
    uploads = [s for s in steps if isinstance(s, dict)
               and str(s.get("uses", "")).startswith("actions/upload-artifact@")]
    if len(uploads) != 1 or not isinstance(uploads[0].get("with"), dict) or (
        uploads[0]["with"].get("name") != NAME or uploads[0].get("if") != CONDITION
    ):
        faults.append("uploads must be guard-gated and noncanonical")
    return faults


def test_real_workflow_is_protected():
    assert problems(WORKFLOW.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(("old", "new", "fault"), [
    ("required: true", "required: false", "mandatory nondefault"),
    ("type: string", "type: boolean", "mandatory nondefault"),
    ("required: true", "required: true\n        default: bypass", "mandatory nondefault"),
    ("  workflow_dispatch:", "  push:\n  workflow_dispatch:", "manual-only"),
    ("exit 1", "exit 0", "fail closed"),
    ("VERA_RECOVERY_ACK: ${{ inputs.recovery_ack }}", "VERA_RECOVERY_ACK: hardcoded", "dispatch environment"),
    (NAME, "budget-main-study-recovered-${{ github.run_id }}", "noncanonical"),
    (CONDITION, "always()", "guard-gated"),
    ("run-id: 34620917346", "run-id: 34783525480", "input identity"),
    (" --noncanonical-evaluator-replay-ack " + ACK,
     " --noncanonical-evaluator-replay-ack NONCANONICAL_REPLICATION",
     "direct replay acknowledgement"),
    ("- name: " + GUARD, "- name: Other guard", "unconditional first"),
])
def test_rejects_unsafe_workflow_mutation(old, new, fault):
    original = WORKFLOW.read_text(encoding="utf-8")
    changed = original.replace(old, new, 1)
    assert changed != original
    assert any(fault in message for message in problems(changed))


def test_guard_must_precede_checkout_secrets_and_evaluator():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert (source.index("- name: " + GUARD)
            < source.index("- name: Checkout research branch")
            < source.index("- name: Validate API secret")
            < source.index("- name: Resume common post-hoc evaluator only"))
    changed = source.replace("      - name: " + GUARD,
                             "      - name: Early unsafe step\n"
                             "        run: echo premature\n"
                             "      - name: " + GUARD, 1)
    assert any("unconditional first" in item for item in problems(changed))
