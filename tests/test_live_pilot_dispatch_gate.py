"""Offline checks: paid diagnostic pilot requires authorization and distinct evidence."""
from pathlib import Path

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/live-pilot.yml"
ACK = "NONCANONICAL_LIVE_PILOT"
GUARD = "Require explicit noncanonical live-pilot acknowledgement"
SECRET = "Validate API secret is configured"
PREFLIGHT = "Preflight live search and concurrent browser extraction"
TREATMENT = "Run frozen live pilot"
ARCHIVE = "noncanonical-diagnostic-pilot-${{ github.run_id }}"


def dispatch_gate_problems(source: str) -> list[str]:
    try:
        spec = yaml.load(source, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return ["invalid workflow YAML"]
    if not isinstance(spec, dict):
        return ["invalid workflow root"]
    if not isinstance(spec.get("on"), dict) or set(spec["on"]) != {"workflow_dispatch"}:
        return ["paid pilot must have manual-only dispatch"]
    dispatch = spec["on"]["workflow_dispatch"]
    inputs = dispatch.get("inputs") if isinstance(dispatch, dict) else None
    ack = inputs.get("pilot_ack") if isinstance(inputs, dict) else None
    faults: list[str] = []
    if not isinstance(ack, dict) or (
        ack.get("required") != "true" or ack.get("type") != "string"
        or "default" in ack
    ):
        faults.append("mandatory nondefault pilot acknowledgement missing")
    concurrency = spec.get("concurrency")
    if not isinstance(concurrency, dict) or concurrency.get("cancel-in-progress") != "false":
        faults.append("unacknowledged dispatch must not cancel active pilot runs")

    jobs = spec.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"pilot"}:
        return faults + ["unexpected pilot job layout"]
    job = jobs["pilot"]
    if not isinstance(job, dict):
        return faults + ["malformed pilot job"]
    if job.get("continue-on-error") is not None or job.get("if") is not None:
        faults.append("pilot job must enforce failed acknowledgement")
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
        return faults + ["missing first-step pilot acknowledgement guard"]
    first = steps[0]
    if (
        first.get("name") != GUARD or first.get("if") is not None
        or first.get("continue-on-error") is not None
        or first.get("shell") != "bash"
    ):
        faults.append("pilot guard must be unconditional first step")
    if first.get("env") != {"VERA_PILOT_ACK": "${{ inputs.pilot_ack }}"}:
        faults.append("guard must use the manual dispatch acknowledgement")
    script = first.get("run")
    if not isinstance(script, str) or (
        'if [ "$VERA_PILOT_ACK" != "' + ACK + '" ]; then' not in script
        or "exit 1" not in script
        or "NONCANONICAL DIAGNOSTIC PILOT" not in script
        or "$GITHUB_STEP_SUMMARY" not in script
    ):
        faults.append("guard must fail closed and label pilot diagnostic")

    # A newly acknowledged diagnostic must not cancel other approved runs.
    # Restrict the job to read-only repository access.
    if job.get("permissions") != {"contents": "read"}:
        faults.append("pilot job requires read-only contents permission")
    if spec.get("permissions") not in (None, {"contents": "read"}):
        faults.append("pilot workflow must not elevate permissions")
    if any(
        isinstance(step, dict) and (
            "/cancel" in str(step.get("run", ""))
            or "gh run cancel" in str(step.get("run", ""))
            or "GH_TOKEN" in str(step.get("env", {}))
        )
        for step in steps
    ):
        faults.append("pilot must not cancel other authorized runs")

    # Provider-backed steps must not bypass a failed acknowledgement.
    ordered = [SECRET, PREFLIGHT, TREATMENT]
    positions: list[int] = []
    for label in ordered:
        matches = [
            (i, step) for i, step in enumerate(steps)
            if isinstance(step, dict) and step.get("name") == label
        ]
        if len(matches) != 1:
            faults.append(f"expected one authorization-gated step: {label}")
            continue
        index, step = matches[0]
        positions.append(index)
        if index == 0 or step.get("if") is not None or (
            step.get("continue-on-error") is not None
        ):
            faults.append(f"{label}: step bypasses failed acknowledgement")
    if len(positions) == len(ordered) and positions != sorted(positions):
        faults.append("live pilot authorization step order changed")

    live_entries = [
        step for step in steps if isinstance(step, dict)
        and "scripts/run_pilot.py" in str(step.get("run", ""))
    ]
    if len(live_entries) != 1 or live_entries[0].get("name") != TREATMENT:
        faults.append("expected exactly one gated pilot execution entrypoint")
    uploads = [
        step for step in steps if isinstance(step, dict)
        and "actions/upload-artifact@" in str(step.get("uses", ""))
    ]
    if len(uploads) != 1 or not isinstance(uploads[0].get("with"), dict) or (
        uploads[0]["with"].get("name") != ARCHIVE
    ):
        faults.append("future pilot archives must be labelled noncanonical")
    return faults


