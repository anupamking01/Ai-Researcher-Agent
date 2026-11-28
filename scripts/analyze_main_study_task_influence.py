"""Exploratory, exhaustive paired-task influence diagnostic for frozen VERA results.

This is a post-hoc robustness description, NOT a new confirmatory test.
Each of the ten tasks is omitted once for each of the three frozen primary
contrasts. No treatment, evaluator, human-rating, or analysis output is changed.
The default CLI independently verifies the canonical automated analysis first.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import statistics
from pathlib import Path

from scripts import analyze_main_study
from scripts import verify_analysis_provenance
from scripts import verify_main_study_outputs
from scripts import verify_main_study_execution

ROOT = Path(__file__).resolve().parents[1]
INFERENCE = Path("outputs/main_study_inference.json")
PROVENANCE = Path("outputs/main_study_analysis_provenance.json")
MAX_SOURCE_BYTES = 16 * 1024 * 1024


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate canonical inference JSON key: {key!r}")
        result[key] = value
    return result


def _reject_non_json_number(token):
    raise ValueError(f"non-JSON finite number: {token}")


def _source_identity(metadata: os.stat_result) -> tuple:
    """Track the exact inode generation across metadata/read/path checks."""
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_regular_bounded(path: Path, *, label: str) -> bytes:
    """Capture bounded canonical bytes from one path-bound regular-file inode.

    O_NOFOLLOW/O_NONBLOCK reject symlink and FIFO races; opening the parent
    directory first prevents a renamed path from silently selecting a different
    source. This is a read-time custody safeguard, not file authenticity proof.
    """
    path = Path(path)
    parent_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    file_flags = (
        os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        parent_fd = os.open(path.parent, parent_flags)
    except OSError as exc:
        raise ValueError(f"{label} parent must be a regular directory: {path.parent}") from exc
    try:
        parent_before = os.fstat(parent_fd)
        _require(stat.S_ISDIR(parent_before.st_mode),
                 f"{label} parent must be a regular directory: {path.parent}")
        try:
            candidate = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise ValueError(f"{label} must be a regular file: {path}") from exc
        _require(stat.S_ISREG(candidate.st_mode),
                 f"{label} must be a regular file: {path}")
        _require(candidate.st_size <= MAX_SOURCE_BYTES,
                 f"{label} exceeds source-byte limit")
        try:
            source_fd = os.open(path.name, file_flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ValueError(f"{label} changed during source capture: {path}") from exc
        try:
            opened = os.fstat(source_fd)
            _require(stat.S_ISREG(opened.st_mode),
                     f"{label} must be a regular file: {path}")
            _require(_source_identity(opened) == _source_identity(candidate),
                     f"{label} changed during source capture: {path}")
            _require(opened.st_size <= MAX_SOURCE_BYTES,
                     f"{label} exceeds source-byte limit")
            chunks = []
            offset = 0
            while offset < opened.st_size:
                chunk = os.pread(
                    source_fd, min(1024 * 1024, opened.st_size - offset), offset
                )
                _require(bool(chunk),
                         f"{label} changed during source capture: {path}")
                chunks.append(chunk)
                offset += len(chunk)
            _require(not os.pread(source_fd, 1, offset),
                     f"{label} changed during source capture: {path}")
            after = os.fstat(source_fd)
            _require(_source_identity(after) == _source_identity(opened),
                     f"{label} changed during source capture: {path}")
            try:
                visible = os.stat(
                    path.name, dir_fd=parent_fd, follow_symlinks=False
                )
                parent_visible = os.stat(path.parent, follow_symlinks=False)
            except OSError as exc:
                raise ValueError(
                    f"{label} changed during source capture: {path}"
                ) from exc
            _require(_source_identity(visible) == _source_identity(opened),
                     f"{label} changed during source capture: {path}")
            _require(stat.S_ISDIR(parent_visible.st_mode) and
                     (parent_visible.st_dev, parent_visible.st_ino) ==
                     (parent_before.st_dev, parent_before.st_ino),
                     f"{label} parent changed during source capture: {path.parent}")
            return b"".join(chunks)
        finally:
            os.close(source_fd)
    finally:
        os.close(parent_fd)


def _parse_analysis(data: bytes) -> dict:
    try:
        payload = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_non_json_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("canonical inference must be valid UTF-8 JSON") from exc
    _require(type(payload) is dict, "canonical inference must be an object")
    return payload


def _valid_difference(value, *, label: str) -> float:
    _require(
        type(value) in (int, float)
        and math.isfinite(value)
        and -1.0 <= value <= 1.0,
        f"{label} must be a finite strict-support paired difference in [-1, 1]",
    )
    return float(value)


def diagnostic(payload: dict) -> dict:
    """Summarize ALL possible single-task omissions, without choosing one."""
    _require(type(payload) is dict, "canonical inference must be an object")
    _require(
        type(payload.get("schema_version")) is int
        and payload["schema_version"] == 1
        and payload.get("study_id") == "budget-main-v1",
        "unexpected frozen study identity",
    )
    tasks = payload.get("task_ids")
    _require(
        type(tasks) is list
        and len(tasks) == analyze_main_study.EXPECTED_TASKS
        and all(type(x) is str and x and x == x.strip() for x in tasks)
        and len(set(tasks)) == len(tasks)
        and type(payload.get("n_tasks")) is int
        and payload["n_tasks"] == len(tasks),
        "frozen task identities/count must be complete and unique",
    )
    names = tuple(name for _, _, name in analyze_main_study.PRIMARY_CONTRASTS)
    blocks = payload.get("primary_contrasts")
    _require(type(blocks) is dict and set(blocks) == set(names),
             "expected exactly the frozen primary contrasts")

    summaries = {}
    for name in names:
        block = blocks[name]
        _require(type(block) is dict, f"{name} must be a contrast object")
        raw = block.get("task_differences")
        _require(
            type(raw) is list and len(raw) == len(tasks),
            f"{name} must contain one ordered difference per frozen task",
        )
        diffs = [
            _valid_difference(value, label=f"{name}/{task}")
            for task, value in zip(tasks, raw)
        ]
        stated_mean = _valid_difference(
            block.get("mean_difference"), label=f"{name} published mean"
        )
        full_mean = statistics.mean(diffs)
        _require(
            math.isclose(stated_mean, full_mean, rel_tol=0, abs_tol=1e-12),
            f"{name} published mean is inconsistent with its task differences",
        )
        entries = []
        for index, task_id in enumerate(tasks):
            retained = diffs[:index] + diffs[index + 1:]
            omitted_mean = statistics.mean(retained)
            entries.append({
                "omitted_task_id": task_id,
                "remaining_pairs": len(retained),
                "mean_difference_without_task": omitted_mean,
                "change_from_full_mean": omitted_mean - full_mean,
            })
        summaries[name] = {
            "full_sample_mean_difference": stated_mean,
            "n_frozen_pairs": len(diffs),
            "all_task_omissions": entries,
            "loo_mean_min": min(x["mean_difference_without_task"] for x in entries),
            "loo_mean_max": max(x["mean_difference_without_task"] for x in entries),
        }

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "post_hoc_exploratory_task_influence_only",
        "scope": "three_frozen_primary_contrasts_all_ten_single_task_omissions",
        "confirmatory_analysis_replaced": False,
        "human_validation_performed": False,
        "inferential_p_values_or_intervals_added": False,
        "task_ids": list(tasks),
        "results": summaries,
    }


def run_verified(root: Path = ROOT) -> dict:
    """Use the existing provenance and independent recomputation gate first.

    The pre/post byte comparison is an additional guard against observable
    changes around the established descriptor-bound upstream verifiers. It is
    not an atomic filesystem snapshot or an authenticity proof by itself.
    """
    root = Path(root)
    source_path = root / INFERENCE
    receipt_path = root / PROVENANCE
    source_before = _read_regular_bounded(source_path, label="canonical analysis")
    receipt_before = _read_regular_bounded(receipt_path, label="analysis provenance")
    receipt = verify_analysis_provenance.parse_receipt_json(
        receipt_before.decode("utf-8")
    )
    _require(type(receipt) is dict, "analysis provenance must be an object")
    _require(
        "verified_execution" in receipt,
        "canonical provenance must include verified treatment execution",
    )
    # Execution-bound verification includes the underlying provenance check.
    verify_main_study_execution.verify_execution_receipt(receipt, root=root)
    verify_analysis_provenance.verify_recomputed_outputs(receipt, root=root)
    verify_main_study_outputs.verify_outputs(root=root)
    if (
        source_before != _read_regular_bounded(source_path, label="canonical analysis")
        or receipt_before != _read_regular_bounded(receipt_path, label="analysis provenance")
    ):
        raise ValueError("verified canonical inputs changed during influence analysis")
    result = diagnostic(_parse_analysis(source_before))
    result["verified_canonical_inference_sha256"] = hashlib.sha256(
        source_before
    ).hexdigest()
    result["verified_provenance_receipt_sha256"] = hashlib.sha256(
        receipt_before
    ).hexdigest()
    result["source_provenance_independently_recomputed"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = run_verified(args.root)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"TASK INFLUENCE DIAGNOSTIC: FAIL: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
