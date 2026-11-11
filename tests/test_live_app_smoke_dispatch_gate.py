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
ARCHIVE = "noncanonical-diagnostic-live-smoke-${{ github.run_id }}"


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

    # A second manual dispatch must not terminate a separately authorized
    # in-flight provider-backed smoke test, even when its own ack is invalid.
    concurrency = document.get("concurrency")
    if not isinstance(concurrency, dict) or (
        concurrency.get("group") != "live-app-smoke-${{ github.ref }}"
        or concurrency.get("cancel-in-progress") != "false"
    ):
        faults.append("live-smoke concurrency must not cancel approved runs")

    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"live-smoke"}:
        return faults + ["unexpected live-smoke job layout"]
    job = jobs["live-smoke"]
    if not isinstance(job, dict):
        return faults + ["malformed live-smoke job"]
    if job.get("permissions") != {"contents": "read"} or (
        document.get("permissions") not in (None, {"contents": "read"})
    ):
        faults.append("live-smoke must retain read-only token permissions")
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

    # Default GitHub Actions step conditions stop after a failed guard.
    # A later `if: always()` on a paid step would override that protection,
    # while continue-on-error could conceal an authorization failure.
    if job.get("continue-on-error") is not None:
        faults.append("live-smoke job must not mask acknowledgement failure")
    paid_steps = ("Validate live-test secret", "Start FastAPI application", SMOKE)
    positions = []
    for label in paid_steps:
        matches = [
            index for index, step in enumerate(steps)
            if isinstance(step, dict) and step.get("name") == label
        ]
        if len(matches) != 1:
            faults.append(f"expected exactly one paid execution step: {label}")
            continue
        index = matches[0]
        positions.append(index)
        step = steps[index]
        if step.get("if") is not None or step.get("continue-on-error") is not None:
            faults.append(f"{label}: paid step bypasses acknowledgement gate")
    if len(positions) == len(paid_steps) and positions != sorted(positions):
        faults.append("paid execution steps are out of order")

    # Neither an explicit cancellation API call nor Actions-write credentials
    # should reintroduce the same interruption after manual authorization.
    for step in steps:
        if not isinstance(step, dict):
            continue
        script = str(step.get("run", ""))
        if (
            "/cancel" in script or "gh run cancel" in script
            or "GH_TOKEN" in str(step.get("env", {}))
        ):
            faults.append("live-smoke must not cancel another authorized run")
            break

    uploads = [
        step for step in steps
        if isinstance(step, dict)
        and "actions/upload-artifact@" in str(step.get("uses", ""))
    ]
    if len(uploads) != 1 or not isinstance(uploads[0].get("with"), dict) or (
        uploads[0]["with"].get("name") != ARCHIVE
    ):
        faults.append("live-smoke artifacts must remain diagnostically labelled")

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


@pytest.mark.parametrize(
    "step_name",
    ["Validate live-test secret", "Start FastAPI application", SMOKE],
)
@pytest.mark.parametrize("unsafe_option", ["if: always()", "continue-on-error: true"])
def test_paid_steps_cannot_override_failed_acknowledgement(step_name, unsafe_option):
    current = WORKFLOW.read_text(encoding="utf-8")
    marker = "      - name: " + step_name + "\n"
    assert marker in current
    modified = current.replace(marker, marker + "        " + unsafe_option + "\n", 1)
    assert any(
        "paid step bypasses acknowledgement gate" in problem
        for problem in dispatch_problems(modified)
    )


def test_job_failure_cannot_be_hidden_after_rejected_acknowledgement():
    current = WORKFLOW.read_text(encoding="utf-8")
    marker = "  live-smoke:\n"
    assert marker in current
    modified = current.replace(marker, marker + "    continue-on-error: true\n", 1)
    assert any(
        "job must not mask acknowledgement failure" in problem
        for problem in dispatch_problems(modified)
    )


def test_paid_steps_must_remain_in_authorized_order():
    current = WORKFLOW.read_text(encoding="utf-8")
    modified = current.replace(
        "- name: Validate live-test secret", "- name: SWAP_SENTINEL", 1
    ).replace(
        "- name: Start FastAPI application", "- name: Validate live-test secret", 1
    ).replace(
        "- name: SWAP_SENTINEL", "- name: Start FastAPI application", 1
    )
    assert modified != current
    assert any(
        "paid execution steps are out of order" in problem
        for problem in dispatch_problems(modified)
    )


@pytest.mark.parametrize(
    ("needle", "replacement"),
    [
        ("cancel-in-progress: false", "cancel-in-progress: true"),
        ("  group: live-app-smoke-${{ github.ref }}", "  group: unrelated-group"),
    ],
)
def test_rejects_inflight_smoke_cancellation_or_unsafe_concurrency(needle, replacement):
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.count(needle) == 1
    changed = source.replace(needle, replacement, 1)
    assert any(
        "must not cancel approved runs" in issue
        for issue in dispatch_problems(changed)
    )


def test_rejects_concurrency_removal():
    source = WORKFLOW.read_text(encoding="utf-8")
    changed = source.replace(
        "concurrency:\n  group: live-app-smoke-${{ github.ref }}\n"
        "  cancel-in-progress: false\n",
        "",
        1,
    )
    assert changed != source
    assert any("must not cancel approved runs" in issue
               for issue in dispatch_problems(changed))


@pytest.mark.parametrize(
    "command",
    [
        "gh run cancel 1234",
        "curl -X POST https://api.github.com/repos/owner/repo/actions/runs/1234/cancel",
    ],
)
def test_rejects_explicit_smoke_run_cancellation(command):
    source = WORKFLOW.read_text(encoding="utf-8")
    marker = "      - name: Set up Python\n"
    assert marker in source
    changed = source.replace(
        marker,
        "      - name: Unapproved cancellation\n"
        "        run: " + command + "\n" + marker,
        1,
    )
    assert any("must not cancel another authorized run" in issue
               for issue in dispatch_problems(changed))


def test_rejects_actions_permission_escalation():
    source = WORKFLOW.read_text(encoding="utf-8")
    changed = source.replace(
        "      contents: read\n", "      contents: read\n      actions: write\n", 1
    )
    assert changed != source
    assert any("read-only token permissions" in issue
               for issue in dispatch_problems(changed))


def test_rejects_actions_token_reintroduction():
    source = WORKFLOW.read_text(encoding="utf-8")
    marker = "      - name: Set up Python\n"
    assert marker in source
    changed = source.replace(
        marker,
        "      - name: Unauthorized Actions token\n"
        "        env:\n          GH_TOKEN: synthetic-token\n"
        "        run: echo unused\n" + marker,
        1,
    )
    assert any("must not cancel another authorized run" in issue
               for issue in dispatch_problems(changed))


def test_rejects_unqualified_smoke_artifact_label():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.count("name: " + ARCHIVE) == 1
    changed = source.replace("name: " + ARCHIVE, "name: live-app-smoke-legacy", 1)
    assert any("diagnostically labelled" in issue
               for issue in dispatch_problems(changed))
