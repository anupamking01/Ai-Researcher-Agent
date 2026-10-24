"""Fail closed unless automated and human analyses are ready for reconciliation.

This preflight computes no reconciliation result, creates no ratings, reruns no
treatments/evaluators, and adds no human-validation hypothesis tests.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import statistics
import stat
from contextlib import ExitStack, contextmanager
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


def _snapshot_regular_descriptor(descriptor: int, *, label: str):
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} must be a regular file")
    chunks = []
    offset = 0
    while True:
        chunk = os.pread(descriptor, 1024 * 1024, offset)
        if not chunk:
            break
        chunks.append(chunk)
        offset += len(chunk)
    after = os.fstat(descriptor)
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity:
        raise ValueError(f"{label} changed while it was being read")
    return b"".join(chunks), after_identity


def _open_bound_input(stack: ExitStack, path: Path, *, label: str):
    path = Path(path)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parent_descriptor = os.open(path.parent, directory_flags)
    except OSError as exc:
        raise ValueError(
            f"{label} parent must be a regular directory: {path.parent}"
        ) from exc
    stack.callback(os.close, parent_descriptor)
    parent = os.fstat(parent_descriptor)
    if not stat.S_ISDIR(parent.st_mode):
        raise ValueError(
            f"{label} parent must be a regular directory: {path.parent}"
        )

    file_flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    file_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path.name, file_flags, dir_fd=parent_descriptor)
    except OSError as exc:
        raise ValueError(f"{label} must be a regular file: {path}") from exc
    stack.callback(os.close, descriptor)
    content, identity = _snapshot_regular_descriptor(descriptor, label=label)
    return {
        "path": path,
        "parent_descriptor": parent_descriptor,
        "parent_identity": (parent.st_dev, parent.st_ino),
        "descriptor": descriptor,
        "content": content,
        "identity": identity,
    }


def _require_bound_input_stable(snapshot, *, label: str):
    path = snapshot["path"]
    content, identity = _snapshot_regular_descriptor(
        snapshot["descriptor"],
        label=label,
    )
    if content != snapshot["content"] or identity != snapshot["identity"]:
        raise ValueError(f"{label} changed during verification")
    try:
        current = os.stat(
            path.name,
            dir_fd=snapshot["parent_descriptor"],
            follow_symlinks=False,
        )
        parent_current = os.stat(path.parent, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(f"{label} changed during verification") from exc
    if (
        not stat.S_ISREG(current.st_mode)
        or (current.st_dev, current.st_ino) != identity[:2]
        or not stat.S_ISDIR(parent_current.st_mode)
        or (parent_current.st_dev, parent_current.st_ino)
        != snapshot["parent_identity"]
    ):
        raise ValueError(f"{label} changed during verification")


@contextmanager
def _capture_regular_inputs(paths):
    """Hold stable, path-bound snapshots for the complete verification phase."""
    with ExitStack() as descriptors:
        snapshots = {
            label: _open_bound_input(descriptors, path, label=label)
            for label, path in paths.items()
        }
        try:
            yield {label: item["content"] for label, item in snapshots.items()}
        except BaseException:
            raise
        else:
            for label, snapshot in snapshots.items():
                _require_bound_input_stable(snapshot, label=label)


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


def _bounded_number(value, label, *, minimum, maximum):
    number = _number(value, label)
    if not minimum <= number <= maximum:
        raise ValueError(f"{label} outside [{minimum}, {maximum}]")
    return number


def _nonnegative_integer(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _task_ids(payload, label):
    tasks = payload.get("task_ids")
    _require(isinstance(tasks, list) and tasks, f"{label} task_ids must be non-empty")
    _require(all(isinstance(x, str) and x for x in tasks), f"{label} task_ids invalid")
    _require(len(tasks) == len(set(tasks)), f"{label} task_ids must be unique")
    n_tasks = _nonnegative_integer(payload.get("n_tasks"), f"{label} n_tasks")
    _require(n_tasks == len(tasks), f"{label} n_tasks mismatch")
    return tasks


def _validate_summary(result, diffs, label):
    n_pairs = _nonnegative_integer(result.get("n_pairs"), f"{label} n_pairs")
    positive = _nonnegative_integer(
        result.get("positive_tasks"), f"{label} positive_tasks"
    )
    negative = _nonnegative_integer(
        result.get("negative_tasks"), f"{label} negative_tasks"
    )
    tied = _nonnegative_integer(result.get("tied_tasks"), f"{label} tied_tasks")
    _require(n_pairs == len(diffs), f"{label} n_pairs mismatch")
    _require(positive == sum(x > 0 for x in diffs), f"{label} positive count mismatch")
    _require(negative == sum(x < 0 for x in diffs), f"{label} negative count mismatch")
    _require(tied == sum(x == 0 for x in diffs), f"{label} tie count mismatch")
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
        diffs = [
            _bounded_number(
                x,
                f"automated {name} difference",
                minimum=-1.0,
                maximum=1.0,
            )
            for x in raw
        ]
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
                _bounded_number(
                    task_diffs[task],
                    f"human {name}/{dimension}/{task}",
                    minimum=-4.0,
                    maximum=4.0,
                )
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


def _verify_preserved_legacy_receipt(receipt: dict, *, root: Path) -> None:
    """Validate the one pinned legacy receipt with stable verifier source bytes."""
    adapted = copy.deepcopy(receipt)
    builder = adapted.get("provenance_builder")
    if (
        not isinstance(builder, dict)
        or builder.get("path") != "scripts/build_analysis_provenance.py"
    ):
        raise ValueError("legacy receipt has invalid provenance-builder binding")
    implementations = adapted.get("verification_implementations")
    provenance = (
        implementations.get("provenance")
        if isinstance(implementations, dict)
        else None
    )
    if (
        not isinstance(provenance, dict)
        or provenance.get("path") != "scripts/verify_analysis_provenance.py"
    ):
        raise ValueError("legacy receipt has invalid provenance-verifier binding")
    output_consistency = (
        implementations.get("output_consistency")
        if isinstance(implementations, dict)
        else None
    )
    if (
        not isinstance(output_consistency, dict)
        or output_consistency.get("path")
        != "scripts/verify_main_study_outputs.py"
    ):
        raise ValueError("legacy receipt has invalid output-verifier binding")

    # These three fingerprints must describe the same retained source inodes
    # throughout both legacy verification calls. Hashing Path.read_bytes()
    # independently here would trust a same-byte pathname replacement.
    source_paths = {
        "legacy_provenance_builder": root / builder["path"],
        "legacy_provenance_verifier": root / provenance["path"],
        "legacy_output_verifier": root / output_consistency["path"],
    }
    with _capture_regular_inputs(source_paths) as captured:
        builder["sha256"] = hashlib.sha256(
            captured["legacy_provenance_builder"]
        ).hexdigest()
        provenance["sha256"] = hashlib.sha256(
            captured["legacy_provenance_verifier"]
        ).hexdigest()
        output_consistency["sha256"] = hashlib.sha256(
            captured["legacy_output_verifier"]
        ).hexdigest()
        verify_analysis_provenance.verify_receipt(adapted, root=root)
        verify_analysis_provenance.verify_recomputed_outputs(receipt, root=root)


def _verify_automated_provenance(content: bytes, *, root: Path) -> None:
    """Verify execution-bound receipts and retain the preserved legacy path."""
    receipt = _load(content, "automated provenance")
    if "verified_execution" in receipt:
        verify_main_study_execution.verify_execution_receipt(receipt, root=root)
        verify_analysis_provenance.verify_recomputed_outputs(receipt, root=root)
        return
    if hashlib.sha256(content).hexdigest() != FROZEN_LEGACY_AUTOMATED_PROVENANCE_SHA256:
        raise ValueError(
            "automated provenance is missing verified_execution and does not match "
            "the pinned preserved legacy receipt"
        )
    _verify_preserved_legacy_receipt(receipt, root=root)


def verify_readiness(root=ROOT, human_root=None, contract=None):
    """Verify both canonical bundles and return a source-bound readiness receipt."""
    root = Path(root)
    human_root = Path(human_root) if human_root else root / HUMAN_ROOT
    contract = Path(contract) if contract else root / CONTRACT
    with _capture_regular_inputs(
        {"reconciliation_contract": contract}
    ) as contract_snapshot:
        contract_content = contract_snapshot["reconciliation_contract"]
        contract_sha256 = hashlib.sha256(contract_content).hexdigest()
        if contract_sha256 != FROZEN_RECONCILIATION_CONTRACT_SHA256:
            raise ValueError(
                "frozen reconciliation contract fingerprint mismatch: "
                f"expected {FROZEN_RECONCILIATION_CONTRACT_SHA256}, got {contract_sha256}"
            )
        paths = {
            "automated_analysis": root / AUTO_JSON,
            "automated_provenance": root / AUTO_PROV,
            "human_analysis": human_root / "analysis.json",
            "human_manifest": human_root / "analysis_manifest.json",
        }
        with _capture_regular_inputs(paths) as captured:
            before = {"reconciliation_contract": contract_content, **captured}

            _verify_automated_provenance(before["automated_provenance"], root=root)
            verify_main_study_outputs.verify_outputs(root=root)
            human_verification = _verify_human_analysis_bundle(human_root, root=root)

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
                "inputs_descriptor_bound_during_verification": True,
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
