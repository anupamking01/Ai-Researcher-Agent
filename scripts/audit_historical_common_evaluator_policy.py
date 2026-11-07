"""Audit original versus recovery common-evaluator *source policy*, without scoring.

The first 37 cached evaluations and three recovered cells came from different
Git revisions. This source-only audit establishes what their pinned code and
workflow declarations share, and explicitly records a zero-evidence input-policy
difference. It cannot authenticate executions or historical report bytes.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

from scripts import audit_historical_design_source as history

ORIGINAL = "c3c15e46a8eec3a8bbc24c968eedc0548172a897"
RECOVERY = "8733ce492abc74e7b2966ed22ce08d3fddec43ca"
EVALUATOR_PATH = "scripts/evaluate_posthoc_support.py"
PROMPT_PATH = "logic/prompts.py"
NORMALIZER_PATH = "logic/experiment.py"
ORIGINAL_WORKFLOW = ".github/workflows/budget-main-study.yml"
RECOVERY_WORKFLOW = ".github/workflows/evaluator-recovery.yml"
# Independent GitHub Git-object identities, not reported experiment outcomes.
EXPECTED_BLOBS = {
    (ORIGINAL, EVALUATOR_PATH): "2480e2f478fdd9eb69dde8ce2dfa44253c3744c7",
    (RECOVERY, EVALUATOR_PATH): "fcb634bb6299d9cb91cbece968d109ddc9fd3b4b",
    (ORIGINAL, PROMPT_PATH): "1a2b893e5e37baf7f4d4572ac7f819e85d50945a",
    (RECOVERY, PROMPT_PATH): "1a2b893e5e37baf7f4d4572ac7f819e85d50945a",
    (ORIGINAL, NORMALIZER_PATH): "c98916c4a0aa17a94c38dd981489693bec5b87a7",
    (RECOVERY, NORMALIZER_PATH): "c98916c4a0aa17a94c38dd981489693bec5b87a7",
    (ORIGINAL, ORIGINAL_WORKFLOW): "3bf4387bd45a670334001f467a37dc8ad9e1cdd3",
    (RECOVERY, RECOVERY_WORKFLOW): "e5ef5a82ecc5cc0fc0337893bd2e82d147673098",
}

# Historical evaluator execution, usage and cost dependencies. These are
# source-level checks, not evidence about installed packages or API responses.
RUNTIME_DEPENDENCY_BLOBS = {
    "agent/llm_utils.py": "bbc8daec4ae972f26851195dc59dd0ca1966d865",
    "logic/usage.py": "336b7d96967395d368a962a751001f34b4fb8091",
    "settings/config.py": "943e126fa0e7dcd19179b4f6aec827ce0fcb42ba",
    "scripts/summarize_pilot.py": "08413f9d9ab7748cfed78c30ec1c189610c7fd14",
    "experiments/openai_pricing_2026-09-08.json": "7082f89c2a2adb7e8fa1f006971e91f5ef84d282",
    "requirements.txt": "ce750159fc65f1bd533c02891fd68177b5df324a",
    "requirements-dev.txt": "fe93bd52ff68a801a663ec88fcde541a906b6f9c",
}
EXPECTED_BLOBS.update({
    (commit, path): blob_sha
    for commit in (ORIGINAL, RECOVERY)
    for path, blob_sha in RUNTIME_DEPENDENCY_BLOBS.items()
})

class HistoricalEvaluatorPolicyError(ValueError):
    """The frozen Git source does not support the stated evaluator provenance."""

def _parse(raw: bytes) -> ast.Module:
    try:
        return ast.parse(raw.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise HistoricalEvaluatorPolicyError("evaluator source must be UTF-8 Python") from exc

def _call_signature(main: ast.FunctionDef, name: str, expected: str) -> str:
    calls = [node for node in ast.walk(main)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == name]
    expected_node = ast.parse(expected, mode="eval").body
    if len(calls) != 1 or ast.dump(calls[0]) != ast.dump(expected_node):
        raise HistoricalEvaluatorPolicyError(f"unexpected {name} evaluator call")
    return ast.dump(calls[0], include_attributes=False)

def inspect_evaluator(raw: bytes, *, recovered: bool) -> dict:
    """Verify a narrow, explicit common prompt/model/scorer *call* contract."""
    module = _parse(raw)
    caps = [node.value for node in module.body if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "MAX_CLAIMS"
                    for t in node.targets)]
    if (len(caps) != 1 or not isinstance(caps[0], ast.Constant)
            or type(caps[0].value) is not int or caps[0].value != 12):
        raise HistoricalEvaluatorPolicyError("historical evaluator claim cap is not 12")
    mains = [node for node in module.body if isinstance(node, ast.FunctionDef)
             and node.name == "main"]
    if len(mains) != 1:
        raise HistoricalEvaluatorPolicyError("missing unique evaluator main")
    main = mains[0]
    signatures = {
        "prompt": _call_signature(
            main, "generate_verification_prompt",
            'generate_verification_prompt(str(trace.get("question", "")), report, evidence, max_claims=MAX_CLAIMS)',
        ),
        "model": _call_signature(
            main, "create_chat_completion",
            'create_chat_completion(model=os.environ["SMART_LLM_MODEL"], messages=[{"role": "user", "content": prompt}], usage_tracker=tracker, request_timeout_seconds=120)',
        ),
        "normalizer": _call_signature(
            main, "normalize_verifier_output", "normalize_verifier_output(raw)",
        ),
    }
    # The recovery script admits genuinely zero-successful-source traces with
    # an explicit no-evidence sentinel. The original script instead rejected
    # empty research context. These are *different input policies*.
    expected = (
        "evidence, evidence_status = _evidence_for_trace(trace, variant, task_id, run_id)"
        if recovered else "evidence = _research_context(run_id)"
    )
    pattern = ast.parse(expected).body[0]
    if sum(ast.dump(node) == ast.dump(pattern)
           for node in ast.walk(main) if isinstance(node, ast.Assign)) != 1:
        raise HistoricalEvaluatorPolicyError("unexpected historical evidence selection")
    if recovered:
        helpers = [node for node in module.body if isinstance(node, ast.FunctionDef)
                   and node.name == "_evidence_for_trace"]
        if len(helpers) != 1:
            raise HistoricalEvaluatorPolicyError("missing recovery zero-evidence helper")
        helper = helpers[0]
        sentinel = ast.parse('return NO_EVIDENCE_SENTINEL, "zero_successful_sources"').body[0]
        matches = [node for node in ast.walk(helper) if isinstance(node, ast.Return)
                   and ast.dump(node) == ast.dump(sentinel)]
        tests = [node for node in ast.walk(helper) if isinstance(node, ast.Compare)
                 and ast.dump(node) == ast.dump(
                     ast.parse("successful_sources == 0", mode="eval").body)]
        if len(matches) != 1 or len(tests) != 1:
            raise HistoricalEvaluatorPolicyError("recovery zero-source condition changed")
        constants = [node.value for node in module.body if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "NO_EVIDENCE_SENTINEL"
                             for t in node.targets)]
        if (len(constants) != 1 or not isinstance(constants[0], ast.Constant)
                or type(constants[0].value) is not str
                or "Do not use outside knowledge" not in constants[0].value):
            raise HistoricalEvaluatorPolicyError("recovery sentinel no longer forbids outside knowledge")
    else:
        reject = ast.parse("not evidence.strip()", mode="eval").body
        checks = [node for node in ast.walk(main) if isinstance(node, ast.If)
                  and ast.dump(node.test) == ast.dump(reject)
                  and any(isinstance(child, ast.Raise) for child in node.body)]
        if len(checks) != 1:
            raise HistoricalEvaluatorPolicyError("original empty-evidence rejection absent")
    return signatures

def inspect_workflow(raw: bytes, *, recovered: bool) -> None:
    """Read declared workflow model, temperature, evaluator invocation and source."""
    try:
        workflow = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HistoricalEvaluatorPolicyError("workflow must be UTF-8") from exc
    for label, pattern in (
        ("model", r"(?m)^\s*SMART_LLM_MODEL:\s*gpt-5\.6-terra\s*$"),
        ("temperature", r'(?m)^\s*TEMPERATURE:\s*"?1"?\s*$'),
        ("evaluator command",
         r"(?m)^\s*run:\s*python scripts/evaluate_posthoc_support\.py --max-evaluator-cost-usd 1\.25\s*$"),
    ):
        if len(re.findall(pattern, workflow)) != 1:
            raise HistoricalEvaluatorPolicyError(f"historical workflow {label} changed")
    # Both launch workflows must install the same pinned source dependencies.
    for dependency in ("requirements.txt", "requirements-dev.txt"):
        if len(re.findall(
            rf"(?m)^\\s*pip install -r {re.escape(dependency)}\\s*$", workflow,
        )) != 1:
            raise HistoricalEvaluatorPolicyError(f"historical workflow install drift: {dependency}")
    if recovered:
        if ("run-id: 34620917346" not in workflow
                or "name: budget-main-study-34620917346" not in workflow
                or "len(evals) != 37" not in workflow
                or "expected_missing = [('P6V','main-02'), ('P6V','main-08'), ('P6V','main-10')]" not in workflow):
            raise HistoricalEvaluatorPolicyError("recovery source lacks original 37+3 provenance gate")
        if re.search(r"(?m)^\s*run:\s*python scripts/run_budget_main_study\.py\b", workflow):
            raise HistoricalEvaluatorPolicyError("recovery workflow may not run treatments")
    elif not re.search(
        r"(?m)^\s*run:\s*python scripts/run_budget_main_study\.py --max-agent-cost-usd 3\.00\s*$",
        workflow,
    ):
        raise HistoricalEvaluatorPolicyError("original workflow lacks treatment invocation")

def inspect_shared_runtime_dependencies(sources: dict[tuple[str, str], bytes]) -> dict[str, str]:
    """Check independently pinned dependencies and return their SHA-256 hashes.

    Comparing Git sources rules out *source drift* between the two historical
    revisions. It does not prove which package wheels or provider versions ran.
    """
    fingerprints: dict[str, str] = {}
    for path in RUNTIME_DEPENDENCY_BLOBS:
        original = sources.get((ORIGINAL, path))
        recovered = sources.get((RECOVERY, path))
        if (not isinstance(original, bytes) or not original
                or not isinstance(recovered, bytes) or original != recovered):
            raise HistoricalEvaluatorPolicyError(
                f"historical evaluator runtime dependency source drift: {path}"
            )
        fingerprints[path] = hashlib.sha256(original).hexdigest()
    try:
        requirement_lines = sources[(ORIGINAL, "requirements.txt")].decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise HistoricalEvaluatorPolicyError("historical requirements are not UTF-8") from exc
    provider_pins = [line.strip() for line in requirement_lines
                     if line.strip().lower().startswith("openai")]
    if provider_pins != ["openai==0.27.10"]:
        raise HistoricalEvaluatorPolicyError("historical OpenAI client pin changed")
    return fingerprints


def audit_checkout(root: Path) -> dict:
    root = root.resolve()
    history.audit_checkout(root)  # full history, root, original runner identity
    history._git(root, "merge-base", "--is-ancestor", ORIGINAL, RECOVERY)
    history._git(root, "merge-base", "--is-ancestor", RECOVERY, "HEAD")
    sources: dict[tuple[str, str], bytes] = {}
    for (commit, path), expected_sha in EXPECTED_BLOBS.items():
        observed = history._git(root, "rev-parse", f"{commit}:{path}").decode().strip()
        if observed != expected_sha:
            raise HistoricalEvaluatorPolicyError(f"historical source blob mismatch: {commit[:8]}:{path}")
        source = history._git(root, "show", f"{commit}:{path}")
        if not source:
            raise HistoricalEvaluatorPolicyError("historical source is empty")
        sources[(commit, path)] = source
    original_core = inspect_evaluator(sources[(ORIGINAL, EVALUATOR_PATH)], recovered=False)
    recovery_core = inspect_evaluator(sources[(RECOVERY, EVALUATOR_PATH)], recovered=True)
    if original_core != recovery_core:
        raise HistoricalEvaluatorPolicyError("common evaluator prompt/model/normalizer call changed")
    if sources[(ORIGINAL, PROMPT_PATH)] != sources[(RECOVERY, PROMPT_PATH)]:
        raise HistoricalEvaluatorPolicyError("prompt-generator bytes changed between phases")
    if sources[(ORIGINAL, NORMALIZER_PATH)] != sources[(RECOVERY, NORMALIZER_PATH)]:
        raise HistoricalEvaluatorPolicyError("score-normalizer bytes changed between phases")
    inspect_workflow(sources[(ORIGINAL, ORIGINAL_WORKFLOW)], recovered=False)
    inspect_workflow(sources[(RECOVERY, RECOVERY_WORKFLOW)], recovered=True)
    runtime_fingerprints = inspect_shared_runtime_dependencies(sources)
    return {
        "schema_version": 1,
        "status": "pinned_historical_evaluator_source_policy_comparison_only",
        "historical_treatment_commit": ORIGINAL,
        "historical_evaluator_recovery_commit": RECOVERY,
        "source_blob_shas": {f"{commit[:8]}:{path}": sha
                             for (commit, path), sha in sorted(EXPECTED_BLOBS.items())},
        "historical_prompt_sha256": hashlib.sha256(sources[(ORIGINAL, PROMPT_PATH)]).hexdigest(),
        "historical_normalizer_sha256": hashlib.sha256(sources[(ORIGINAL, NORMALIZER_PATH)]).hexdigest(),
        "declared_common_model": "gpt-5.6-terra",
        "declared_common_temperature": 1,
        "declared_claim_cap": 12,
        "prompt_generator_bytes_identical": True,
        "score_normalizer_bytes_identical": True,
        "evaluator_core_call_ast_identical": True,
        "shared_runtime_dependency_bytes_identical": True,
        "shared_runtime_source_sha256": runtime_fingerprints,
        "historical_installed_package_versions_authenticated": False,
        "historical_provider_execution_authenticated": False,
        "original_empty_evidence_rejected": True,
        "recovery_zero_successful_source_sentinel_added": True,
        "entire_evaluator_input_policy_identical": False,
        "historical_execution_authenticated": False,
        "original_37_evaluations_authenticated": False,
        "recovered_3_evaluations_authenticated": False,
        "per_cell_evidence_status_authenticated": False,
        "equal_evaluator_outputs_established": False,
        "human_validation_performed": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(json.dumps(audit_checkout(args.root), sort_keys=True, indent=2))
    except (HistoricalEvaluatorPolicyError, history.HistoricalDesignSourceError) as exc:
        parser.exit(1, f"historical evaluator policy audit failed: {exc}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
