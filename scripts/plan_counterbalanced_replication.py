"""Offline design-only counterbalancing plan for a NEW VERA replication task set.

Never executes treatments or evaluators; does not reclassify the frozen 2026 study.
This is a prospective design aid, not evidence of random historical assignment.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import stat

VARIANTS = ("D3", "D6", "P6", "P6V")
ORIGINAL_TASK_SET_ID = "main-budget-v1-2026-09-11"
DESIGN_VERSION = "vera-prospective-williams-10-v1"
MAX_MANIFEST_BYTES = 256 * 1024
TASK_COUNT = 10


class DesignError(ValueError):
    """A task source or proposed design violates the prospective contract."""


def _distinct_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise DesignError(f"duplicate task-manifest JSON key: {name}")
        result[name] = value
    return result


def _reject_nonfinite(value: str):
    raise DesignError(f"nonstandard task-manifest JSON constant: {value}")


def _bounded_int(token: str) -> int:
    if len(token) > 128:
        raise DesignError("task-manifest numeric token is unbounded")
    return int(token)


def _bounded_float(token: str) -> float:
    if len(token) > 128:
        raise DesignError("task-manifest numeric token is unbounded")
    return float(token)


def _source_generation(st) -> tuple:
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns)


def read_manifest(path: Path) -> bytes:
    """Capture one bounded regular file, rejecting links and observable swaps."""
    path = Path(path)
    if not hasattr(os, "O_NOFOLLOW"):
        raise DesignError("the platform cannot guarantee a no-follow manifest read")
    try:
        named_before = path.lstat()
        if not stat.S_ISREG(named_before.st_mode) or not (
            0 < named_before.st_size <= MAX_MANIFEST_BYTES
        ):
            raise DesignError("task manifest must be a bounded regular non-symlink file")
        fd = os.open(
            path, os.O_RDONLY | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode)
                    or _source_generation(opened) != _source_generation(named_before)):
                raise DesignError("task manifest changed before capture")
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
            after = os.fstat(stream.fileno())
        named_after = path.lstat()
    except OSError as exc:
        raise DesignError("cannot safely capture task manifest") from exc
    if (len(raw) != opened.st_size or len(raw) > MAX_MANIFEST_BYTES
            or _source_generation(opened) != _source_generation(after)
            or _source_generation(after) != _source_generation(named_after)):
        raise DesignError("task manifest changed during capture")
    return raw


def build_plan(source: bytes) -> dict:
    """Bind a fixed outcome-blind schedule to exact new-manifest bytes."""
    if type(source) is not bytes or not 0 < len(source) <= MAX_MANIFEST_BYTES:
        raise DesignError("task manifest bytes outside supported range")
    try:
        payload = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_distinct_keys,
            parse_constant=_reject_nonfinite,
            parse_int=_bounded_int,
            parse_float=_bounded_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DesignError("task manifest is not unambiguous UTF-8 JSON") from exc
    if type(payload) is not dict:
        raise DesignError("task manifest must be a JSON object")
    task_set_id = payload.get("task_set_id")
    if (type(task_set_id) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", task_set_id) is None
            or task_set_id == ORIGINAL_TASK_SET_ID):
        raise DesignError("a distinct, safe NEW task_set_id is required")
    if payload.get("frozen_before_execution") is not True:
        raise DesignError("new task manifest must explicitly declare frozen_before_execution")
    tasks = payload.get("tasks")
    if type(tasks) is not list or len(tasks) != TASK_COUNT:
        raise DesignError("prospective design requires exactly 10 new tasks")

    task_ids = []
    questions = set()
    for index, task in enumerate(tasks, start=1):
        if type(task) is not dict:
            raise DesignError(f"task {index} is not a JSON object")
        identifier, category, question = (
            task.get("id"), task.get("category"), task.get("question")
        )
        if (type(identifier) is not str
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", identifier) is None):
            raise DesignError(f"task {index} has an unsafe identifier")
        if type(category) is not str or not category.strip():
            raise DesignError(f"task {index} has no category")
        if type(question) is not str or not question.strip():
            raise DesignError(f"task {index} has no question")
        if identifier in task_ids or question.strip() in questions:
            raise DesignError("tasks have duplicate identifiers or questions")
        task_ids.append(identifier)
        questions.add(question.strip())

    source_sha256 = hashlib.sha256(source).hexdigest()
    # Even-order Williams Latin square. Each treatment occurs once at each
    # position across four rows, and each ordered pair is balanced 2:2.
    base = (0, 1, 3, 2)
    latin = [
        tuple(VARIANTS[(offset + item) % 4] for item in base)
        for offset in range(4)
    ]
    # Ten tasks: two full squares plus a mutually reversed pair. Every
    # treatment pair precedes each other five times; position counts are 2/3.
    slots = latin + latin + [VARIANTS, tuple(reversed(VARIANTS))]
    # Domain-separated SHA-256 ordering, independent of Python RNG versions.
    # The source manifest is a pre-execution input; no outcome data are read.
    slot_order = sorted(
        range(TASK_COUNT),
        key=lambda index: hashlib.sha256(
            f"{DESIGN_VERSION}\n{source_sha256}\nslot:{index}".encode("ascii")
        ).digest(),
    )
    schedule = [
        {"task_id": task_id, "arm_order": list(slots[slot_order[position]])}
        for position, task_id in enumerate(task_ids)
    ]
    position_counts = {
        variant: [sum(row["arm_order"][position] == variant for row in schedule)
                  for position in range(4)]
        for variant in VARIANTS
    }
    precedence_counts = {
        f"{left}_before_{right}": sum(
            row["arm_order"].index(left) < row["arm_order"].index(right)
            for row in schedule
        )
        for i, left in enumerate(VARIANTS)
        for right in VARIANTS[i + 1:]
    }
    if (any(set(row["arm_order"]) != set(VARIANTS)
            or len(row["arm_order"]) != len(VARIANTS) for row in schedule)
            or any(sorted(counts) != [2, 2, 3, 3]
                   for counts in position_counts.values())
            or any(count != TASK_COUNT // 2 for count in precedence_counts.values())):
        raise DesignError("counterbalancing design invariant failed")

    plan = {
        "schema_version": 1,
        "classification": "prospective_design_only_no_executions",
        "design_version": DESIGN_VERSION,
        "source_manifest_sha256": source_sha256,
        "task_set_id": task_set_id,
        "historical_2026_study_replaced": False,
        "frozen_original_2026_task_set_reused": False,
        "task_count": TASK_COUNT,
        "treatment_cells_planned": TASK_COUNT * len(VARIANTS),
        "schedule": schedule,
        "position_counts": position_counts,
        "pairwise_precedence_counts": precedence_counts,
        "historical_design_causal_limitation_resolved": False,
        "independent_replication_or_human_validation_performed": False,
    }
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False)
    plan["design_receipt_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-manifest", type=Path, required=True,
                        help="separately frozen NEW ten-task manifest; no default")
    args = parser.parse_args()
    try:
        plan = build_plan(read_manifest(args.task_manifest))
    except DesignError as exc:
        parser.exit(2, f"PROSPECTIVE DESIGN: FAIL: {exc}\n")
    print(json.dumps(plan, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
