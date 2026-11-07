"""Protect offline validation from inheriting live research API credentials."""
from pathlib import Path
import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
SECRET = "${{ secrets.OPENAI_API_KEY }}"
ALLOWED = {
    "budget-main-study.yml": frozenset({
        "Validate API secret",
        "Preflight live search and browser extraction",
        "Run 10-task four-variant treatment matrix",
        "Apply common post-hoc support evaluator",
    }),
    "evaluator-recovery.yml": frozenset({
        "Validate API secret",
        "Resume common post-hoc evaluator only",
    }),
}


def _ref(value):
    if isinstance(value, dict):
        return any(_ref(v) for v in value.values())
    if isinstance(value, list):
        return any(_ref(v) for v in value)
    return isinstance(value, str) and "secrets.OPENAI_API_KEY" in value


def problems(source, *, allowed):
    workflow = yaml.load(source, Loader=yaml.BaseLoader)
    if not isinstance(workflow, dict):
        return ["expected YAML mapping"]
    faults = []
    for scope, env in (("workflow", workflow.get("env")),):
        if env is not None and (
            not isinstance(env, dict) or "OPENAI_API_KEY" in env or _ref(env)
        ):
            faults.append(f"{scope}: job-global secret exposure")
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return faults + ["no jobs"]
    seen = []
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            faults.append(f"{job_name}: malformed job")
            continue
        env = job.get("env")
        if env is not None and (
            not isinstance(env, dict) or "OPENAI_API_KEY" in env or _ref(env)
        ):
            faults.append(f"{job_name}: job-global secret exposure")
        steps = job.get("steps")
        if not isinstance(steps, list):
            faults.append(f"{job_name}: no steps")
            continue
        for n, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                faults.append(f"{job_name}: malformed step {n}")
                continue
            label = step.get("name", f"step {n}")
            step_env = step.get("env") or {}
            if not isinstance(step_env, dict):
                faults.append(f"{label}: malformed env")
                continue
            if _ref({k: v for k, v in step.items() if k != "env"}) or _ref({
                k: v for k, v in step_env.items() if k != "OPENAI_API_KEY"
            }):
                faults.append(f"{label}: secret interpolation outside approved env")
            if label in allowed:
                seen.append(label)
                if step_env.get("OPENAI_API_KEY") != SECRET:
                    faults.append(f"{label}: missing step-scoped secret")
            elif "OPENAI_API_KEY" in step_env:
                faults.append(f"{label}: offline step receives secret")
    for label in allowed:
        if seen.count(label) != 1:
            faults.append(f"{label}: expected one authorized live step")
    return faults


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_live_research_secrets_restricted_to_authorized_steps(name):
    assert problems(
        (WORKFLOWS / name).read_text(encoding="utf-8"),
        allowed=ALLOWED[name],
    ) == []


BASE = """name: synthetic
jobs:
  study:
    env:
      SMART_LLM_MODEL: fixed
    steps:
      - name: Run offline tests
        run: python -m pytest
      - name: Live experiment
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: python live.py
"""


def _audit(source):
    return problems(source, allowed=frozenset({"Live experiment"}))


def test_valid_synthetic_workflow():
    assert _audit(BASE) == []


def test_job_global_secret_rejected():
    changed = BASE.replace(
        "      SMART_LLM_MODEL: fixed",
        "      SMART_LLM_MODEL: fixed\n      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}",
    )
    assert any("job-global secret exposure" in issue for issue in _audit(changed))


def test_offline_secret_inheritance_rejected():
    changed = BASE.replace(
        "      - name: Run offline tests",
        "      - name: Run offline tests\n        env:\n"
        "          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}",
    )
    assert any("offline step receives secret" in issue for issue in _audit(changed))


def test_provider_secret_alias_and_inline_usage_rejected():
    changed = BASE.replace(
        "run: python -m pytest",
        "run: echo ${{ secrets.OPENAI_API_KEY }}",
    )
    assert any("interpolation outside approved env" in issue for issue in _audit(changed))
    aliased = BASE.replace(
        "      SMART_LLM_MODEL: fixed",
        "      SMART_LLM_MODEL: ${{ secrets.OPENAI_API_KEY }}",
    )
    assert any("job-global secret exposure" in issue for issue in _audit(aliased))


def test_missing_live_secret_or_renamed_step_rejected():
    changed = BASE.replace(
        "          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}\n", ""
    )
    assert any("missing step-scoped secret" in issue for issue in _audit(changed))
    renamed = BASE.replace("name: Live experiment", "name: New step")
    assert any("expected one authorized live step" in issue for issue in _audit(renamed))
