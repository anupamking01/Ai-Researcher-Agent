"""Outcome-free synthetic coverage of historical task-freeze ancestry."""
import json
import pytest
from scripts import audit_historical_task_freeze as audit

SOURCE = json.dumps({
    "task_set_id": audit.TASK_SET, "frozen_before_execution": True,
    "purpose": "Synthetic manifest only",
    "tasks": [{"id": f"main-{n:02d}", "category": "synthetic",
               "question": f"Question {n}"} for n in range(1, 11)],
}).encode()

def fake_git(*, freeze_blob=None, launch_blob=None, bad_ancestry=False,
             shallow=False, source=SOURCE, bad_commit=False):
    freeze_blob = audit.BLOB if freeze_blob is None else freeze_blob
    launch_blob = freeze_blob if launch_blob is None else launch_blob
    def run(root, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return (str(root) + "\n").encode()
        if args == ("rev-parse", "--is-shallow-repository"):
            return b"true\n" if shallow else b"false\n"
        if len(args) == 2 and args[0] == "rev-parse" and args[1].endswith("^{commit}"):
            return (("a" * 40 if bad_commit else args[1].split("^")[0]) + "\n").encode()
        if args[:2] == ("merge-base", "--is-ancestor"):
            if bad_ancestry and args[2] == audit.FREEZE:
                raise audit.TaskFreezeError("not an ancestor")
            return b""
        if args == ("rev-parse", f"{audit.FREEZE}:{audit.PATH}"):
            return (freeze_blob + "\n").encode()
        if args == ("rev-parse", f"{audit.LAUNCH}:{audit.PATH}"):
            return (launch_blob + "\n").encode()
        if args == ("show", f"{audit.FREEZE}:{audit.PATH}"):
            return source
        raise AssertionError(args)
    return run

def test_source_structure():
    assert audit.inspect_manifest(SOURCE) == list(audit.TASK_IDS)

@pytest.mark.parametrize("source", [
    b"{}", b"\xff", b'{"a":NaN}',
    SOURCE.replace(b'"frozen_before_execution": true', b'"frozen_before_execution": false'),
    SOURCE.replace(b'"id": "main-10"', b'"id": "main-09"'),
    SOURCE.replace(b'"purpose":', b'"purpose": "duplicate", "purpose":', 1),
    SOURCE.replace(b'"question": "Question 10"', b'"question": ""'),
])
def test_reject_untrustworthy_manifest(source):
    with pytest.raises(audit.TaskFreezeError):
        audit.inspect_manifest(source)

def test_valid_ancestry_receipt_never_claims_registration_or_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "_git", fake_git())
    receipt = audit.audit(tmp_path)
    assert receipt["prelaunch_git_ancestry_verified"] is True
    assert receipt["unchanged_manifest_blob_at_launch"] is True
    assert receipt["task_ids"] == list(audit.TASK_IDS)
    for key in ("independent_external_task_preregistration_established",
                "task_selection_outcome_blinding_established",
                "task_independence_established",
                "original_treatment_execution_authenticated",
                "original_report_trace_custody_authenticated",
                "human_validation_performed"):
        assert receipt[key] is False

@pytest.mark.parametrize("change", [
    {"freeze_blob": "a" * 40}, {"launch_blob": "b" * 40},
    {"bad_ancestry": True}, {"shallow": True}, {"bad_commit": True},
    {"source": b"{}"},
])
def test_invalid_git_lineage_rejected(tmp_path, monkeypatch, change):
    monkeypatch.setattr(audit, "_git", fake_git(**change))
    with pytest.raises(audit.TaskFreezeError):
        audit.audit(tmp_path)

def test_missing_git_not_an_accepted_history(tmp_path):
    with pytest.raises(audit.TaskFreezeError):
        audit._git(tmp_path, "show", "HEAD:missing-file")
