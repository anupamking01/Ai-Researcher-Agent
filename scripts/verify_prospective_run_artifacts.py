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
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import stat
import unicodedata
from urllib.parse import urlsplit

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
_GIT_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_RUNTIME_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
_RUNTIME_FIELDS = frozenset({
    "runner_commit", "requirements_sha256", "smart_model_id",
    "fast_model_id", "search_provider_id", "generation_temperature",
    "search_candidate_multiplier", "browse_timeout_seconds",
    "run_timeout_seconds", "max_concurrent_browses",
})


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
        or ord(character) in (0x061c, 0x200e, 0x200f)
        or 0x202a <= ord(character) <= 0x202e
        or 0x2066 <= ord(character) <= 0x206f
        for character in report_text
    ):
        raise design.DesignError(
            f"report {number} contains unsafe control or bidirectional formatting"
        )


def _source_fetch_identity(url: object, *, number: int) -> str:
    """Canonicalize the HTTP resource named in a *self-reported* source ledger.

    URL fragments do not affect the HTTP request. An alternate spelling must
    not be counted as an additional scheduled retrieval for the same resource.
    This is syntactic validation only: no DNS, redirects or retrievals occur.
    """
    if (
        type(url) is not str or not 0 < len(url) <= 2048
        or url != url.strip() or "\\" in url
        or any(
            character.isspace() or unicodedata.category(character) in {
                "Cc", "Cf", "Zl", "Zp"
            }
            for character in url
        )
    ):
        raise design.DesignError(
            f"trace {number} source ledger requires bounded, visible HTTP(S) URLs"
        )
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc or not host or "@" in parsed.netloc
            or port == 0
        ):
            raise ValueError("not an absolute unauthenticated HTTP(S) resource")
        # A bracketed IP literal is an address, not a DNS name. Different
        # compressed/expanded IPv6 spellings identify the *same* fetch target;
        # do not let them inflate a claimed source count or break outcome
        # reconciliation. Reject scoped addresses (whose interface-zone
        # semantics are local and cannot anchor portable source evidence).
        if ":" in host:
            if "%" in host:
                raise ValueError("scoped IPv6 addresses are not portable sources")
            normalized_host = ipaddress.IPv6Address(host).compressed
        else:
            normalized_host = host.encode("idna").decode("ascii").lower()
        if not normalized_host or "%" in normalized_host:
            raise ValueError("invalid source host")
    except (UnicodeError, ValueError) as exc:
        raise design.DesignError(
            f"trace {number} source ledger has invalid HTTP(S) source URL"
        ) from exc
    authority = (
        f"[{normalized_host}]" if ":" in normalized_host else normalized_host
    )
    default_port = 443 if parsed.scheme == "https" else 80
    if port is not None and port != default_port:
        authority += f":{port}"
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{authority}{path}{query}"


def _validate_source_budget_ledger(trace: dict, *, number: int, variant: str) -> None:
    """Check *reported* source use against the assigned prospective browse cap.

    A matching ledger is internally consistent evidence metadata, not proof
    that URLs were fetched or that provider/browser calls occurred.
    """
    budget = design.PROSPECTIVE_TREATMENT_CONTROLS_V1[variant]["source_budget"]
    for field in ("source_count", "successful_source_count", "failed_source_count"):
        value = trace.get(field)
        if type(value) is not int or value < 0:
            raise design.DesignError(
                f"trace {number} source ledger {field} must be a nonnegative integer"
            )
    if trace["source_count"] > budget:
        raise design.DesignError(
            f"trace {number} source ledger exceeds assigned {variant} browse budget"
        )
    if (trace["successful_source_count"] + trace["failed_source_count"]
            != trace["source_count"]):
        raise design.DesignError(
            f"trace {number} source ledger outcome counts do not partition sources"
        )

    recorded = {}
    for field, count_field in (
        ("scheduled_urls", "source_count"),
        ("successful_urls", "successful_source_count"),
        ("failed_urls", "failed_source_count"),
    ):
        urls = trace.get(field)
        if (type(urls) is not list
                or len(urls) != trace[count_field]
                or any(
                    type(url) is not str or not url or url != url.strip()
                    for url in urls
                )
                or len(set(urls)) != len(urls)):
            raise design.DesignError(
                f"trace {number} source ledger {field} is invalid or inconsistent"
            )
        fetch_identities = [
            _source_fetch_identity(url, number=number) for url in urls
        ]
        if len(set(fetch_identities)) != len(urls):
            raise design.DesignError(
                f"trace {number} source ledger {field} counts one HTTP resource repeatedly"
            )
        # Match each outcome to the HTTP resource scheduled for retrieval,
        # not the literal URL spelling: fragments, host case and default
        # ports can legitimately differ between scheduling and reporting.
        # The original strings remain unchanged in the trace evidence.
        recorded[field] = set(fetch_identities)
    if (recorded["successful_urls"] & recorded["failed_urls"]
            or recorded["scheduled_urls"] != (
                recorded["successful_urls"] | recorded["failed_urls"]
            )):
        raise design.DesignError(
            f"trace {number} source ledger has missing, invented or overlapping URL outcomes"
        )



