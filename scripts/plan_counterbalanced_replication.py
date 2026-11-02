"""Offline design-only counterbalancing plan for a NEW VERA replication task set.

Never executes treatments or evaluators; does not reclassify the frozen 2026 study.
This is a prospective design aid, not evidence of random historical assignment.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import unicodedata

VARIANTS = ("D3", "D6", "P6", "P6V")
# Frozen prospective intervention contract, not observed provider behavior.
PROSPECTIVE_TREATMENT_CONTROLS_V1 = {
    "D3": {"planning_mode": "direct", "source_budget": 3, "verification_mode": "none"},
    "D6": {"planning_mode": "direct", "source_budget": 6, "verification_mode": "none"},
    "P6": {"planning_mode": "planner", "source_budget": 6, "verification_mode": "none"},
    "P6V": {"planning_mode": "planner", "source_budget": 6, "verification_mode": "verify"},
}
ORIGINAL_TASK_SET_ID = "main-budget-v1-2026-09-11"
DESIGN_VERSION = "vera-prospective-williams-10-v1"
MAX_MANIFEST_BYTES = 256 * 1024
TASK_COUNT = 10


# SHA-256 of NFKC/whitespace/casefold-normalized questions in the frozen
# September 2026 original main-study manifest. These are source fingerprints,
# NOT independently authenticated reports or evidence of valid replication.
# The regression test cross-checks every digest against the byte-pinned
# experiments/main_budget_tasks.json source at original commit c3c15e46.
ORIGINAL_2026_QUESTION_SHA256 = frozenset({
    "77539c749b52602df19551290eaa8f147165f96aab7b37940b60d1ac50f88156",
    "ca2a291ef4babb16903a94f89fd8c3d2937649b77eda4ffe89dd6adf25039756",
    "853e0b6172e7d70cc41d549dac87c28f786d940c0d6c57207b37e6a229b94a9e",
    "f9fceb3bc84c38da3e170b49696431e9226bb2f3ce32278a9cca42348ed198ab",
    "f3146da707bdc647a3540af5bb3840a4e6344ca2c5a9fb72215d668714b6a4fe",
    "98eab67ff549c656707d15d451df2108bcd048d6534b955d112ab24d0af99363",
    "04fad1acb9e48a13aca4d0c1401125032ae5002724cd30d683593b2ea7e48258",
    "7a1fb088bb79fb52adfda5c74a3b0eb36384b46499d7e7ff69a4e05528af64cd",
    "ec30abd696e192acb6f9d78851ee36129f7deaf0473259af2b1a21939b200597",
    "ebd62c6716ccec7608d5f163cd3eff895c3e59c30410d40c81d193cc53d89a58",
})
ORIGINAL_2026_TASK_IDS = frozenset(f"main-{index:02d}" for index in range(1, 11))



def _contains_hidden_task_control(text: str) -> bool:
    """Reject invisible prompt changes before freezing a NEW task schedule.

    The manifest is retained byte-for-byte; silently deleting formatting
    controls would change what a future model actually receives. JSON-escaped
    lone UTF-16 surrogates are not Unicode scalar values and cannot form a
    portable UTF-8 research prompt. Do not
    remove every combining mark: genuine accented text remains supported.
    """
    for character in text:
        codepoint = ord(character)
        if (
            unicodedata.category(character) in {"Cf", "Cs"}
            or (unicodedata.category(character) == "Cc" and character not in "\t\n\r")
            or codepoint == 0x034F  # Combining Grapheme Joiner
            or 0x180B <= codepoint <= 0x180D  # Mongolian variation selectors
            or codepoint == 0x180F  # Mongolian variation selector four
            or 0xFE00 <= codepoint <= 0xFE0F  # Variation selectors 1-16
            or 0xE0100 <= codepoint <= 0xE01EF  # Supplementary selectors
        ):
            return True
    return False


def _normalized_question_sha256(question: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", question).split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
    result = float(token)
    if not math.isfinite(result):
        raise DesignError("task-manifest float is not finite")
    return result


def _source_generation(st) -> tuple:
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns)


def read_manifest(path: Path) -> bytes:
    """Capture a bounded file through no-follow, descriptor-held ancestry.

    The same reader is used for both the NEW task manifest and its schedule
    receipt. A pinned digest cannot establish a stable pathname if a parent
    is a redirect or is replaced while the bytes are being captured.
    """
    path = Path(path)
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise DesignError("the platform cannot guarantee a no-follow manifest read")
    if ".." in path.parts:
        raise DesignError("task manifest path cannot contain parent traversal")
    absolute = path.absolute()
    if any(parent.is_symlink() for parent in absolute.parents):
        raise DesignError("task manifest has a symlinked parent directory")
    ancestor_flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        named_before = path.lstat()
        if not stat.S_ISREG(named_before.st_mode) or not (
            0 < named_before.st_size <= MAX_MANIFEST_BYTES
        ):
            raise DesignError("task manifest must be a bounded regular non-symlink file")
        with ExitStack() as stack:
            parent_fd = os.open(absolute.anchor, ancestor_flags)
            stack.callback(os.close, parent_fd)
            ancestor_entries = []
            # Walk the entire ancestor chain using openat and O_NOFOLLOW,
            # retaining each directory descriptor until capture completes.
            # A pathname-only symlink check would be vulnerable to a parent
            # being replaced between the initial check and the file open.
            for component in absolute.parts[1:-1]:
                child_fd = os.open(component, ancestor_flags, dir_fd=parent_fd)
                stack.callback(os.close, child_fd)
                child_stat = os.fstat(child_fd)
                linked_stat = os.stat(
                    component, dir_fd=parent_fd, follow_symlinks=False
                )
                if _source_generation(child_stat) != _source_generation(linked_stat):
                    raise DesignError("task manifest parent directory changed before capture")
                ancestor_entries.append((parent_fd, component, child_fd))
                parent_fd = child_fd

            fd = os.open(absolute.name, file_flags, dir_fd=parent_fd)
            stack.callback(os.close, fd)
            opened = os.fstat(fd)
            linked_before = os.stat(
                absolute.name, dir_fd=parent_fd, follow_symlinks=False
            )
            if (not stat.S_ISREG(opened.st_mode)
                    or _source_generation(opened) != _source_generation(named_before)
                    or _source_generation(opened) != _source_generation(linked_before)):
                raise DesignError("task manifest changed before capture")

            captured = bytearray()
            while len(captured) <= MAX_MANIFEST_BYTES:
                piece = os.read(
                    fd, min(65536, MAX_MANIFEST_BYTES + 1 - len(captured))
                )
                if not piece:
                    break
                captured.extend(piece)
            after = os.fstat(fd)
            linked_after = os.stat(
                absolute.name, dir_fd=parent_fd, follow_symlinks=False
            )
            if (len(captured) != opened.st_size
                    or len(captured) > MAX_MANIFEST_BYTES
                    or _source_generation(opened) != _source_generation(after)
                    or _source_generation(after) != _source_generation(linked_after)):
                raise DesignError("task manifest changed during capture")

            # A replacement parent can leave the original file descriptor and
            # filename internally consistent while altering the path a future
            # verifier or executor would resolve.
            for holder_fd, component, child_fd in ancestor_entries:
                linked = os.stat(
                    component, dir_fd=holder_fd, follow_symlinks=False
                )
                if _source_generation(os.fstat(child_fd)) != _source_generation(linked):
                    raise DesignError("task manifest parent directory changed during capture")
            return bytes(captured)
    except OSError as exc:
        raise DesignError("cannot safely capture task manifest") from exc

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
    if set(payload) != {"schema_version", "task_set_id", "frozen_before_execution", "tasks"} or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise DesignError("new task manifest must use exact design-only schema v1")
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
    # Each row must be an independent question, not just a distinct task ID.
    # Reuse the historical-leakage normalization for within-set uniqueness.
    question_fingerprints = set()
    for index, task in enumerate(tasks, start=1):
        if type(task) is not dict or set(task) != {"id", "category", "question"}:
            raise DesignError(f"task {index} must contain only id/category/question")
        identifier, category, question = (
            task.get("id"), task.get("category"), task.get("question")
        )
        if (type(identifier) is not str
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", identifier) is None):
            raise DesignError(f"task {index} has an unsafe identifier")
        if identifier in ORIGINAL_2026_TASK_IDS:
            raise DesignError("prospective task reuses a reserved 2026 main-study ID")
        if type(category) is not str or not category.strip():
            raise DesignError(f"task {index} has no category")
        if type(question) is not str or not question.strip():
            raise DesignError(f"task {index} has no question")
        # Unseen Unicode marks can change the raw prompt and the deterministic
        # assignment digest without changing what a coordinator sees. Refuse
        # them instead of silently normalizing a future treatment prompt.
        if _contains_hidden_task_control(category):
            raise DesignError(
                f"task {index} category contains invisible/control Unicode"
            )
        if _contains_hidden_task_control(question):
            raise DesignError(
                f"task {index} question contains invisible/control Unicode"
            )
        question_fingerprint = _normalized_question_sha256(question)
        if question_fingerprint in ORIGINAL_2026_QUESTION_SHA256:
            raise DesignError(
                "prospective task repeats a frozen 2026 main-study question"
            )
        if identifier in task_ids or question_fingerprint in question_fingerprints:
            raise DesignError(
                "tasks have duplicate identifiers or normalized-equivalent questions"
            )
        task_ids.append(identifier)
        question_fingerprints.add(question_fingerprint)

    source_sha256 = hashlib.sha256(source).hexdigest()
    # Assignment must not be tunable by reformatting semantically identical
    # JSON: distinguish exact raw custody from canonical design input.
    semantic_manifest_sha256 = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
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
            f"{DESIGN_VERSION}\n{semantic_manifest_sha256}\nslot:{index}".encode("ascii")
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
        "semantic_task_manifest_sha256": semantic_manifest_sha256,
        "task_set_id": task_set_id,
        "historical_2026_study_replaced": False,
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
