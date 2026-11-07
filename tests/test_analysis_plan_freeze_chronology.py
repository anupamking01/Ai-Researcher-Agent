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
    (tmp_path / "paper" / "MAIN_STUDY_INFERENCE.md").write_text(
        "Primary inference is limited to the three preregistered strict-support contrasts.\\n",
        encoding="utf-8",
    )
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "main_study_inference.json").write_text(
        '{"synthetic": true}\\n', encoding="utf-8"
    )
    publication = _commit(tmp_path, "publish-results", "frozen synthetic analysis\\n")
    (tmp_path / "paper" / "MAIN_STUDY_REPORTING_COVER.md").write_text(
        (Path(__file__).resolve().parents[1] / "paper" / "MAIN_STUDY_REPORTING_COVER.md")
        .read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "add reporting qualification")
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


def test_published_report_and_json_are_unchanged_with_committed_cover(history):
    root, milestones = history
    receipt = audit_history(root, milestones=milestones)
    assert receipt["canonical_publication_report_bytes_unchanged"] is True
    assert receipt["canonical_publication_inference_json_bytes_unchanged"] is True
    assert receipt["historical_report_contains_unqualified_preregistration_wording"] is True
    assert receipt["separate_committed_reporting_cover_checked"] is True
    assert len(receipt["original_publication_sha256_by_path"]) == 2
    assert len(receipt["reporting_cover_sha256"]) == 64
    assert receipt["prospective_precollection_analysis_preregistration_established"] is False


def test_rejects_working_copy_rewrite_of_historical_report(history):
    root, milestones = history
    (root / "paper" / "MAIN_STUDY_INFERENCE.md").write_text("new interpretation\\n")
    with pytest.raises(FreezeChronologyError, match="canonical publication/report bytes changed"):
        audit_history(root, milestones=milestones)


def test_rejects_committed_rewrite_of_canonical_result_json(history):
    root, milestones = history
    (root / "outputs" / "main_study_inference.json").write_text('{"selected": true}\\n')
    _git(root, "add", ".")
    _git(root, "commit", "-m", "replace frozen numeric result")
    with pytest.raises(FreezeChronologyError, match="canonical publication/report bytes changed"):
        audit_history(root, milestones=milestones)


def test_rejects_missing_or_symlinked_cover(history):
    root, milestones = history
    cover = root / "paper" / "MAIN_STUDY_REPORTING_COVER.md"
    cover.unlink()
    with pytest.raises(FreezeChronologyError, match="absent or oversized"):
        audit_history(root, milestones=milestones)
    cover.symlink_to(root / "paper" / "MAIN_STUDY_INFERENCE.md")
    with pytest.raises(FreezeChronologyError, match="symlink"):
        audit_history(root, milestones=milestones)


def test_rejects_cover_omitting_precollection_qualification(history):
    root, milestones = history
    cover = root / "paper" / "MAIN_STUDY_REPORTING_COVER.md"
    content = cover.read_text()
    content = content.replace(
        "prospective\nprecollection statistical preregistration is not established",
        "prospective\nprecollection preregistration is certain",
    )
    assert content != cover.read_text()
    cover.write_text(content)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "delete historical qualification")
    with pytest.raises(FreezeChronologyError, match="reporting cover lacks required claim"):
        audit_history(root, milestones=milestones)


def test_rejects_uncommitted_cover_rewrite(history):
    root, milestones = history
    cover = root / "paper" / "MAIN_STUDY_REPORTING_COVER.md"
    cover.write_text(cover.read_text() + "\\nunsaved clarification\\n")
    with pytest.raises(FreezeChronologyError, match="differs from committed HEAD"):
        audit_history(root, milestones=milestones)
