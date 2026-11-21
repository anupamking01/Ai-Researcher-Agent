"""Regression guard: checkout authentication must not survive read-only evidence audits."""
import re
from pathlib import Path
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1] / ".github" / "workflows"
READ_ONLY_AUDITS = (
    ("exploratory-pareto-stability.yml", "verify-exploratory-pareto", 1, {"contents": "read"}),
    ("git-canonical-escrow-offline-audit.yml", "verify-git-escrow", 2, {"contents": "read"}),
    ("preserved-canonical-package-audit.yml", "verify-outer-package", 2, {"contents": "read", "actions": "read"}),
    ("retained-canonical-archive-audit.yml", "verify-retained-archive", 2, {"contents": "read", "actions": "read"}),
)
PINNED = re.compile(r"actions/checkout@[a-f0-9]{40}\Z")


def _problems(source, *, job_name, expected_checkouts, permissions):
    try:
        document = yaml.load(source, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return ["invalid YAML"]
    if not isinstance(document, dict):
        return ["workflow must be a mapping"]
    errors = []
    if document.get("permissions") != permissions:
        errors.append("workflow token permissions must remain read-only")
    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {job_name}:
        return errors + ["unexpected or missing research-audit job"]
    job = jobs[job_name]
    if not isinstance(job, dict):
        return errors + ["invalid audit job"]
    if "permissions" in job:
        errors.append("job token permission override forbidden")
    steps = job.get("steps")
    if not isinstance(steps, list):
        return errors + ["audit steps missing"]
    checkouts = [step for step in steps if isinstance(step, dict)
                 and str(step.get("uses", "")).startswith("actions/checkout@")]
    if len(checkouts) != expected_checkouts:
        errors.append("unapproved checkout count")
    for step in checkouts:
        if not PINNED.fullmatch(str(step.get("uses", ""))):
            errors.append("checkout must be immutable-SHA-pinned")
        options = step.get("with")
        if not isinstance(options, dict) or options.get("persist-credentials") != "false":
            errors.append("checkout credentials must not persist")
    return errors


@pytest.mark.parametrize("filename,job,number,permissions", READ_ONLY_AUDITS)
def test_read_only_audit_checkout_boundary(filename, job, number, permissions):
    source = (ROOT / filename).read_text(encoding="utf-8")
    assert _problems(source, job_name=job, expected_checkouts=number, permissions=permissions) == []


@pytest.mark.parametrize("filename,job,number,permissions", READ_ONLY_AUDITS)
@pytest.mark.parametrize("replacement", [
    "persist-credentials: true",
    "persist-credentials: ${{ github.event_name == 'push' }}",
    "fetch-depth: 1",
])
def test_checkout_mutations_fail_closed(filename, job, number, permissions, replacement):
    source = (ROOT / filename).read_text(encoding="utf-8")
    mutated = source.replace("persist-credentials: false", replacement, 1)
    assert mutated != source
    assert _problems(mutated, job_name=job, expected_checkouts=number, permissions=permissions)


@pytest.mark.parametrize("filename,job,number,permissions", READ_ONLY_AUDITS)
def test_workflow_token_escalation_fails(filename, job, number, permissions):
    source = (ROOT / filename).read_text(encoding="utf-8")
    mutated = source.replace("  contents: read\n", "  contents: write\n", 1)
    assert mutated != source
    assert "workflow token permissions must remain read-only" in _problems(
        mutated, job_name=job, expected_checkouts=number, permissions=permissions)


@pytest.mark.parametrize("filename,job,number,permissions", READ_ONLY_AUDITS)
def test_job_token_override_fails(filename, job, number, permissions):
    source = (ROOT / filename).read_text(encoding="utf-8")
    mutated = source.replace("    steps:\n",
        "    permissions:\n      contents: write\n    steps:\n", 1)
    assert mutated != source
    assert "job token permission override forbidden" in _problems(
        mutated, job_name=job, expected_checkouts=number, permissions=permissions)


@pytest.mark.parametrize("filename,job,number,permissions", READ_ONLY_AUDITS)
def test_unprotected_new_checkout_fails(filename, job, number, permissions):
    source = (ROOT / filename).read_text(encoding="utf-8")
    mutated = source.replace("    steps:\n",
        "    steps:\n      - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803\n", 1)
    assert mutated != source
    assert "unapproved checkout count" in _problems(
        mutated, job_name=job, expected_checkouts=number, permissions=permissions)
