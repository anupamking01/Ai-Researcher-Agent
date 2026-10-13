"""Fail closed unless automated and human analyses are ready for reconciliation.

This preflight computes no reconciliation result, creates no ratings, reruns no
treatments/evaluators, and adds no human-validation hypothesis tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

from scripts import analyze_main_study
from scripts import human_eval_analysis_core as human_core
from scripts import verify_analysis_provenance
from scripts import verify_human_eval_analysis_outputs
from scripts import verify_main_study_execution
from scripts import verify_main_study_outputs

ROOT = Path(__file__).resolve().parents[1]
AUTO_JSON = Path("outputs/main_study_inference.json")
AUTO_PROV = Path("outputs/main_study_analysis_provenance.json")
HUMAN_ROOT = Path("outputs/human_eval/analysis-v1")
CONTRACT = Path("paper/HUMAN_RECONCILIATION_FREEZE.md")
FROZEN_RECONCILIATION_CONTRACT_SHA256 = (
    "3732fb7a231e3be88935d469ab4c39f454a4d0d2adfcfed7e40298889b5a90aa"
)
FROZEN_LEGACY_AUTOMATED_PROVENANCE_SHA256 = (
    "73f12a725f3cf4d27748a95e1f380ca5cfcac3b8fdd5adeda7abaa2f3f6e10e0"
)
STUDY = "budget-main-v1"
CONTRASTS = tuple(name for _, _, name in analyze_main_study.PRIMARY_CONTRASTS)
DIMS = tuple(human_core.DIMS)


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _regular_bytes(path, label):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _load(content, label):
    def unique_object_pairs(pairs):
        value = {}
        for key, member in pairs:
            if key in value:
                raise ValueError(f"{label} contains duplicate JSON key {key!r}")
            value[key] = member
        return value

    try:
        value = json.loads(
            content.decode("utf-8"), object_pairs_hook=unique_object_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    _require(isinstance(value, dict), f"{label} must contain an object")
    return value


def _fingerprint(content):
    return {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _task_ids(payload, label):
    tasks = payload.get("task_ids")
    _require(isinstance(tasks, list) and tasks, f"{label} task_ids must be non-empty")
    _require(all(isinstance(x, str) and x for x in tasks), f"{label} task_ids invalid")
    _require(len(tasks) == len(set(tasks)), f"{label} task_ids must be unique")
    _require(payload.get("n_tasks") == len(tasks), f"{label} n_tasks mismatch")
    return tasks


def _validate_summary(result, diffs, label):
    _require(result.get("n_pairs") == len(diffs), f"{label} n_pairs mismatch")
    _require(result.get("positive_tasks") == sum(x > 0 for x in diffs), f"{label} positive count mismatch")
    _require(result.get("negative_tasks") == sum(x < 0 for x in diffs), f"{label} negative count mismatch")
    _require(result.get("tied_tasks") == sum(x == 0 for x in diffs), f"{label} tie count mismatch")
    if diffs:
        actual = _number(result.get("mean_difference"), f"{label} mean_difference")
        _require(
            math.isclose(actual, statistics.mean(diffs), rel_tol=0.0, abs_tol=1e-12),
            f"{label} mean_difference inconsistent with task differences",
        )
    else:
        _require(result.get("mean_difference") is None, f"{label} empty mean must be null")


def validate_payloads(automated, human):
    """Validate the frozen cross-analysis identity without comparing outcomes."""
    _require(automated.get("schema_version") == 1, "automated schema mismatch")
    _require(automated.get("study_id") == STUDY, "automated study mismatch")
    _require(
        automated.get("primary_outcome") == "strict_support_rate",
        "automated measure must be strict_support_rate",
    )
    tasks = _task_ids(automated, "automated")
    _require(
        len(tasks) == analyze_main_study.EXPECTED_TASKS,
        "frozen task count mismatch",
    )
    primary = automated.get("primary_contrasts")
    _require(
        isinstance(primary, dict) and set(primary) == set(CONTRASTS),
        "automated contrast set mismatch",
    )
    for name in CONTRASTS:
        result = primary[name]
        raw = result.get("task_differences")
        _require(
            isinstance(raw, list) and len(raw) == len(tasks),
            f"automated {name} task differences mismatch",
        )
        diffs = [_number(x, f"automated {name} difference") for x in raw]
        _validate_summary(result, diffs, f"automated {name}")

    expected = {
        "schema_version": 1,
        "study_id": STUDY,
        "status": "human_validation_analysis",
        "analysis_scope": "complementary_not_main_confirmatory",
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests": "none_predeclared_for_human_validation",
    }
    for key, value in expected.items():
        _require(human.get(key) == value, f"human {key} mismatch")
    human_tasks = _task_ids(human, "human")
    _require(human_tasks == tasks, "ordered task identity mismatch")
    _require(human.get("dimensions") == list(DIMS), "human dimension set/order mismatch")
    paired = human.get("paired_contrasts")
    _require(
        isinstance(paired, dict) and set(paired) == set(CONTRASTS),
        "human contrast set mismatch",
    )

    all_tasks = set(tasks)
    for name in CONTRASTS:
        block = paired[name]
        _require(
            isinstance(block, dict) and set(block) == set(DIMS),
            f"human {name} dimensions mismatch",
        )
        for dimension in DIMS:
            result = block[dimension]
            included = result.get("task_ids_included")
            missing = result.get("missing_pair_tasks")
            _require(
                isinstance(included, list) and isinstance(missing, list),
                f"human {name}/{dimension} must declare included/missing tasks",
            )
            inc, miss = set(included), set(missing)
            _require(
                len(included) == len(inc) and len(missing) == len(miss),
                f"human {name}/{dimension} duplicate task ids",
            )
            _require(
                inc.isdisjoint(miss) and inc | miss == all_tasks,
                f"human {name}/{dimension} included/missing tasks must partition frozen tasks",
            )
            _require(
                included == [x for x in tasks if x in inc]
                and missing == [x for x in tasks if x in miss],
                f"human {name}/{dimension} task order mismatch",
            )
            task_diffs = result.get("task_differences")
            _require(
                isinstance(task_diffs, dict) and set(task_diffs) == inc,
                f"human {name}/{dimension} task differences mismatch",
            )
            diffs = [
                _number(task_diffs[task], f"human {name}/{dimension}/{task}")
                for task in included
            ]
            _validate_summary(result, diffs, f"human {name}/{dimension}")

    return {
        "schema_version": 1,
        "study_id": STUDY,
        "status": "automated_human_reconciliation_identity_valid",
        "analysis_scope": "descriptive_reconciliation_only",
        "primary_outcome": "strict_support_rate",
        "human_dimensions": list(DIMS),
        "contrasts": list(CONTRASTS),
        "task_ids": tasks,
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests_added": False,
    }


def _verify_human_analysis_bundle(human_root, *, root):
    """Recompute the human bundle using only the selected checkout's inputs."""
    root = Path(root)
    packet_root = root / "outputs" / "human_eval"
    return verify_human_eval_analysis_outputs.verify_bundle_against_inputs(
        human_root,
        freeze_root=packet_root / "frozen-v1",
        packet_root=packet_root,
        packet_path=packet_root / "packet.jsonl",
        protocol_path=root / "paper" / "HUMAN_EVAL_PROTOCOL.md",
        assignment_plan_path=root / "paper" / "HUMAN_EVAL_ASSIGNMENT_PLAN.md",
        analysis_plan_path=root / "paper" / "HUMAN_EVAL_ANALYSIS_PLAN.md",
        task_manifest_path=root / "experiments" / "main_budget_tasks.json",
        repo_root=root,
    )