def test_real_pilot_requires_consent_without_live_execution():
    assert dispatch_gate_problems(WORKFLOW.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("  workflow_dispatch:", "  push:\n  workflow_dispatch:", "manual-only"),
        ("required: true", "required: false", "mandatory"),
        ("type: string", "type: boolean", "mandatory"),
        ("type: string", "type: string\n        default: NONCANONICAL_LIVE_PILOT", "mandatory"),
        ("cancel-in-progress: false", "cancel-in-progress: true", "must not cancel"),
        ("exit 1", "exit 0", "fail closed"),
        ("VERA_PILOT_ACK: ${{ inputs.pilot_ack }}",
         "VERA_PILOT_ACK: NONCANONICAL_LIVE_PILOT", "manual dispatch"),
        ("- name: " + GUARD, "- name: Guard removed", "first step"),
        ("name: " + ARCHIVE, "name: research-pilot-${{ github.run_id }}", "noncanonical"),
        ("- name: " + TREATMENT, "- name: Renamed pilot", "entrypoint"),
    ],
)
def test_unsafe_dispatch_or_evidence_mutations_rejected(old, new, expected):
    source = WORKFLOW.read_text(encoding="utf-8")
    changed = source.replace(old, new, 1)
    assert changed != source
    assert any(expected in problem for problem in dispatch_gate_problems(changed))


def test_guard_precedes_checkout_or_provider_access():
    source = WORKFLOW.read_text(encoding="utf-8")
    changed = source.replace(
        "      - name: " + GUARD,
        "      - name: Unexpected early step\n        run: echo premature\n"
        "      - name: " + GUARD, 1
    )
    assert any("first step" in p for p in dispatch_gate_problems(changed))


@pytest.mark.parametrize("label", [SECRET, PREFLIGHT, TREATMENT])
@pytest.mark.parametrize("option", ["if: always()", "continue-on-error: true"])
def test_paid_steps_cannot_override_guard(label, option):
    source = WORKFLOW.read_text(encoding="utf-8")
    marker = "      - name: " + label + "\n"
    assert marker in source
    changed = source.replace(marker, marker + "        " + option + "\n", 1)
    assert any("bypasses failed acknowledgement" in p
               for p in dispatch_gate_problems(changed))


def test_job_must_not_mask_guard_failure():
    source = WORKFLOW.read_text(encoding="utf-8")
    changed = source.replace(
        "  pilot:\n", "  pilot:\n    continue-on-error: true\n", 1
    )
    assert any("enforce failed acknowledgement" in p
               for p in dispatch_gate_problems(changed))


def test_live_steps_keep_gated_order():
    source = WORKFLOW.read_text(encoding="utf-8")
    changed = source.replace(
        "- name: " + SECRET, "- name: SWAP_NAME", 1
    ).replace(
        "- name: " + TREATMENT, "- name: " + SECRET, 1
    ).replace(
        "- name: SWAP_NAME", "- name: " + TREATMENT, 1
    )
    assert any("order changed" in p for p in dispatch_gate_problems(changed))


@pytest.mark.parametrize(
    "shell_command",
    [
        'gh api -X POST "repos/$GITHUB_REPOSITORY/actions/runs/$run_id/cancel"',
        "gh run cancel 123456",
        "curl -X POST https://api.github.com/repos/example/repo/actions/runs/123/cancel",
    ],
)
def test_reintroduced_cancellation_rejected(shell_command):
    source = WORKFLOW.read_text(encoding="utf-8")
    marker = "      - name: Set up Python\n"
    assert marker in source
    changed = source.replace(
        marker,
        "      - name: Unexpected cancellation\n"
        "        run: |\n"
        f"          {shell_command}\n"
        + marker,
        1,
    )
    assert any("must not cancel other authorized runs" in p
               for p in dispatch_gate_problems(changed))


@pytest.mark.parametrize(
    "permission",
    ["      actions: write\n", "      contents: write\n"],
)
def test_privilege_escalation_rejected(permission):
    source = WORKFLOW.read_text(encoding="utf-8")
    marker = "      contents: read\n"
    assert marker in source
    changed = source.replace(marker, marker + permission, 1)
    assert any("read-only contents permission" in p
               for p in dispatch_gate_problems(changed))


def test_reintroduced_actions_token_rejected():
    source = WORKFLOW.read_text(encoding="utf-8")
    marker = "      - name: Set up Python\n"
    assert marker in source
    changed = source.replace(
        marker,
        "      - name: Unexpected token\n"
        "        env:\n"
        "          GH_TOKEN: secret-token-placeholder\n"
        "        run: echo token-is-not-needed\n"
        + marker,
        1,
    )
    assert any("must not cancel other authorized runs" in p
               for p in dispatch_gate_problems(changed))
