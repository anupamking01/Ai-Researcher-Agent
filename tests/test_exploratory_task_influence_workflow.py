"""Guard that offline canonical task-influence evidence is generated and checked
before the workflow uploads its standalone exploratory artifact.
"""
from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[1] /
            ".github/workflows/exploratory-pareto-stability.yml")


def test_task_influence_uses_retained_canonical_worktree_and_is_checked_before_upload():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "git worktree add --detach" in text
    assert 'RECEIPT_IMPLEMENTATION_COMMIT="f333623380526fa05dcb14110e7ec1fb72d2d0e2"' in text
    assert "scripts/analyze_main_study_task_influence.py" in text
    assert "scripts/verify_main_study_task_influence_artifact.py" in text
    producer = text.index("python -m scripts.analyze_main_study_task_influence")
    checker = text.index("python -m scripts.verify_main_study_task_influence_artifact")
    upload = text.index("name: vera-task-influence-")
    assert producer < checker < upload
    assert "python -m scripts.run_budget_main_study" not in text
    assert "python -m scripts.evaluate_posthoc_support" not in text
    assert "OPENAI_API_KEY" not in text


def test_task_artifact_has_an_independent_receipt_and_fails_on_missing_files():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "TASK_AUDIT_PATH:" in text
    assert "TASK_RECEIPT_PATH:" in text
    assert "task_influence_diagnostic_sha256" not in text or (
        "scripts/verify_main_study_task_influence_artifact" in text
    )
    assert "if-no-files-found: error" in text
    assert "retention-days: 90" in text
    assert "docs/MAIN_STUDY_TASK_INFLUENCE.md" in text
