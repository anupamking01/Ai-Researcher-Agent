"""Guard frozen design and published analysis across both real archive audits.

These CI contracts ensure the workflows fail closed on branch-side drift
before they verify an older, pinned source tree. They do not run treatments.
"""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ".github/workflows/retained-canonical-archive-audit.yml",
    ".github/workflows/preserved-canonical-package-audit.yml",
)
FROZEN_DESIGN = {
    "experiments/main_budget_tasks.json",
    "experiments/openai_pricing_2026-09-08.json",
    "paper/ANALYSIS_PLAN.md",
}
PUBLISHED_ANALYSIS = {
    "outputs/canonical_analysis_source.json",
    "outputs/main_study_analysis_inputs_manifest.json",
    "outputs/main_study_inference.json",
    "outputs/main_study_runs.csv",
    "outputs/posthoc_support_runs.csv",
    "paper/MAIN_STUDY_INFERENCE.md",
}
BOUND = FROZEN_DESIGN | PUBLISHED_ANALYSIS
PINNED_ANALYSIS_REVISION = "f333623380526fa05dcb14110e7ec1fb72d2d0e2"


@pytest.mark.parametrize("path", WORKFLOWS)
def test_real_retained_audits_reject_frozen_design_drift(path):
    workflow = (ROOT / path).read_text(encoding="utf-8")
    assert PINNED_ANALYSIS_REVISION in workflow
    assert 'git -C "$frozen" rev-parse HEAD' in workflow

    # A change to any frozen control or published scientific file must cause
    # the real-source archive audit to execute, not merely the unit tests.
    assert "    paths:\n" in workflow
    watched = workflow.split("    paths:\n", 1)[1].split("\npermissions:", 1)[0]
    watched_paths = {
        line.strip()[2:] for line in watched.splitlines()
        if line.strip().startswith("- ")
    }
    assert BOUND <= watched_paths

    # The comparison must take place before downloading the retained ZIP,
    # so a changed protocol cannot be laundered through old evidence.
    assert "for relative in \\" in workflow
    loop = workflow.split("for relative in \\", 1)[1].split("; do", 1)[0]
    compared = {
        line.strip().removesuffix("\\").strip()
        for line in loop.splitlines() if line.strip()
    }
    assert compared == BOUND
    assert workflow.index("for relative in \\") < workflow.index("cmp --")
    assert workflow.index("cmp --") < workflow.index("      - name: Download")
    assert "run_budget_main_study" not in workflow
    assert "run_pilot" not in workflow
    assert "OPENAI_API_KEY" not in workflow