def _common_runtime_context_digest(context: object, *, number: int) -> str:
    """Validate a prospective trace's *recorded* non-treatment environment.

    Require the same declared code, model/provider and operational settings
    across all attempted arms. An independently retained preregistration hash
    may anchor these claims; the statements themselves cannot prove execution.
    """
    if type(context) is not dict or set(context) != _RUNTIME_FIELDS:
        raise design.DesignError(
            f"trace {number} requires exact common runtime-context fields"
        )
    if (type(context["runner_commit"]) is not str
            or _GIT_SHA.fullmatch(context["runner_commit"]) is None):
        raise design.DesignError(
            f"trace {number} runtime runner_commit is not a Git commit identifier"
        )
    if (type(context["requirements_sha256"]) is not str
            or _SHA256.fullmatch(context["requirements_sha256"]) is None):
        raise design.DesignError(
            f"trace {number} runtime requirements_sha256 is not a SHA-256 digest"
        )
    for field in ("smart_model_id", "fast_model_id", "search_provider_id"):
        value = context[field]
        if type(value) is not str or _RUNTIME_ID.fullmatch(value) is None:
            raise design.DesignError(
                f"trace {number} runtime {field} needs a bounded provider identifier"
            )
    temperature = context["generation_temperature"]
    if (type(temperature) not in (int, float)
            or not 0 <= temperature <= 2 or not math.isfinite(temperature)):
        raise design.DesignError(
            f"trace {number} runtime generation_temperature is not finite in [0, 2]"
        )
    for field in ("search_candidate_multiplier", "max_concurrent_browses"):
        value = context[field]
        if type(value) is not int or not 1 <= value <= 64:
            raise design.DesignError(
                f"trace {number} runtime {field} needs a bounded positive integer"
            )
    for field in ("browse_timeout_seconds", "run_timeout_seconds"):
        value = context[field]
        if (type(value) not in (int, float)
                or not 0 < value <= 86400 or not math.isfinite(value)):
            raise design.DesignError(
                f"trace {number} runtime {field} needs finite positive seconds"
            )
    # Compare permitted continuous settings by VALUE, not by whether the
    # recorder serialized an integral value as 60 or 60.0. All accepted
    # integers are small enough to convert exactly to float. Preserve the
    # original trace bytes and their independent inventory fingerprint.
    canonical_context = dict(context)
    for field in (
        "generation_temperature", "browse_timeout_seconds",
        "run_timeout_seconds",
    ):
        value = canonical_context[field]
        canonical_context[field] = 0.0 if value == 0 else float(value)
    canonical = json.dumps(
        canonical_context, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

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
    expected_runtime_context_sha256: str | None = None,
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
    common_runtime_sha256: str | None = None
    runtime_context_external_pin_matched = False
    # A configured browse cap is not evidence that any sources were actually
    # scheduled or resolved. Report integer exposure denominators separately
    # for each arm, including failed and partial executions, without implying
    # that these self-reported URLs were independently fetched.
    source_usage_by_variant = {
        variant: {
            "attempted_cells": 0,
            "completed_cells": 0,
            "scheduled_source_claims": 0,
            "successful_source_claims": 0,
            "failed_source_claims": 0,
            "at_budget_attempted_cells": 0,
            "zero_scheduled_source_attempts": 0,
            "zero_successful_source_attempts": 0,
        }
        for variant in design.VARIANTS
    }
    # Keep only bounded, task-paired source counts in memory for a prospective
    # exposure diagnostic; never use them to exclude or rerun treatment cells.
    paired_exposure_by_task: dict[str, dict[str, dict]] = {}
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
            # A declared source budget is insufficient: the attempted run's
            # own URL ledger must fit that budget and partition source outcomes.
            _validate_source_budget_ledger(
                trace, number=number, variant=event["variant"]
            )
            source_usage = source_usage_by_variant[event["variant"]]
            source_usage["attempted_cells"] += 1
            if event["status"] == "completed":
                source_usage["completed_cells"] += 1
            source_usage["scheduled_source_claims"] += trace["source_count"]
            source_usage["successful_source_claims"] += trace["successful_source_count"]
            source_usage["failed_source_claims"] += trace["failed_source_count"]
            if trace["source_count"] == expected_controls["source_budget"]:
                source_usage["at_budget_attempted_cells"] += 1
            if trace["source_count"] == 0:
                source_usage["zero_scheduled_source_attempts"] += 1
            if trace["successful_source_count"] == 0:
                source_usage["zero_successful_source_attempts"] += 1
            paired_exposure_by_task.setdefault(event["task_id"], {})[
                event["variant"]
            ] = {
                "status": event["status"],
                "scheduled": trace["source_count"],
                "successful": trace["successful_source_count"],
            }
            # A recorded arm is not comparable to another if its declared
            # model, source code, search backend or common guardrails drift.
            # This validates candidate metadata only, not provider activity.
            runtime_sha = _common_runtime_context_digest(
                trace.get("runtime_context"), number=number
            )
            if common_runtime_sha256 is None:
                common_runtime_sha256 = runtime_sha
                runtime_context_external_pin_matched = chronology._check_pin(
                    expected_runtime_context_sha256,
                    label="expected common runtime-context SHA-256",
                    actual=runtime_sha,
                )
            elif runtime_sha != common_runtime_sha256:
                raise design.DesignError(
                    f"trace {number} runtime context changed across attempted cells"
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

    # Arm-wide totals can conceal whether extra retrieval was used for the
    # *same task* in a paired primary contrast. Report descriptive, integer
    # signed differences only for tasks with both attempts; do not count a
    # missing arm as zero exposure. Failed attempts remain in this denominator,
    # with complete pairs disclosed separately. No scientific effect is tested.
    paired_source_exposure_by_contrast = {}
    for earlier, later in (("D3", "D6"), ("D6", "P6"), ("P6", "P6V")):
        counts = {
            "both_attempted_tasks": 0,
            "both_completed_tasks": 0,
            "scheduled_delta_positive": 0,
            "scheduled_delta_zero": 0,
            "scheduled_delta_negative": 0,
            "scheduled_delta_sum": 0,
            "successful_delta_positive": 0,
            "successful_delta_zero": 0,
            "successful_delta_negative": 0,
            "successful_delta_sum": 0,
        }
        for per_arm in paired_exposure_by_task.values():
            if earlier not in per_arm or later not in per_arm:
                continue
            earlier_cell, later_cell = per_arm[earlier], per_arm[later]
            counts["both_attempted_tasks"] += 1
            if (earlier_cell["status"] == "completed"
                    and later_cell["status"] == "completed"):
                counts["both_completed_tasks"] += 1
            for metric in ("scheduled", "successful"):
                delta = later_cell[metric] - earlier_cell[metric]
                counts[f"{metric}_delta_sum"] += delta
                direction = "positive" if delta > 0 else "negative" if delta < 0 else "zero"
                counts[f"{metric}_delta_{direction}"] += 1
        paired_source_exposure_by_contrast[f"{later} - {earlier}"] = counts

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
        "self_reported_source_ledgers_within_frozen_budgets": True,
        "self_reported_source_usage_by_variant": source_usage_by_variant,
        "self_reported_paired_source_exposure_by_contrast": paired_source_exposure_by_contrast,
        "self_reported_source_urls_http_and_fetch_distinct": True,
        "common_runtime_context_sha256": common_runtime_sha256,
        "common_runtime_context_external_pin_matched": runtime_context_external_pin_matched,
        "recorded_common_runtime_context_consistent": True,
        "actual_common_runtime_independently_authenticated": False,
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
    parser.add_argument("--expected-runtime-context-sha256")
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
            expected_runtime_context_sha256=args.expected_runtime_context_sha256,
        )
    except design.DesignError as exc:
        parser.exit(2, f"PROSPECTIVE LOCAL ARTIFACT CONTINUITY: FAIL: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
