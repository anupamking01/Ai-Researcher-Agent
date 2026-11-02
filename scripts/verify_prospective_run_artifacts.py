"""Offline source-to-record audit for a FUTURE VERA counterbalanced replication.

Checks a candidate 40-cell chronology against bounded, content-fingerprinted
local traces and reports. This is a self-reported artifact-consistency gate,
not independent authentication of model calls, retrieval, or research outcomes.
No treatments, evaluations, or ratings are run.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from scripts import plan_counterbalanced_replication as design
from scripts import verify_counterbalanced_replication_execution as chronology

INDEX_CLASSIFICATION = "prospective_replication_local_artifact_continuity_only"
MAX_INDEX_BYTES = 256 * 1024
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_TREE_ENTRIES = 256
MAX_ARTIFACT_TREE_DEPTH = 16
_INDEX_FIELDS = frozenset({
    "schema_version", "classification", "task_set_id",
    "execution_log_sha256", "cells",
})
_CELL_FIELDS = frozenset({
    "task_id", "variant", "run_id", "status", "trace", "report",
})
_FILE_FIELDS = frozenset({"path", "size_bytes", "sha256"})
_PATH_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _json_bytes(raw: bytes, description: str) -> object:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=design._distinct_keys,
            parse_constant=design._reject_nonfinite,
            parse_int=design._bounded_int,
            parse_float=design._bounded_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise design.DesignError(
            f"{description} is not unambiguous UTF-8 JSON"
        ) from exc


def _file_generation(st: os.stat_result) -> tuple:
    return (
        st.st_dev, st.st_ino, st.st_mode, st.st_size,
        st.st_nlink, st.st_mtime_ns, st.st_ctime_ns,
    )


def _read_regular_under(root_fd: int, relative: str) -> tuple[bytes, tuple[int, int]]:
    """Open each path segment relative to directory descriptors, without links.

    Reject hardlinks as well as repeated inode identities: a candidate index
    cannot silently use the same underlying evidence as two distinct files.
    """
    if (type(relative) is not str or not 0 < len(relative) <= 384
            or not all(_PATH_COMPONENT.fullmatch(part) for part in relative.split("/"))):
        raise design.DesignError("artifact path is not a safe relative path")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise design.DesignError("platform lacks safe descriptor-relative artifact reads")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    directory_flags = flags | os.O_DIRECTORY
    try:
        with ExitStack() as stack:
            parent = os.dup(root_fd)
            stack.callback(os.close, parent)
            for component in relative.split("/")[:-1]:
                parent = os.open(component, directory_flags, dir_fd=parent)
                stack.callback(os.close, parent)
            fd = os.open(relative.split("/")[-1], flags | getattr(os, "O_NONBLOCK", 0),
                         dir_fd=parent)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or not 0 < before.st_size <= MAX_ARTIFACT_BYTES):
                    raise design.DesignError(
                        "artifact must be a bounded regular file with no hardlink aliases"
                    )
                raw = stream.read(MAX_ARTIFACT_BYTES + 1)
                after = os.fstat(stream.fileno())
            if (len(raw) != before.st_size
                    or _file_generation(before) != _file_generation(after)):
                raise design.DesignError("artifact changed during source capture")
            return raw, (before.st_dev, before.st_ino)
    except OSError as exc:
        raise design.DesignError("artifact could not be safely opened") from exc


def _validate_file_claim(claim: object, *, description: str,
                         root_fd: int, seen_paths: set[str],
                         seen_inodes: set[tuple[int, int]],
                         captured_claims: dict[str, tuple[tuple[int, int], int, str]]) -> tuple[bytes, int]:
    if type(claim) is not dict or set(claim) != _FILE_FIELDS:
        raise design.DesignError(f"{description} requires exact file fingerprint fields")
    path, length, digest = claim["path"], claim["size_bytes"], claim["sha256"]
    if (type(path) is not str or type(length) is not int
            or not 0 < length <= MAX_ARTIFACT_BYTES
            or type(digest) is not str or _SHA256.fullmatch(digest) is None):
        raise design.DesignError(f"{description} has invalid file fingerprint types")
    if path in seen_paths:
        raise design.DesignError(f"{description} reuses an artifact path")
    raw, inode = _read_regular_under(root_fd, path)
    if inode in seen_inodes:
        raise design.DesignError(f"{description} reuses an artifact inode")
    if len(raw) != length or hashlib.sha256(raw).hexdigest() != digest:
        raise design.DesignError(f"{description} differs from supplied artifact bytes")
    seen_paths.add(path)
    seen_inodes.add(inode)
    captured_claims[path] = (inode, length, digest)
    return raw, len(raw)



def _inventory_artifact_paths(root_fd: int) -> set[str]:
    """Enumerate a dedicated evidence root; reject unindexed retained artifacts.

    This is a bounded local custody check. It cannot detect traces deleted
    before capture, files outside this root, or transient concurrent changes.
    """
    directory_flags = (os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
                       | getattr(os, "O_CLOEXEC", 0))
    seen: set[str] = set()
    entries_seen = 0
    try:
        with ExitStack() as stack:
            opened_root = os.dup(root_fd)
            stack.callback(os.close, opened_root)
            pending = [(opened_root, "", 0)]
            while pending:
                parent, prefix, depth = pending.pop()
                with os.scandir(parent) as entries:
                    for entry in entries:
                        entries_seen += 1
                        if entries_seen > MAX_ARTIFACT_TREE_ENTRIES:
                            raise design.DesignError(
                                "artifact root has too many directory entries"
                            )
                        name = entry.name
                        if _PATH_COMPONENT.fullmatch(name) is None:
                            raise design.DesignError(
                                "artifact root contains an unsafe path component"
                            )
                        relative = prefix + name
                        if len(relative) > 384:
                            raise design.DesignError(
                                "artifact root contains an overlong relative path"
                            )
                        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
                        if stat.S_ISDIR(before.st_mode):
                            if depth >= MAX_ARTIFACT_TREE_DEPTH:
                                raise design.DesignError(
                                    "artifact root directory nesting exceeds limit"
                                )
                            child = os.open(name, directory_flags, dir_fd=parent)
                            stack.callback(os.close, child)
                            if _file_generation(os.fstat(child)) != _file_generation(before):
                                raise design.DesignError(
                                    "artifact directory changed during inventory"
                                )
                            pending.append((child, relative + "/", depth + 1))
                        elif stat.S_ISREG(before.st_mode) and before.st_nlink == 1:
                            seen.add(relative)
                        else:
                            raise design.DesignError(
                                "artifact root must contain only single-link regular files and directories"
                            )
    except OSError as exc:
        raise design.DesignError("artifact root could not be safely inventoried") from exc
    return seen


def _require_readable_markdown_report(raw: bytes, *, number: int) -> None:
    """Reject reports that cannot be reviewed as nonblank UTF-8 Markdown text.

    Fingerprints alone allow a binary, whitespace-only, or NUL-containing
    payload to masquerade as a completed research report. This validates only
    the report's textual envelope, not its quality or scientific accuracy.
    """
    try:
        report_text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise design.DesignError(
            f"report {number} is not valid UTF-8 Markdown text"
        ) from exc
    if "\x00" in report_text or not report_text.lstrip("\ufeff").strip():
        raise design.DesignError(
            f"report {number} must contain nonblank Markdown text without NUL bytes"
        )
    # Text that decodes correctly can still contain terminal escape bytes or
    # explicit bidirectional overrides that misrepresent what an annotator sees.
    # Keep ordinary tab/newline/CR and multilingual printable text intact.
    if any(
        (ord(character) < 0x20 and character not in "\t\n\r")
        or 0x7f <= ord(character) <= 0x9f
        or 0x202a <= ord(character) <= 0x202e
        or 0x2066 <= ord(character) <= 0x2069
        for character in report_text
    ):
        raise design.DesignError(
            f"report {number} contains unsafe control or bidirectional formatting"
        )


def audit_run_artifacts(
    task_manifest: bytes,
    plan_receipt: bytes,
    execution_log: bytes,
    evidence_index: bytes,
    artifact_root: Path,
    *,
    expected_task_manifest_sha256: str | None = None,
    expected_plan_file_sha256: str | None = None,
    expected_execution_log_sha256: str | None = None,
    expected_evidence_index_sha256: str | None = None,
) -> dict:
    """Audit recorded lineage and actual local bytes, without asserting execution."""
    recorded = chronology.audit_execution_log(
        task_manifest, plan_receipt, execution_log,
        expected_task_manifest_sha256=expected_task_manifest_sha256,
        expected_plan_file_sha256=expected_plan_file_sha256,
        expected_execution_log_sha256=expected_execution_log_sha256,
    )
    if (type(evidence_index) is not bytes
            or not 0 < len(evidence_index) <= MAX_INDEX_BYTES):
        raise design.DesignError("evidence index bytes outside supported range")
    # Reconstruct task-question fingerprints only after the strict prospective
    # manifest/plan/chronology gate has accepted the frozen input.
    # This checks trace-to-task metadata agreement, not actual prompt delivery.
    frozen_questions = {
        task["id"]: hashlib.sha256(task["question"].encode("utf-8")).hexdigest()
        for task in _json_bytes(task_manifest, "verified task manifest")["tasks"]
    }
    index_sha = hashlib.sha256(evidence_index).hexdigest()
    index_pin_matched = chronology._check_pin(
        expected_evidence_index_sha256,
        label="expected evidence-index SHA-256",
        actual=index_sha,
    )
    index = _json_bytes(evidence_index, "evidence index")
    if type(index) is not dict or set(index) != _INDEX_FIELDS:
        raise design.DesignError("evidence index must use the exact schema")
    if type(index["schema_version"]) is not int or index["schema_version"] != 1:
        raise design.DesignError("evidence index requires integer schema version 1")
    if (type(index["classification"]) is not str
            or index["classification"] != INDEX_CLASSIFICATION):
        raise design.DesignError("evidence index has invalid classification")
    if (type(index["task_set_id"]) is not str
            or index["task_set_id"] != recorded["task_set_id"]):
        raise design.DesignError("evidence index task set differs from chronology")
    if (type(index["execution_log_sha256"]) is not str
            or index["execution_log_sha256"] != recorded["execution_log_sha256"]):
        raise design.DesignError("evidence index is not bound to the exact execution log")
    cells = index["cells"]
    if type(cells) is not list or len(cells) != recorded["recorded_cells"]:
        raise design.DesignError("evidence index must retain all 40 cells")

    # The event JSON has already passed the strict, bounded chronology audit;
    # parsing it a second time cannot redefine its cell identities or statuses.
    events = _json_bytes(execution_log, "verified execution log")["events"]
    seen_paths: set[str] = set()
    seen_inodes: set[tuple[int, int]] = set()
    captured_claims: dict[str, tuple[tuple[int, int], int, str]] = {}
    total_bytes = trace_count = report_count = 0
    # Keep a single source-root inode pinned for the entire multi-file audit.
    # Re-opening its path per file risks mixing independent directory trees.
    if not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY'):
        raise design.DesignError('platform lacks safe descriptor-relative artifact reads')
    root_path = Path(artifact_root)
    try:
        root_fd = os.open(
            root_path,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY | getattr(os, 'O_CLOEXEC', 0),
        )
    except OSError as exc:
        raise design.DesignError('artifact root could not be safely opened') from exc
    try:
        root_before = os.fstat(root_fd)
        initial_paths = _inventory_artifact_paths(root_fd)
        for number, (event, cell) in enumerate(zip(events, cells, strict=True), start=1):
            if type(cell) is not dict or set(cell) != _CELL_FIELDS:
                raise design.DesignError(f"artifact cell {number} has incorrect fields")
            for field in ("task_id", "variant", "run_id", "status"):
                if type(cell[field]) is not type(event[field]) or cell[field] != event[field]:
                    raise design.DesignError(
                        f"artifact cell {number} differs from recorded event {field}"
                    )
            if event["status"] == "not_started":
                if cell["trace"] is not None or cell["report"] is not None:
                    raise design.DesignError(
                        f"unattempted artifact cell {number} invents source evidence"
                    )
                continue
            if cell["trace"] is None:
                raise design.DesignError(f"attempted artifact cell {number} lacks a trace")
            trace_raw, size = _validate_file_claim(
                cell["trace"], description=f"trace {number}",
                root_fd=root_fd, seen_paths=seen_paths, seen_inodes=seen_inodes,
                captured_claims=captured_claims,
            )
            total_bytes += size
            trace_count += 1
            if total_bytes > MAX_TOTAL_ARTIFACT_BYTES:
                raise design.DesignError("aggregate artifact bytes exceed supported budget")
            trace = _json_bytes(trace_raw, f"trace {number}")
            if type(trace) is not dict:
                raise design.DesignError(f"trace {number} must be a JSON object")
            for field in ("task_id", "variant", "run_id", "status"):
                if type(trace.get(field)) is not str or trace[field] != event[field]:
                    raise design.DesignError(
                        f"trace {number} {field} does not bind to recorded event"
                    )
            # The arm label alone cannot establish that its self-reported
            # intervention settings agree with the original four-arm design.
            expected_controls = design.PROSPECTIVE_TREATMENT_CONTROLS_V1[event["variant"]]
            controls = trace.get("treatment_controls")
            if type(controls) is not dict or set(controls) != set(expected_controls):
                raise design.DesignError(
                    f"trace {number} requires exact frozen treatment-control fields"
                )
            if any(
                type(controls[field]) is not type(expected) or controls[field] != expected
                for field, expected in expected_controls.items()
            ):
                raise design.DesignError(
                    f"trace {number} treatment controls differ from frozen variant"
                )
            # A run with the right ID can still claim the wrong question.
            # The exact UTF-8 question bytes (not normalized text) must agree
            # with the frozen manifest. This is self-reported provenance only.
            if (type(trace.get("task_question_sha256")) is not str
                    or trace["task_question_sha256"] != frozen_questions[event["task_id"]]):
                raise design.DesignError(
                    f"trace {number} question fingerprint differs from frozen task manifest"
                )
            # Require each retained trace to corroborate the logged UTC interval.
            # Identical self-reported timestamps are not external clock evidence.
            for field in ("started_at_utc", "finished_at_utc"):
                if type(trace.get(field)) is not str or trace[field] != event[field]:
                    raise design.DesignError(
                        f"trace {number} {field} does not bind to recorded chronology"
                    )
            if "report_sha256" not in trace:
                raise design.DesignError(f"trace {number} lacks a report hash binding")

            report = cell["report"]
            if event["status"] == "completed" and report is None:
                raise design.DesignError(f"completed cell {number} lacks a report")
            if report is None:
                if trace["report_sha256"] is not None:
                    raise design.DesignError(
                        f"trace {number} claims a report not supplied in the inventory"
                    )
            else:
                # Let the strict fingerprint-schema validator reject malformed
                # claims before attempting to interpret the optional path.
                if (type(report) is dict and type(report.get("path")) is str
                        and not report["path"].endswith(".md")):
                    raise design.DesignError(
                        f"report {number} requires a .md Markdown artifact path"
                    )
                report_raw, size = _validate_file_claim(
                    report, description=f"report {number}",
                    root_fd=root_fd, seen_paths=seen_paths, seen_inodes=seen_inodes,
                    captured_claims=captured_claims,
                )
                _require_readable_markdown_report(report_raw, number=number)
                total_bytes += size
                report_count += 1
                if total_bytes > MAX_TOTAL_ARTIFACT_BYTES:
                    raise design.DesignError("aggregate artifact bytes exceed supported budget")
                if (type(trace["report_sha256"]) is not str
                        or trace["report_sha256"] != report["sha256"]):
                    raise design.DesignError(
                        f"trace {number} does not bind the supplied report fingerprint"
                    )

        # Source bytes may be replaced or rewritten after an early cell passes.
        # Re-open every verified path beneath the original root descriptor;
        # require both file identity and content to remain unchanged at the
        # end of the bounded scan. This is not an atomic filesystem snapshot.
        for path, (initial_inode, initial_size, initial_digest) in captured_claims.items():
            try:
                current_raw, current_inode = _read_regular_under(root_fd, path)
            except design.DesignError as exc:
                raise design.DesignError(
                    "previously verified artifact became inaccessible during audit"
                ) from exc
            if (current_inode != initial_inode or len(current_raw) != initial_size
                    or hashlib.sha256(current_raw).hexdigest() != initial_digest):
                raise design.DesignError(
                    "previously verified artifact changed during audit"
                )

        # Every file present in this dedicated root must be accounted for by
        # an attempted cell. Otherwise retained alternative attempts could be
        # omitted from the submitted forty-cell index without being noticed.
        # Compare both the initial and final bounded inventories to the
        # paths actually verified; this is not an atomic or external audit.
        final_paths = _inventory_artifact_paths(root_fd)
        if initial_paths != seen_paths or final_paths != seen_paths:
            raise design.DesignError(
                "artifact root contains unindexed or missing evidence files"
            )

        root_after = os.fstat(root_fd)
        try:
            root_at_path = os.lstat(root_path)
        except OSError as exc:
            raise design.DesignError('artifact root changed during verification') from exc
        if (
            _file_generation(root_before) != _file_generation(root_after)
            or not stat.S_ISDIR(root_at_path.st_mode)
            or root_at_path.st_dev != root_after.st_dev
            or root_at_path.st_ino != root_after.st_ino
        ):
            raise design.DesignError('artifact root changed during verification')
    finally:
        os.close(root_fd)

    return {
        "status": "pass_local_artifact_continuity_only",
        "classification": INDEX_CLASSIFICATION,
        "task_set_id": recorded["task_set_id"],
        "execution_log_sha256": recorded["execution_log_sha256"],
        "evidence_index_sha256": index_sha,
        "evidence_index_external_pin_matched": index_pin_matched,
        "task_manifest_external_pin_matched": recorded["task_manifest_external_pin_matched"],
        "plan_file_external_pin_matched": recorded["plan_file_external_pin_matched"],
        "execution_log_external_pin_matched": recorded["execution_log_external_pin_matched"],
        "planned_cells": recorded["recorded_cells"],
        "attempted_cells": recorded["attempted_cells"],
        "unattempted_cells": recorded["unattempted_cells"],
        "verified_attempted_traces": trace_count,
        "verified_reports": report_count,
        "artifact_paths_rechecked_after_full_scan": len(captured_claims),
        "artifact_root_inventory_file_count": len(seen_paths),
        "artifact_root_inventory_matches_index": True,
        "artifact_identity_and_bytes_stable_at_final_recheck": True,
        "recorded_status_counts": recorded["recorded_status_counts"],
        "all_planned_cells_completed": recorded["all_recorded_cells_completed"],
        "artifact_bytes_equal_supplied_fingerprints": True,
        "trace_question_fingerprints_match_frozen_manifest": True,
        "trace_treatment_controls_match_frozen_design": True,
        "recorded_execution_independently_authenticated": False,
        "model_or_retrieval_calls_verified": False,
        "scientific_outcomes_validated": False,
        "historical_2026_study_validated": False,
        "human_validation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-manifest", required=True, type=Path)
    parser.add_argument("--plan-file", required=True, type=Path)
    parser.add_argument("--execution-log", required=True, type=Path)
    parser.add_argument("--evidence-index", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--expected-task-manifest-sha256")
    parser.add_argument("--expected-plan-file-sha256")
    parser.add_argument("--expected-execution-log-sha256")
    parser.add_argument("--expected-evidence-index-sha256")
    args = parser.parse_args()
    try:
        result = audit_run_artifacts(
            design.read_manifest(args.task_manifest),
            design.read_manifest(args.plan_file),
            design.read_manifest(args.execution_log),
            design.read_manifest(args.evidence_index),
            args.artifact_root,
            expected_task_manifest_sha256=args.expected_task_manifest_sha256,
            expected_plan_file_sha256=args.expected_plan_file_sha256,
            expected_execution_log_sha256=args.expected_execution_log_sha256,
            expected_evidence_index_sha256=args.expected_evidence_index_sha256,
        )
    except design.DesignError as exc:
        parser.exit(2, f"PROSPECTIVE LOCAL ARTIFACT CONTINUITY: FAIL: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
