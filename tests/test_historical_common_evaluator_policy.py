"""Synthetic, outcome-free regressions for historical common-evaluator source audit."""
from __future__ import annotations
import pytest
from scripts import audit_historical_common_evaluator_policy as audit

CORE = '''
MAX_CLAIMS = 12
def main():
    evidence = _research_context(run_id)
    if not evidence.strip():
        raise SystemExit("empty")
    prompt = generate_verification_prompt(str(trace.get("question", "")), report, evidence, max_claims=MAX_CLAIMS)
    raw = create_chat_completion(model=os.environ["SMART_LLM_MODEL"], messages=[{"role": "user", "content": prompt}], usage_tracker=tracker, request_timeout_seconds=120)
    result = normalize_verifier_output(raw)
'''
RECOVERY = '''
MAX_CLAIMS = 12
NO_EVIDENCE_SENTINEL = "The run recorded zero successful sources. Do not use outside knowledge."
def _evidence_for_trace(trace, variant, task_id, run_id):
    if evidence.strip():
        return evidence, "retrieved_evidence"
    if successful_sources == 0:
        return NO_EVIDENCE_SENTINEL, "zero_successful_sources"
    raise SystemExit("missing source")
def main():
    evidence, evidence_status = _evidence_for_trace(trace, variant, task_id, run_id)
    prompt = generate_verification_prompt(str(trace.get("question", "")), report, evidence, max_claims=MAX_CLAIMS)
    raw = create_chat_completion(model=os.environ["SMART_LLM_MODEL"], messages=[{"role": "user", "content": prompt}], usage_tracker=tracker, request_timeout_seconds=120)
    result = normalize_verifier_output(raw)
'''
WORKFLOW = '''
jobs:
  study:
    env:
      SMART_LLM_MODEL: gpt-5.6-terra
      TEMPERATURE: "1"
    steps:
      - run: python scripts/run_budget_main_study.py --max-agent-cost-usd 3.00
      - run: python scripts/evaluate_posthoc_support.py --max-evaluator-cost-usd 1.25
'''
RECOVERY_WORKFLOW = '''
jobs:
  recover:
    env:
      SMART_LLM_MODEL: gpt-5.6-terra
      TEMPERATURE: "1"
    steps:
      - name: budget-main-study-34620917346
        with:
          run-id: 34620917346
      - run: python scripts/evaluate_posthoc_support.py --max-evaluator-cost-usd 1.25
      - run: |
          if len(evals) != 37:
              pass
          expected_missing = [('P6V','main-02'), ('P6V','main-08'), ('P6V','main-10')]
'''

def test_shared_core_calls_have_same_ast():
    assert audit.inspect_evaluator(CORE.encode(), recovered=False) == audit.inspect_evaluator(RECOVERY.encode(), recovered=True)

@pytest.mark.parametrize("mutated", [
    CORE.replace("MAX_CLAIMS = 12", "MAX_CLAIMS = 20"),
    CORE.replace('max_claims=MAX_CLAIMS', 'max_claims=20'),
    CORE.replace('model=os.environ["SMART_LLM_MODEL"]', 'model="other-model"'),
    CORE.replace('"role": "user"', '"role": "system"'),
    CORE.replace('normalize_verifier_output(raw)', 'normalize_verifier_output(prompt)'),
    CORE.replace('if not evidence.strip():', 'if evidence.strip():'),
])
def test_original_policy_drift_rejected(mutated):
    with pytest.raises(audit.HistoricalEvaluatorPolicyError):
        audit.inspect_evaluator(mutated.encode(), recovered=False)

@pytest.mark.parametrize("mutated", [
    RECOVERY.replace('successful_sources == 0', 'successful_sources < 0'),
    RECOVERY.replace('"zero_successful_sources"', '"missing"'),
    RECOVERY.replace('Do not use outside knowledge.', 'Use background knowledge.'),
    RECOVERY.replace('_evidence_for_trace(trace, variant, task_id, run_id)',
                     '_research_context(run_id)'),
])
def test_recovery_policy_drift_rejected(mutated):
    with pytest.raises(audit.HistoricalEvaluatorPolicyError):
        audit.inspect_evaluator(mutated.encode(), recovered=True)

def test_workflows_match_declared_core_and_different_purposes():
    audit.inspect_workflow(WORKFLOW.encode(), recovered=False)
    audit.inspect_workflow(RECOVERY_WORKFLOW.encode(), recovered=True)

@pytest.mark.parametrize("mutated,recovered", [
    (WORKFLOW.replace("gpt-5.6-terra", "gpt-5.6-luna"), False),
    (WORKFLOW.replace('TEMPERATURE: "1"', 'TEMPERATURE: "0"'), False),
    (WORKFLOW.replace("--max-evaluator-cost-usd 1.25", "--max-evaluator-cost-usd 2"), False),
    (RECOVERY_WORKFLOW.replace("len(evals) != 37", "len(evals) != 36"), True),
    (RECOVERY_WORKFLOW + "\n      - run: python scripts/run_budget_main_study.py --max-agent-cost-usd 3.00\n", True),
])
def test_invalid_workflow_drift_rejected(mutated, recovered):
    with pytest.raises(audit.HistoricalEvaluatorPolicyError):
        audit.inspect_workflow(mutated.encode(), recovered=recovered)

def test_checkout_fail_closed_on_substituted_git_blob(tmp_path, monkeypatch):
    monkeypatch.setattr(audit.history, "audit_checkout", lambda root: {})
    monkeypatch.setattr(audit.history, "_git", lambda *args: b"0" * 40)
    with pytest.raises(audit.HistoricalEvaluatorPolicyError, match="blob mismatch"):
        audit.audit_checkout(tmp_path)