def _verify_automated_provenance(content: bytes, *, root: Path) -> None:
    """Require execution binding when present; retain the preserved legacy path."""
    receipt = _load(content, "automated provenance")
    if "verified_execution" in receipt:
        verify_main_study_execution.verify_execution_receipt(receipt, root=root)
        return
    if hashlib.sha256(content).hexdigest() != FROZEN_LEGACY_AUTOMATED_PROVENANCE_SHA256:
        raise ValueError(
            "automated provenance is missing verified_execution and does not match "
            "the pinned preserved legacy receipt"
        )
    verify_analysis_provenance.verify_receipt(receipt, root=root)


def verify_readiness(root=ROOT, human_root=None, contract=None):
    """Verify both canonical bundles and return a source-bound readiness receipt."""
    root = Path(root)
    human_root = Path(human_root) if human_root else root / HUMAN_ROOT
    contract = Path(contract) if contract else root / CONTRACT
    contract_content = _regular_bytes(contract, "reconciliation_contract")
    contract_sha256 = hashlib.sha256(contract_content).hexdigest()
    if contract_sha256 != FROZEN_RECONCILIATION_CONTRACT_SHA256:
        raise ValueError(
            "frozen reconciliation contract fingerprint mismatch: "
            f"expected {FROZEN_RECONCILIATION_CONTRACT_SHA256}, got {contract_sha256}"
        )
    paths = {
        "reconciliation_contract": contract,
        "automated_analysis": root / AUTO_JSON,
        "automated_provenance": root / AUTO_PROV,
        "human_analysis": human_root / "analysis.json",
        "human_manifest": human_root / "analysis_manifest.json",
    }
    before = {"reconciliation_contract": contract_content}
    before.update(
        {
            name: _regular_bytes(path, name)
            for name, path in paths.items()
            if name != "reconciliation_contract"
        }
    )

    _verify_automated_provenance(before["automated_provenance"], root=root)
    verify_main_study_outputs.verify_outputs(root=root)
    human_verification = _verify_human_analysis_bundle(human_root, root=root)

    after = {name: _regular_bytes(path, name) for name, path in paths.items()}
    for name in paths:
        _require(before[name] == after[name], f"{name} changed during verification")

    receipt = validate_payloads(
        _load(before["automated_analysis"], "automated analysis"),
        _load(before["human_analysis"], "human analysis"),
    )
    receipt["verified_input_fingerprints"] = {
        name: _fingerprint(data) for name, data in before.items()
    }
    receipt["verification"] = {
        "automated_provenance_verified": True,
        "automated_output_consistency_verified": True,
        "human_analysis_bundle_verified": True,
        "human_analysis_independently_recomputed": human_verification.get(
            "independent_recomputation_verified"
        )
        is True,
        "cross_analysis_identity_verified": True,
        "inputs_stable_during_verification": True,
    }
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--human-root", type=Path)
    parser.add_argument("--contract", type=Path)
    args = parser.parse_args()
    try:
        receipt = verify_readiness(args.root, args.human_root, args.contract)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN RECONCILIATION READINESS: FAIL: {exc}") from exc
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("HUMAN RECONCILIATION READINESS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
