"""Synthetic Git history tests; no treatment, evaluator or network execution."""

from dataclasses import replace
from pathlib import Path
import subprocess

import pytest

from scripts.audit_analysis_plan_freeze_chronology import (
    FreezeChronologyError,
    Milestones,
    audit_history,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _commit(root: Path, name: str, content: str) -> str:
    path = root / "paper" / "ANALYSIS_PLAN.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "--allow-empty", "-m", name)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def history(tmp_path: Path) -> tuple[Path, Milestones]:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Synthetic Research Tester")
    _git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    prior = _commit(tmp_path, "prior-protocol", "draft protocol placeholder\n")
    treatment = _commit(tmp_path, "treatments", "draft protocol placeholder\n")
    recovery = _commit(tmp_path, "evaluator-recovery", "draft protocol placeholder\n")
    plan = _commit(tmp_path, "freeze-inference", "frozen synthetic analysis\n")
    publication = _commit(tmp_path, "publish-results", "frozen synthetic analysis\n")
    return tmp_path, Milestones(prior, treatment, recovery, plan, publication)


def test_good_history_is_explicitly_nonprospective(history):
    root, milestones = history
    result = audit_history(root, milestones=milestones)
    assert result["status"] == "verified_git_history_sequence_not_outcome_blinding"
    assert result["prospective_precollection_analysis_preregistration_established"] is False
    assert result["pre_analysis_outcome_blinding_established"] is False
    assert result["original_treatment_authenticity_established"] is False
    assert result["human_validation_performed"] is False


def test_rejects_reordered_plan_and_evaluator(history):
    root, milestones = history
    inverted = replace(milestones, evaluator_recovery=milestones.analysis_plan,
                       analysis_plan=milestones.evaluator_recovery)
    with pytest.raises(FreezeChronologyError, match="historical order"):
        audit_history(root, milestones=inverted)


def test_rejects_uncommitted_plan_change(history):
    root, milestones = history
    (root / "paper" / "ANALYSIS_PLAN.md").write_text("changed!\n")
    with pytest.raises(FreezeChronologyError, match="bytes have changed"):
        audit_history(root, milestones=milestones)


def test_rejects_committed_plan_change(history):
    root, milestones = history
    _commit(root, "unauthorized-change", "changed!\n")
    with pytest.raises(FreezeChronologyError, match="bytes have changed"):
        audit_history(root, milestones=milestones)


def test_rejects_missing_historical_commit(history):
    root, milestones = history
    with pytest.raises(FreezeChronologyError, match="complete, authentic local Git history"):
        audit_history(root, milestones=replace(milestones, treatment="0" * 40))


def test_rejects_non_repository_root(history):
    root, milestones = history
    (root / "nested").mkdir()
    with pytest.raises(FreezeChronologyError, match="repository root"):
        audit_history(root / "nested", milestones=milestones)


def test_rejects_symlinked_plan(history):
    root, milestones = history
    plan = root / "paper" / "ANALYSIS_PLAN.md"
    target = root / "other.md"
    target.write_bytes(plan.read_bytes())
    plan.unlink()
    plan.symlink_to(target)
    with pytest.raises(FreezeChronologyError, match="regular file"):
        audit_history(root, milestones=milestones)


def test_rejects_checkout_without_canonical_publication(history):
    root, milestones = history
    _git(root, "checkout", "--quiet", milestones.analysis_plan)
    with pytest.raises(FreezeChronologyError, match="does not descend"):
        audit_history(root, milestones=milestones)


def test_rejects_shallow_history_even_when_current_plan_is_present(history, tmp_path):
    root, milestones = history
    shallow = tmp_path.parent / f"{tmp_path.name}-shallow-copy"
    subprocess.run(
        ["git", "clone", "--quiet", "--depth", "1", root.as_uri(), str(shallow)],
        check=True,
    )
    assert _git(shallow, "rev-parse", "--is-shallow-repository") == "true"
    with pytest.raises(FreezeChronologyError, match="non-shallow"):
        audit_history(shallow, milestones=milestones)
