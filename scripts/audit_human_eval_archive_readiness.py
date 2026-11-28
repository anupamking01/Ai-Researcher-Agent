"""Read-only inventory of ORIGINAL VERA evidence required before human handoff.

This is a recovery diagnostic, NOT a provenance PASS. A path's presence (or
40 trace candidates) never proves its content, run identity, archive custody,
or suitability for human assessment. Use verify_human_eval_automated_handoff
with independently retained pins for the actual acceptance decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import build_human_eval_packet as packet_builder
from scripts import export_human_eval_annotator_bundle as exporter
from scripts import verify_published_main_study_inputs as published
from scripts import verify_human_eval_automated_run_lineage as lineage
from scripts import validate_main_study_inputs as main_input_contract
from scripts import verify_frozen_main_study_tasks as frozen_tasks

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TRACES = 40
VARIANTS = packet_builder.EXPECTED_VARIANTS
EXPECTED_PER_VARIANT = EXPECTED_TRACES // len(VARIANTS)

# Historical main-study CSV measurements were computed from these exact trace
# counters. A recovered trace that agrees on identity but not measurement is
# not the evidence used for the frozen automated analysis.
TRACE_TO_MAIN_MEASUREMENTS = (
    ("source_budget", "source_budget"),
    ("successful_source_count", "successful_sources"),
    ("failed_source_count", "failed_sources"),
    ("search_call_count", "search_calls"),
    ("model_call_count", "model_calls"),
    ("total_tokens", "total_tokens"),
    ("report_words", "report_words"),
)
# Pricing bytes from historical treatment workflow 34620917346 (source
# commit c3c15e46...). Never use present-day prices for frozen outcomes.
FROZEN_PRICING_REL = "experiments/openai_pricing_2026-09-08.json"
ORIGINAL_PRICING_SHA256 = "35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace"
# Exact literal persisted by the pinned September 2026 logic/run.py.
# Actual per-treatment estimates were computed later from the dated rate table.
ORIGINAL_TRACE_COST_STATUS = "not_computed_without_frozen_pricing_table"

# Original treatment workflow 34620917346 metadata, as recorded by GitHub.
# The reported last-update second is inclusive; this is not clock attestation.
ORIGINAL_TREATMENT_WORKFLOW_START_UTC = datetime(
    2026, 9, 11, 16, 15, 15, tzinfo=timezone.utc
)
ORIGINAL_TREATMENT_WORKFLOW_LAST_UPDATE_UTC = datetime(
    2026, 9, 11, 17, 22, 43, tzinfo=timezone.utc
)
# run_agent measures per-run duration with perf_counter, whereas starts use
# wall-clock UTC. Reject gross impossible overlap, but allow small clock drift:
# this is a plausibility bound, not cross-clock synchronization evidence.
ORIGINAL_RUN_CLOCK_DRIFT_ALLOWANCE_SECONDS = 5.0

# Historical c3c15e46 search: 3 candidate results per available browse slot,
# hard cap 20; web_search normalizes to unique, stripped, nonempty hrefs.
ORIGINAL_SEARCH_CANDIDATE_MULTIPLIER = 3
ORIGINAL_SEARCH_CANDIDATE_CAP = 20

FROZEN_EXECUTION_MODES = {
    "D3": ("direct", "none"),
    "D6": ("direct", "none"),
    "P6": ("planner", "none"),
    "P6V": ("planner", "verify"),
}

# Original logic/experiment.py ExperimentConfig.from_variant defaults at
# treatment checkout c3c15e46. run_budget_main_study.py used from_variant()
# and replaced only task identifiers. These are shared execution factors:
# changing them could confound retrieval or latency comparisons even if the
# archived source counts, provider usage, and report words remain unchanged.
ORIGINAL_SHARED_EXECUTION_CONFIG = {
    "search_candidate_multiplier": ORIGINAL_SEARCH_CANDIDATE_MULTIPLIER,
    "max_concurrent_browses": 2,
    "stream_report": False,
    "trace_root": "outputs/experiment_traces",
}

# Individual SHA-256s from the published, aggregate-anchored frozen-input
# manifest. Recheck exact captured bytes at each later CSV read; the earlier
# aggregate verification alone cannot protect mutable paths across calls.
PUBLISHED_CSV_FILE_SHA256 = {
    lineage.MAIN_REL: "966ea80519af5ea7b832c86d7868525a4ef75874f396f242291e3be949382a0e",
    lineage.SUPPORT_REL: "5acd80d6115f269c7fab40180dec0d778a45eaafd7d5c23cb79c43fd7837773c",
}


def _candidate_generation(path: Path) -> tuple[int, ...]:
    """Identify a local source revision, never historical origin."""
    if _file_status(path) != "present_unverified":
        raise ValueError("recovered candidate is missing, redirected, or unsafe")
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise ValueError("recovered candidate must be a single-link regular file")
    return (
        st.st_dev, st.st_ino, st.st_mode, st.st_nlink,
        st.st_size, st.st_mtime_ns, st.st_ctime_ns,
    )


def _capture_recovery_candidate(path: Path, *, label: str) -> tuple[bytes, tuple]:
    """Pin initial bytes and file generation for full-matrix rechecking."""
    before = _candidate_generation(path)
    raw = packet_builder._read_regular_file_captured(path, label=label)
    if _candidate_generation(path) != before:
        raise ValueError("recovered candidate changed during initial capture")
    return raw, (path, label, before, hashlib.sha256(raw).digest())


def _verify_recovery_candidate_window(pins: list[tuple]) -> None:
    """Re-read every source after the matrix checks to reject torn revisions.

    This only establishes two-observation local consistency; it is not an
    atomic snapshot or independent historical archive authentication.
    """
    for path, label, generation, digest in pins:
        if _candidate_generation(path) != generation:
            raise ValueError("recovered candidate changed during matrix audit")
        current = packet_builder._read_regular_file_captured(
            path, label=f"{label} final matrix consistency recheck"
        )
        if (
            hashlib.sha256(current).digest() != digest
            or _candidate_generation(path) != generation
        ):
            raise ValueError("recovered candidate changed during matrix audit")


def _capture_published_csv(repo_root: Path, relative: str, *, label: str) -> bytes:
    """Bind every downstream read to the original published CSV bytes."""
    expected_sha = PUBLISHED_CSV_FILE_SHA256.get(relative)
    if expected_sha is None:
        raise ValueError("unexpected frozen CSV requested")
    raw = packet_builder._read_regular_file_captured(
        repo_root / relative, label=label
    )
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError(f"{label} changed after published input verification")
    return raw


def _verify_frozen_content_input_window(repo_root: Path) -> None:
    """Recheck the byte-pinned inputs that governed the matrix content checks."""
    for relative, expected in (
        ("experiments/main_budget_tasks.json",
         frozen_tasks.ORIGINAL_TASK_MANIFEST_SHA256),
        (lineage.MAIN_REL, PUBLISHED_CSV_FILE_SHA256[lineage.MAIN_REL]),
        (lineage.SUPPORT_REL, PUBLISHED_CSV_FILE_SHA256[lineage.SUPPORT_REL]),
        (FROZEN_PRICING_REL, ORIGINAL_PRICING_SHA256),
    ):
        try:
            raw = packet_builder._read_regular_file_captured(
                repo_root / relative, label=f"final frozen content input {relative}"
            )
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"frozen content input unavailable during matrix audit: {relative}: {exc}"
            ) from exc
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(
                f"frozen content input changed during matrix audit: {relative}"
            )


def _file_status(path: Path) -> str:
    """Inventory only single-link regular files without symlink ancestors."""
    try:
        observed = path.lstat()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "inaccessible"
    if not stat.S_ISREG(observed.st_mode):
        return "unsafe_file_type"
    # The downstream packet/manifest readers require a single-link inode.
    # Count aliases as unsafe even in a partial archive where content
    # validation is skipped, or for coordinator-only blinding artifacts.
    if observed.st_nlink != 1:
        return "unsafe_hardlink"
    try:
        if any(parent.is_symlink() for parent in path.parents):
            return "unsafe_parent_symlink"
    except OSError:
        return "inaccessible"
    return "present_unverified"


def _directory_status(path: Path) -> str:
    """Reject redirected and non-directory archive roots before enumeration."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "inaccessible"
    if not stat.S_ISDIR(mode):
        return "unsafe_directory_type"
    try:
        if any(parent.is_symlink() for parent in path.parents):
            return "unsafe_parent_symlink"
    except OSError:
        return "inaccessible"
    return "present_unverified"


def _bounded_sorted_trace_entries(directory: Path, *, maximum: int) -> list[Path]:
    """Sort a bounded directory snapshot without materializing an unbounded scan.

    Recovery archives may be externally supplied and accidentally contain huge
    trees. A valid 40-cell study never needs more than four variant directories
    or 40 trace files in total. Inspect one overflow entry to fail closed;
    never use sorted(directory.iterdir()) on unbounded input.
    """
    entries: list[Path] = []
    for entry in directory.iterdir():
        if len(entries) >= maximum:
            raise ValueError("trace archive directory exceeds entry limit")
        entries.append(entry)
    return sorted(entries)


def _trace_status(root: Path) -> tuple[dict, tuple[str, ...]]:
    """Inventory 4 x 10 candidate filenames without parsing or endorsing traces.

    An unbalanced 40-file directory cannot possibly represent the frozen
    4 x 10 design. Avoid following links, accepting unfamiliar variants, or
    conflating the existence of JSON filenames with run/task provenance.
    """
    by_variant = {variant: 0 for variant in VARIANTS}
    run_ids: set[str] = set()
    located_ids: set[tuple[str, str]] = set()

    def result(status: str) -> dict:
        return {
            "status": status,
            "count": sum(by_variant.values()),
            "expected": EXPECTED_TRACES,
            "by_variant": dict(by_variant),
            "expected_per_variant": EXPECTED_PER_VARIANT,
        }

    status = _directory_status(root)
    if status != "present_unverified":
        return result(status), ()
    try:
        try:
            # One extra entry preserves the existing unexpected-root diagnosis.
            variant_dirs = _bounded_sorted_trace_entries(
                root, maximum=len(VARIANTS) + 1
            )
        except ValueError:
            return result("trace_root_entry_limit_exceeded"), ()
        for variant_dir in variant_dirs:
            if variant_dir.name not in by_variant:
                return result("unexpected_trace_root_entry"), ()
            if _directory_status(variant_dir) != "present_unverified":
                return result("unsafe_variant_directory"), ()
            try:
                # One overflow trace keeps the 41-file count error distinct.
                candidates = _bounded_sorted_trace_entries(
                    variant_dir, maximum=EXPECTED_TRACES + 1
                )
            except ValueError:
                return result("trace_variant_entry_limit_exceeded"), ()
            for candidate in candidates:
                if candidate.suffix != ".json" or candidate.stem in ("", ".", ".."):
                    return result("unexpected_trace_entry"), ()
                if _file_status(candidate) != "present_unverified":
                    return result("unsafe_trace_file_type"), ()
                if candidate.stem in run_ids:
                    return result("duplicate_trace_run_id"), ()
                run_ids.add(candidate.stem)
                located_ids.add((variant_dir.name, candidate.stem))
                by_variant[variant_dir.name] += 1
                if sum(by_variant.values()) > EXPECTED_TRACES:
                    return result("candidate_count_mismatch"), ()
    except OSError:
        return result("inaccessible"), ()

    if len(run_ids) != EXPECTED_TRACES:
        return result("candidate_count_mismatch"), tuple(sorted(located_ids))
    if any(count != EXPECTED_PER_VARIANT for count in by_variant.values()):
        return result("candidate_matrix_mismatch"), tuple(sorted(located_ids))
    return result("40_matrix_candidates_unverified"), tuple(sorted(located_ids))


def _report_status(root: Path, run_ids: tuple[str, ...]) -> dict:
    """Check one expected Markdown filename per run, without opening reports."""
    result = {"status": "not_checked_without_trace_candidates", "count": 0,
              "expected": EXPECTED_TRACES, "missing_or_unsafe": {}}
    if not run_ids:
        return result
    status = _directory_status(root)
    if status != "present_unverified":
        result["status"] = status
        return result

    failed: dict[str, int] = {}
    for run_id in run_ids:
        status = _file_status(root / run_id / "research_report.md")
        if status == "present_unverified":
            result["count"] += 1
        else:
            failed[status] = failed.get(status, 0) + 1
    result["missing_or_unsafe"] = dict(sorted(failed.items()))
    if failed:
        result["status"] = "missing_or_unsafe_report_candidates"
    elif result["count"] != EXPECTED_TRACES:
        result["status"] = "candidate_count_mismatch"
    else:
        result["status"] = "40_report_candidates_unverified"
    return result


def _pin_status(value: str | None, path: Path) -> str:
    """Compare a supplied pin to bounded, captured manifest bytes.

    Matching proves only local file/pin consistency. The coordinator must
    independently establish when and where the expected digest was retained.
    """
    if value is None:
        return "independent_pin_not_supplied"
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        return "invalid_pin_format"
    if _file_status(path) != "present_unverified":
        return "pinned_file_missing_or_unsafe"
    try:
        actual = hashlib.sha256(
            packet_builder._read_regular_file_captured(
                path, label="archival manifest for pin comparison"
            )
        ).hexdigest()
    except (OSError, ValueError):
        return "pinned_file_unreadable_or_unstable"
    return (
        "pin_matches_file_not_authenticated"
        if actual == value else "pin_mismatch"
    )


def _resource_inventory(sources: dict[str, Path]) -> dict[str, str]:
    """Inventory resources and verify the frozen scoring instructions.

    All three guide copies must match the exporter's fixed protocol pin,
    not merely each other. Other packet contents still require the
    integrated handoff verifier; presence is not authentication.
    """
    statuses = {label: _file_status(path) for label, path in sources.items()}
    for label in (
        "frozen_annotator_guide",
        "canonical/annotator_instructions.md",
        "reverse/annotator_instructions.md",
    ):
        if statuses[label] != "present_unverified":
            continue
        pin = _pin_status(exporter.FROZEN_ANNOTATOR_GUIDE_SHA256, sources[label])
        if pin == "pin_mismatch":
            statuses[label] = "frozen_guide_fingerprint_mismatch"
        elif pin != "pin_matches_file_not_authenticated":
            statuses[label] = "frozen_guide_unreadable_or_unstable"
    return statuses


def _trace_run_alignment(
    *,
    repo_root: Path,
    trace_status: str,
    located_ids: tuple[tuple[str, str], ...],
    published_input_anchor: str,
) -> dict:
    """Check recovered trace *filenames* against published evaluator run IDs.

    A balanced D3/D6/P6/P6V directory can contain 40 unrelated runs or
    treatment-swapped run filenames. The published, manifest-anchored evaluator
    CSV supplies a fixed expected (treatment, run_id) set. This diagnostic
    reads neither trace content nor report text and does NOT authenticate an
    archive or establish report-to-trace provenance.
    """
    result = {"status": "not_checked_without_40_trace_candidates",
              "matched": 0, "missing": 0, "unexpected": 0,
              "expected": EXPECTED_TRACES}
    if trace_status != "40_matrix_candidates_unverified":
        return result
    if published_input_anchor != "published_aggregate_matches":
        return {**result, "status": "not_checked_without_published_input_anchor"}
    source = repo_root / lineage.SUPPORT_REL
    try:
        raw = _capture_published_csv(
            repo_root, lineage.SUPPORT_REL,
            label="published evaluator run-identity CSV"
        )
        rows = lineage._read_study_csv(raw, path=source)
        expected_cells = {
            (variant, task) for variant in VARIANTS for task in lineage.TASKS
        }
        matrix = lineage._matrix(
            rows, label="published evaluator run identities",
            expected_cells=expected_cells, run_identity=True,
        )
    except (OSError, ValueError):
        return {**result, "status": "invalid_published_evaluator_run_ids"}

    expected = {
        (variant, row["run_id"])
        for (variant, _task), row in matrix.items()
    }
    found = set(located_ids)
    missing = expected - found
    unexpected = found - expected
    return {
        "status": (
            "40_run_ids_match_published_evaluator_not_authenticated"
            if not missing and not unexpected else "candidate_run_identity_mismatch"
        ),
        "matched": len(found & expected),
        "missing": len(missing),
        "unexpected": len(unexpected),
        "expected": EXPECTED_TRACES,
    }



def _validate_recovered_shared_execution_config(experiment: dict) -> None:
    """Fail closed on altered original, cross-arm execution factors.

    Unlike source_budget and planning/verification, these values were not
    treatment interventions. The pinned main-study runner never overrode
    their from_variant defaults; equality must include JSON scalar types so
    e.g. true cannot masquerade as integer 1. This is a source-consistency
    audit, not independent proof of archive custody or run execution.
    """
    for field, expected in ORIGINAL_SHARED_EXECUTION_CONFIG.items():
        observed = experiment.get(field)
        if type(observed) is not type(expected) or observed != expected:
            raise ValueError(
                f"recovered experiment {field} differs from original "
                "main-study execution config"
            )



def _validate_recovered_start_time(trace: dict) -> datetime:
    """Check trace start timing against the pinned original treatment workflow.

    The original September 2026 logic.run.run_agent records timezone-aware UTC
    now().isoformat() at the start of each run. The workflow start/last-update
    timestamps form a broad same-provider window, not historical custody
    or independent proof of clock accuracy or actual treatment execution.
    """
    raw = trace.get("started_at_utc")
    if (
        type(raw) is not str
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?\+00:00",
            raw,
        ) is None
    ):
        raise ValueError("recovered trace started_at_utc is not original UTC ISO format")
    try:
        started = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("recovered trace started_at_utc is not a valid UTC instant") from exc
    if not (
        ORIGINAL_TREATMENT_WORKFLOW_START_UTC
        <= started
        < ORIGINAL_TREATMENT_WORKFLOW_LAST_UPDATE_UTC + timedelta(seconds=1)
    ):
        raise ValueError(
            "recovered trace started_at_utc falls outside original treatment workflow"
        )
    return started


def _validate_recovered_persistence_time(
    payload: dict, *, started_at: datetime, latency_seconds: float,
) -> datetime:
    """Check the original trace-save UTC clock against run execution.

    Original logic.experiment.save_run_trace stamped recorded_at_utc after
    run_agent's awaited work and latency measurement. This is a wall-clock
    plausibility check, not authenticated historical chronology or proof of
    process execution; allow the established five-second cross-clock margin.
    """
    raw = payload.get("recorded_at_utc")
    if (
        type(raw) is not str
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?\+00:00",
            raw,
        ) is None
    ):
        raise ValueError("recovered recorded_at_utc is not original UTC ISO format")
    try:
        recorded = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("recovered recorded_at_utc is not a valid UTC instant") from exc
    if not (
        started_at - timedelta(seconds=ORIGINAL_RUN_CLOCK_DRIFT_ALLOWANCE_SECONDS)
        <= recorded
        < ORIGINAL_TREATMENT_WORKFLOW_LAST_UPDATE_UTC + timedelta(seconds=1)
    ):
        raise ValueError(
            "recovered recorded_at_utc is outside plausible original save window"
        )
    if (
        (recorded - started_at).total_seconds()
        + ORIGINAL_RUN_CLOCK_DRIFT_ALLOWANCE_SECONDS < latency_seconds
    ):
        raise ValueError(
            "recovered recorded_at_utc precedes the completed run duration"
        )
    return recorded


# Historical workflow 34620917346, checkout c3c15e46, job study.env.
# settings/config.py gives explicit environment values precedence over
# dotenv; logic/run.py records the resulting CFG controls.
ORIGINAL_RUNTIME_LLM_CONTROLS = {
    "smart_model": "gpt-5.6-terra",
    "fast_model": "gpt-5.6-luna",
    "temperature": 1.0,
}


def _validate_recovered_llm_controls(trace: dict) -> None:
    """Require the original workflow's configured controls for every cell.

    Cross-trace agreement alone cannot reject a uniform substitution. This
    is configuration concordance, not evidence of the actual provider model
    served or of independent historical archive custody.
    """
    for field, expected in ORIGINAL_RUNTIME_LLM_CONTROLS.items():
        observed = trace.get(field)
        if type(observed) is not type(expected) or observed != expected:
            raise ValueError(
                f"recovered trace LLM controls differ from original workflow: {field}"
            )


def _validate_recovered_treatment_verification(trace: dict, *, variant: str) -> None:
    """Reconcile treatment-time verification with the actual frozen arm.

    The original ResearchAgent.write_report invokes verify_report only in
    P6V. A completed P6V run records "ok" (normalized claim counts) or
    "parse_error" (all zero counts), whereas D3/D6/P6 record
    "not_requested" and zero counts. This checks trace self-consistency;
    it is not the separate common post-hoc support-evaluator outcome.
    """
    fields = (
        "citation_count", "supported_claim_count",
        "partially_supported_claim_count", "unsupported_claim_count",
        "contradicted_claim_count",
    )
    counts = {}
    for field in fields:
        value = trace.get(field)
        if type(value) is not int or value < 0:
            raise ValueError(
                f"recovered treatment verification {field} must be a nonnegative integer"
            )
        counts[field] = value
    status = trace.get("verification_status")
    if type(status) is not str:
        raise ValueError("recovered treatment verification_status is missing or invalid")
    if variant == "P6V":
        if status not in ("ok", "parse_error"):
            raise ValueError(
                "recovered P6V verification_status contradicts completed verification"
            )
        if status == "parse_error":
            if any(counts.values()):
                raise ValueError(
                    "recovered P6V parse_error must have zero treatment claim counts"
                )
        elif counts["citation_count"] != sum(
            counts[name] for name in fields[1:]
        ):
            raise ValueError(
                "recovered P6V treatment citation_count disagrees with claim categories"
            )
    elif variant in ("D3", "D6", "P6"):
        if status != "not_requested":
            raise ValueError(
                "recovered nonverification arm verification_status is not_requested"
            )
        if any(counts.values()):
            raise ValueError(
                "recovered nonverification arm has unexpected treatment claim counts"
            )
    else:
        raise ValueError("unknown recovered treatment arm for verification")


def _validate_recovered_source_ledgers(trace: dict, *, variant: str) -> None:
    """Check completed-run source provenance, not merely frozen CSV counters.

    Mirror the original treatment runner's source-URL ledger invariants.
    Internal ledger consistency is useful recovery evidence, but cannot prove
    that a URL was retrieved or authenticate the original archived bytes.
    """
    for name in ("source_count", "query_count"):
        value = trace.get(name)
        if type(value) is not int or value < 0:
            raise ValueError(f"recovered trace {name} must be a nonnegative integer")
    if trace["source_count"] > main_input_contract.FROZEN_SOURCE_BUDGETS[variant]:
        raise ValueError("recovered trace source_count exceeds frozen source budget")
    if trace["source_count"] != (
        trace["successful_source_count"] + trace["failed_source_count"]
    ):
        raise ValueError("recovered trace source_count does not match source outcomes")
    if trace["search_call_count"] > trace["query_count"]:
        raise ValueError("recovered trace query_count is below search_call_count")
    if trace.get("usage_accounting_status") != "provider_usage_complete":
        raise ValueError("recovered trace usage_accounting_status is not complete")

    ledgers = {}
    for name, count_field in (
        ("scheduled_urls", "source_count"),
        ("successful_urls", "successful_source_count"),
        ("failed_urls", "failed_source_count"),
    ):
        values = trace.get(name)
        if (
            type(values) is not list
            or any(type(url) is not str or not url or url != url.strip()
                   for url in values)
            or len(values) != trace[count_field]
            or len(set(values)) != len(values)
        ):
            raise ValueError(f"recovered trace {name} has invalid URL/count ledger")
        ledgers[name] = set(values)
    if (
        ledgers["successful_urls"] & ledgers["failed_urls"]
        or ledgers["scheduled_urls"] != (
            ledgers["successful_urls"] | ledgers["failed_urls"]
        )
    ):
        raise ValueError("recovered trace source URL ledger partition is inconsistent")

    # Original async_search awaited gather(), then iterated zip(new_search_urls,
    # responses) in scheduling order. Queries were awaited sequentially. Thus
    # each outcome ledger must be an order-preserving projection of the global
    # scheduled ledger, regardless of asynchronous browser completion order.
    for name in ("successful_urls", "failed_urls"):
        expected_order = [
            url for url in trace["scheduled_urls"] if url in ledgers[name]
        ]
        if trace[name] != expected_order:
            raise ValueError(f"recovered trace {name} violates original source outcome order")




def _validate_recovered_derived_telemetry(trace: dict) -> None:
    """Recompute redundant measurements emitted by original RunTrace.to_dict().

    The pinned September 2026 treatment implementation calculated these
    four fields from its source and treatment-verifier counters before saving
    each trace. Matching published aggregate CSV rows is insufficient if a
    recovered trace contradicts its own derived outcomes. These are NOT the
    separate post-hoc common-evaluator support measurements, nor proof of
    authentic original custody.
    """
    categories = (
        "supported_claim_count", "partially_supported_claim_count",
        "unsupported_claim_count", "contradicted_claim_count",
    )
    category_total = sum(trace[field] for field in categories)
    verified_claims = category_total if category_total > 0 else trace["citation_count"]
    observed_claims = trace.get("verified_claim_count")
    if type(observed_claims) is not int or observed_claims != verified_claims:
        raise ValueError(
            "recovered trace verified_claim_count contradicts original derived telemetry"
        )

    expected_rates = {
        "source_success_rate": (
            trace["successful_source_count"] / trace["source_count"]
            if trace["source_count"] else 0.0
        ),
        "claim_support_rate": (
            trace["supported_claim_count"] / verified_claims
            if verified_claims else 0.0
        ),
        "citation_precision_proxy": (
            max(trace["citation_count"] - trace["unsupported_claim_count"], 0)
            / trace["citation_count"]
            if trace["citation_count"] else 0.0
        ),
    }
    for field, expected in expected_rates.items():
        observed = trace.get(field)
        if (
            type(observed) not in (int, float)
            or not (0 <= observed <= 1)
            or not math.isfinite(observed)
            or not math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-12)
        ):
            raise ValueError(
                f"recovered trace {field} contradicts original derived telemetry"
            )


def _validate_recovered_search_provenance(trace: dict) -> None:
    """Reconcile the original runner's query/result ledger with scheduled URLs.

    The experiment runner persists both planned queries and one result record
    per actual search invocation. Aggregate search-call and source counters can
    agree with frozen CSV measurements even if these nested records were
    replaced. Skipped planned queries are legitimate when budget runs out.
    This checks internal consistency, not real retrieval or archive custody.
    """
    queries = trace.get("search_queries")
    if (type(queries) is not list
            or len(queries) != trace["query_count"]
            or any(type(query) is not str or not query.strip()
                   for query in queries)):
        raise ValueError("recovered trace search_queries/query_count ledger is invalid")

    records = trace.get("search_records")
    if type(records) is not list or len(records) != trace["search_call_count"]:
        raise ValueError("recovered trace search_records/search_call_count ledger is invalid")

    next_query = 0
    scheduled_from_records: list[str] = []
    for index, record in enumerate(records):
        if type(record) is not dict:
            raise ValueError(f"recovered search_records[{index}] is not an object")
        query = record.get("query")
        if type(query) is not str or not query.strip():
            raise ValueError(f"recovered search_records[{index}] query is invalid")
        # A query can be skipped if its allocated source budget was already
        # exhausted. Executed queries must nevertheless preserve plan order,
        # even when two planned queries have identical text.
        while next_query < len(queries) and queries[next_query] != query:
            next_query += 1
        if next_query == len(queries):
            raise ValueError("recovered search_records query order differs from plan")
        next_query += 1

        candidates = record.get("candidate_urls")
        scheduled = record.get("scheduled_urls")
        if (type(candidates) is not list
                or any(type(url) is not str or not url for url in candidates)):
            raise ValueError(f"recovered search_records[{index}] candidate_urls invalid")
        if (type(scheduled) is not list
                or any(type(url) is not str or not url for url in scheduled)):
            raise ValueError(f"recovered search_records[{index}] scheduled_urls invalid")
        # Historical web_search returned a *nonempty* normalized result list
        # for positive num_results, or raised RuntimeError when all pools
        # failed. async_search recorded that failure as a bounded search_error.
        # A purported successful zero-result search is therefore impossible.
        if "search_error" in record:
            error = record["search_error"]
            if (type(error) is not str or not error or len(error) > 1000
                    or candidates or scheduled):
                raise ValueError(
                    "recovered search_error record has invalid error or URLs"
                )
        elif not candidates:
            raise ValueError(
                "recovered search_records empty candidates without search_error"
            )

        # The original get_new_urls retains candidate-result order while
        # removing previously visited URLs; repetitions in search results are
        # legitimate, but newly scheduled URLs cannot be invented/reordered.
        candidate_index = 0
        for url in scheduled:
            while (candidate_index < len(candidates)
                   and candidates[candidate_index] != url):
                candidate_index += 1
            if candidate_index == len(candidates):
                raise ValueError("recovered search_records scheduled URL is missing "
                                 "or out of candidate-result order")
            candidate_index += 1
        scheduled_from_records.extend(scheduled)

    if scheduled_from_records != trace.get("scheduled_urls"):
        raise ValueError("recovered search_records scheduled URLs differ from trace ledger")



def _validate_recovered_query_budget_allocation(trace: dict, *, variant: str) -> None:
    """Check the original runner's planned-query and per-query browse budgets.

    The treatment's total source count can agree with the frozen CSV even
    when a recovered trace spends that budget in a different query. Original
    ResearchAgent.create_search_queries returns the exact question for direct
    arms, or four planned queries for planner arms. conduct_research allocates
    its fixed browse budget by divmod, giving earlier queries the remainder;
    async_search never schedules more than its individual allocation or the
    remaining global budget. The runner also greedily schedules the earliest
    previously unseen candidate URLs, retaining visited URLs across queries;
    merely selecting any candidate subsequence is insufficient. These are
    execution-contract checks, not evidence of genuine retrieval. Historical
    metasearch also bounds, strips, and deduplicates each query candidate list.
    conduct_research attempts every planned query with a positive allocation
    while global browse budget remains: missing or reordered eligible searches
    are not legitimate skipped slots, even if aggregate counters still agree.
    """
    queries = trace["search_queries"]
    if variant in ("D3", "D6"):
        if queries != [trace["question"]]:
            raise ValueError(
                "recovered direct search query differs from frozen research question"
            )
    elif variant in ("P6", "P6V"):
        if len(queries) != 4:
            raise ValueError(
                "recovered planner query count differs from original four-query plan"
            )
    else:
        raise ValueError("unexpected recovered treatment variant")

    total_budget = trace["source_budget"]
    base, remainder = divmod(total_budget, len(queries))
    allocations = [
        base + (1 if index < remainder else 0)
        for index in range(len(queries))
    ]
    next_query = 0
    remaining = total_budget
    visited_urls: set[str] = set()
    for index, record in enumerate(trace["search_records"]):
        query = record["query"]
        # The original conduct_research loop never skips a positive-budget
        # query while global browse budget remains, even after a search error
        # or zero search results. Only zero-allocation slots may be omitted.
        # Match by slot, not by searching ahead for query text: that would
        # permit a fabricated missing search between two valid records.
        while next_query < len(queries) and allocations[next_query] <= 0:
            next_query += 1
        if next_query == len(queries) or remaining <= 0:
            raise ValueError(
                f"recovered search_records[{index}] ran without a query browse budget"
            )
        if query != queries[next_query]:
            raise ValueError(
                f"recovered search_records[{index}] skipped an eligible planned query"
            )
        allowed = min(allocations[next_query], remaining)
        candidates = record.get("candidate_urls")
        # The original metasearch normalizer retained at most the requested
        # nonempty, stripped, distinct hrefs. Scheduled URL counts alone can
        # match frozen measurements even when candidate provenance is impossible.
        if (type(candidates) is not list
                or any(type(url) is not str or not url or url != url.strip()
                       for url in candidates)):
            raise ValueError(
                f"recovered search_records[{index}] search candidate list is invalid"
            )
        candidate_limit = min(
            max(allowed * ORIGINAL_SEARCH_CANDIDATE_MULTIPLIER, allowed),
            ORIGINAL_SEARCH_CANDIDATE_CAP,
        )
        if len(candidates) > candidate_limit or len(set(candidates)) != len(candidates):
            raise ValueError(
                f"recovered search_records[{index}] search candidate list differs "
                "from the original bounded, deduplicated metasearch output"
            )
        scheduled = len(record["scheduled_urls"])
        if scheduled > allowed:
            raise ValueError(
                f"recovered search_records[{index}] exceeds its per-query browse budget"
            )
        # ResearchAgent.get_new_urls greedily takes the first previously unseen
        # candidates up to this query's allocation. A subsequence check alone
        # allows fabricated omission of earlier eligible results while all
        # frozen source totals and aggregate search ledgers still match.
        expected_scheduled: list[str] = []
        for url in record["candidate_urls"]:
            if len(expected_scheduled) >= allowed:
                break
            if url in visited_urls:
                continue
            visited_urls.add(url)
            expected_scheduled.append(url)
        if record["scheduled_urls"] != expected_scheduled:
            raise ValueError(
                f"recovered search_records[{index}] differs from original "
                "greedy candidate URL scheduling"
            )
        remaining -= scheduled
        next_query += 1

    # End-of-record truncation is also impossible if an eligible planned
    # query would still have been attempted by the original sequential loop.
    if remaining > 0 and any(
        allocation > 0 for allocation in allocations[next_query:]
    ):
        raise ValueError(
            "recovered search_records omit an eligible planned query"
        )


def _validate_recovered_context_words(trace: dict) -> None:
    """Check the minimum context implied by original successful source summaries."""
    words = trace.get("research_context_words")
    if type(words) is not int or words < 0:
        raise ValueError("recovered trace research_context_words must be a nonnegative integer")
    # Original async_browse returned the URL-labelled prefix plus a stripped,
    # nonempty summary. conduct_research joined these with whitespace only.
    # A nonempty cached context would bypass query creation, already rejected
    # by the original query-plan checks. No exact context text is reconstructed.
    urls = trace["successful_urls"]
    minimum = sum(len(f"Information gathered from url {url}:".split()) + 1
                  for url in urls)
    if words < minimum or (not urls and words != 0):
        raise ValueError("recovered trace research_context_words contradicts original source summaries")


def _validate_recovered_provider_usage(trace: dict) -> None:
    """Validate the frozen run's per-model usage and aggregate cost basis.

    The historical runner required complete provider-reported usage for every
    model. Aggregate model-call and token counts can match the published CSV
    while the underlying provider ledger is missing or internally impossible.
    This is internal consistency only; historical prices and archive custody
    are not independently authenticated here.
    """
    by_model = trace.get("provider_usage_by_model")
    if type(by_model) is not dict or not by_model:
        raise ValueError("recovered trace provider_usage_by_model must be nonempty")

    totals = {
        "model_calls": 0, "unavailable_calls": 0,
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
    }
    for model, usage in by_model.items():
        if type(model) is not str or not model or model != model.strip():
            raise ValueError("recovered trace provider model name is invalid")
        if type(usage) is not dict:
            raise ValueError(f"recovered trace {model} usage ledger must be an object")
        for field in totals:
            value = usage.get(field)
            if type(value) is not int or value < 0:
                raise ValueError(
                    f"recovered trace {model} {field} must be a nonnegative integer"
                )
            totals[field] += value
        if usage["model_calls"] <= 0:
            raise ValueError(f"recovered trace {model} model_calls must be positive")
        if usage["unavailable_calls"] != 0:
            raise ValueError(
                f"recovered trace {model} unavailable_calls contradict complete usage"
            )
        if usage["total_tokens"] != (
            usage["prompt_tokens"] + usage["completion_tokens"]
        ):
            raise ValueError(f"recovered trace {model} total_tokens ledger mismatch")

    expected = {
        "model_call_count": totals["model_calls"],
        "unavailable_usage_call_count": totals["unavailable_calls"],
        "prompt_tokens": totals["prompt_tokens"],
        "completion_tokens": totals["completion_tokens"],
        "total_tokens": totals["total_tokens"],
    }
    for field, value in expected.items():
        if type(trace.get(field)) is not int or trace[field] != value:
            raise ValueError(f"recovered trace aggregate {field} ledger mismatch")
    if totals["total_tokens"] <= 0:
        raise ValueError("recovered trace provider usage must contain positive tokens")



def _validate_recovered_provider_model_identity(trace: dict) -> None:
    """Bind usage-bucket model names to the frozen run's recorded LLM controls.

    Original ResearchAgent completions always pass CFG.smart_llm_model or
    CFG.fast_llm_model into UsageTracker.record_response. UsageTracker uses
    that *requested* model name as its ledger key, rather than a provider-
    returned alias. An otherwise valid, identically priced third bucket can
    conceal a different treatment model without changing frozen totals.
    Some runs may legitimately use only one configured model (or configure
    both controls to the same name), so do not require both keys.
    This checks recovered internal consistency, not real provider identity.
    """
    configured = {trace["smart_model"], trace["fast_model"]}
    unexpected = set(trace["provider_usage_by_model"]) - configured
    if unexpected:
        raise ValueError(
            "recovered provider usage model identity is outside recorded "
            "smart_model/fast_model runtime controls"
        )


def _validate_recovered_model_call_roles(trace: dict, *, variant: str) -> None:
    """Check recorded call allocation against the original completed-run path.

    At c3c15e46 the distinct smart model performs one report call, one
    additional call for planner arms and one for treatment verification.
    The fast model performs at most one summary per scheduled browse.
    Failed browses can still record usage (e.g. no relevant evidence or
    a late response before the snapshot), so do not equate fast calls
    with successful sources. A successful source needs a recorded call.
    These are bounds on tracker records, not provider HTTP requests.
    """
    planning, verification = FROZEN_EXECUTION_MODES[variant]
    expected_smart = 1 + (planning == "planner") + (verification == "verify")
    ledger = trace["provider_usage_by_model"]
    smart_calls = ledger.get(trace["smart_model"], {}).get("model_calls", 0)
    fast_calls = ledger.get(trace["fast_model"], {}).get("model_calls", 0)
    if smart_calls != expected_smart:
        raise ValueError("recovered smart model call count differs from original treatment roles")
    if not trace["successful_source_count"] <= fast_calls <= trace["source_count"]:
        raise ValueError("recovered fast model call count contradicts original browse outcomes")


def _validate_recovered_trace_cost_provenance(trace: dict) -> None:
    """Keep historical raw trace cost placeholders separate from priced analysis.

    At pinned source c3c15e46, logic.run initializes RunTrace with a zero
    estimated_cost_usd and the explicit not-computed cost status. Offline
    summarization later estimates treatment costs using dated uncached rates.
    A recovered trace must not impersonate provider billing or claim it had
    already estimated the cost at execution time. This verifies only original
    source consistency, not billing, artifact custody, or economic accuracy.
    """
    if trace.get("cost_accounting_status") != ORIGINAL_TRACE_COST_STATUS:
        raise ValueError(
            "recovered trace cost_accounting_status differs from original "
            "unpriced execution trace"
        )
    raw_cost = trace.get("estimated_cost_usd")
    if type(raw_cost) is not float or not math.isfinite(raw_cost) or raw_cost != 0.0:
        raise ValueError(
            "recovered trace estimated_cost_usd is not original zero placeholder"
        )


def _load_original_run_pricing(repo_root: Path) -> dict:
    """Capture exactly the historical treatment checkout's dated price table.

    The source revision anchor constrains re-pricing but is not independent
    evidence of provider billing or historical archive custody.
    """
    raw = packet_builder._read_regular_file_captured(
        repo_root / FROZEN_PRICING_REL, label="original treatment-run pricing table"
    )
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_PRICING_SHA256:
        raise ValueError("original treatment-run pricing table source fingerprint mismatch")
    payload = packet_builder._load_json_object(
        raw, label="original treatment-run pricing table"
    )
    if (payload.get("unit") != "per_1m_text_tokens"
            or payload.get("currency") != "USD"
            or type(payload.get("models")) is not dict):
        raise ValueError("original treatment-run pricing table has invalid units")
    return payload["models"]


def _validate_recovered_efficiency_measurements(
    trace: dict, frozen_row: dict, *, pricing_models: dict
) -> None:
    """Check latency and reprice model usage against frozen treatment results.

    Reproduce the historical run summarizer's uncached-token cost method;
    trace.estimated_cost_usd is only an uncomputed placeholder.
    """
    latency = trace.get("latency_seconds")
    if type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0:
        raise ValueError("recovered trace latency_seconds must be finite and nonnegative")
    try:
        frozen_latency = float(frozen_row["latency_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("frozen treatment latency_seconds is invalid") from exc
    if not math.isfinite(frozen_latency) or latency != frozen_latency:
        raise ValueError("recovered trace latency_seconds differs from frozen treatment CSV")

    if frozen_row.get("cost_status") != "estimated_from_frozen_uncached_rates":
        raise ValueError("frozen treatment cost_status differs from original cost method")
    parts = []
    for model, usage in trace["provider_usage_by_model"].items():
        rates = pricing_models.get(model)
        if type(rates) is not dict:
            raise ValueError(f"recovered model {model!r} has no original frozen price")
        for field in ("input", "output"):
            rate = rates.get(field)
            if type(rate) not in (int, float) or not math.isfinite(rate) or rate < 0:
                raise ValueError(f"original frozen pricing {model!r} {field} is invalid")
        parts.extend((
            usage["prompt_tokens"] / 1_000_000 * rates["input"],
            usage["completion_tokens"] / 1_000_000 * rates["output"],
        ))
    computed_cost = math.fsum(parts)
    try:
        frozen_cost = float(frozen_row["treatment_cost_usd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("frozen treatment_cost_usd is invalid") from exc
    if (not math.isfinite(frozen_cost) or frozen_cost < 0
            or not math.isfinite(computed_cost)
            or not math.isclose(computed_cost, frozen_cost,
                                rel_tol=1e-12, abs_tol=1e-12)):
        raise ValueError("recovered provider ledger cost differs from frozen treatment_cost_usd")


def _trace_report_content_status(
    *,
    repo_root: Path,
    trace_root: Path,
    report_root: Path,
    located_ids: tuple[tuple[str, str], ...],
    run_alignment_status: str,
    task_anchor_status: str,
) -> dict:
    """Diagnose archived trace/report *content* against frozen run/task cells.

    This is a read-only recovery preflight, not a source-authenticity or
    historical-custody proof. The integrated handoff remains authoritative.
    """
    result = {"status": "not_checked_without_published_run_identity",
              "checked": 0, "expected": EXPECTED_TRACES}
    if run_alignment_status != "40_run_ids_match_published_evaluator_not_authenticated":
        return result
    if task_anchor_status != "original_treatment_run_task_manifest_matches":
        return {**result, "status": "not_checked_without_original_run_task_manifest"}

    task_file = repo_root / "experiments/main_budget_tasks.json"
    # The task anchor already passed. A missing or unsafe file now is a
    # late source failure, not a dependency skip: the earlier resource
    # inventory may still say present and otherwise leave no blockers.
    task_file_status = _file_status(task_file)
    if task_file_status != "present_unverified":
        return {
            **result, "status": "invalid_frozen_task_or_evaluator",
            "reason": f"frozen task manifest unavailable after source verification: {task_file_status}",
        }
    source = repo_root / lineage.SUPPORT_REL
    main_source = repo_root / lineage.MAIN_REL
    try:
        task_manifest = packet_builder._load_task_manifest(task_file)
        if task_manifest["sha256"] != frozen_tasks.ORIGINAL_TASK_MANIFEST_SHA256:
            raise ValueError("frozen task manifest changed after source verification")
        main_bytes = _capture_published_csv(
            repo_root, lineage.MAIN_REL,
            label="frozen treatment CSV for recovered trace telemetry"
        )
        main_rows = lineage._read_study_csv(main_bytes, path=main_source)
        evaluator_bytes = _capture_published_csv(
            repo_root, lineage.SUPPORT_REL,
            label="frozen evaluator for recovered trace content"
        )
        rows = lineage._read_study_csv(evaluator_bytes, path=source)
        expected_cells = {
            (variant, task) for variant in VARIANTS for task in lineage.TASKS
        }
        matrix = lineage._matrix(
            rows, label="frozen evaluator trace-content mapping",
            expected_cells=expected_cells, run_identity=True,
        )
        main_matrix = lineage._matrix(
            main_rows, label="frozen treatment trace-content mapping",
            expected_cells=expected_cells, run_identity=False,
        )
        pricing_models = _load_original_run_pricing(repo_root)
        expected_tasks = {
            (variant, row["run_id"]): task
            for (variant, task), row in matrix.items()
        }
        if set(expected_tasks) != set(located_ids):
            raise ValueError("archived run filenames differ from frozen evaluator")
        if set(task_manifest["tasks"]) != set(lineage.TASKS):
            raise ValueError("frozen task manifest has an unexpected task matrix")
    except (OSError, ValueError) as exc:
        return {**result, "status": "invalid_frozen_task_or_evaluator",
                "reason": str(exc)}

    # Diagnose distribution safety with the same versioned validator used by
    # the actual blinded packet builder. A source/runtime drift must not make
    # this recovery receipt claim that report text is ready for annotators.
    try:
        packet_builder.require_loaded_content_validator_unchanged(
            operation="archival blinding-readiness preflight"
        )
    except (OSError, ValueError) as exc:
        return {**result, "status": "invalid_content_validator_contract",
                "reason": str(exc)}

    # Bound aggregate capture to the same maximum as the human-packet builder.
    # The output deliberately contains no report text or treatment results.
    total_bytes = 0
    checked = 0
    candidate_pins: list[tuple] = []
    run_starts: dict[tuple[str, str], datetime] = {}
    run_latencies: dict[tuple[str, str], float] = {}
    run_recordings: dict[tuple[str, str], datetime] = {}
    from urllib.parse import unquote
    for variant, run_id in located_ids:
        trace_file = trace_root / variant / f"{run_id}.json"
        report_file = report_root / run_id / "research_report.md"
        try:
            if (_file_status(trace_file) != "present_unverified"
                    or _file_status(report_file) != "present_unverified"):
                raise ValueError("trace or report is missing, redirected, or unsafe")
            trace_bytes, trace_pin = _capture_recovery_candidate(
                trace_file, label="recovered experimental trace"
            )
            report_bytes, report_pin = _capture_recovery_candidate(
                report_file, label="recovered Markdown report"
            )
            candidate_pins.extend((trace_pin, report_pin))
            total_bytes += len(trace_bytes) + len(report_bytes)
            packet_builder._require_packet_byte_limit(
                total_bytes, label="aggregate recovered trace/report bytes"
            )
            payload = packet_builder._load_json_object(
                trace_bytes, label="recovered experimental trace"
            )
            experiment, trace = packet_builder._validated_trace_sections(
                payload, trace_path=trace_file
            )
            task_id = expected_tasks[(variant, run_id)]
            task_set_id = task_manifest["task_set_id"]
            if (experiment.get("variant_id") != variant
                    or trace.get("variant_id") != variant
                    or experiment.get("task_id") != task_id
                    or trace.get("task_id") != task_id
                    or trace.get("run_id") != run_id):
                raise ValueError("embedded treatment, task, or run identity mismatch")
            if (experiment.get("task_set_id") != task_set_id
                    or trace.get("task_set_id") != task_set_id
                    or trace.get("question") != task_manifest["tasks"][task_id]):
                raise ValueError("trace task-set identity or frozen question mismatch")
            if trace.get("completed") is not True:
                raise ValueError("incomplete treatment cannot enter the human packet")
            # Original logic/run.py records these keys only when run_error
            # is not None, which also makes completed False. Even null or
            # empty placeholders contradict the original successful trace.
            if "error_type" in trace or "error_message" in trace:
                raise ValueError(
                    "recovered completed treatment contains original run-error metadata"
                )
            frozen_row = main_matrix[(variant, task_id)]
            if frozen_row.get("completed") != "True":
                raise ValueError("frozen treatment CSV does not record a completed run")
            expected_planning, expected_verification = FROZEN_EXECUTION_MODES[variant]
            if (experiment.get("planning_mode") != expected_planning
                    or experiment.get("verification_mode") != expected_verification):
                raise ValueError("recovered treatment execution mode differs from frozen arm")
            # The pinned September 2026 logic/run.py persisted these treatment
            # modes in RunTrace *as well as* the ExperimentConfig envelope.
            # A contradictory trace could otherwise impersonate a frozen arm
            # while its source counts and published CSV values still agree.
            for field, expected in (
                ("planning_mode", expected_planning),
                ("verification_mode", expected_verification),
            ):
                if type(trace.get(field)) is not str or trace[field] != expected:
                    raise ValueError(
                        f"recovered trace {field} differs from frozen treatment arm"
                    )
            # The original c3c15e46 ExperimentConfig.from_variant() kept
            # both float defaults; the main runner replaced only task IDs,
            # and run_agent copied these values into the trace. Agreement
            # between two edited values does not establish source fidelity.
            for field, expected in (
                ("browse_timeout_seconds", 60.0),
                ("run_timeout_seconds", 480.0),
            ):
                configured = experiment.get(field)
                recorded = trace.get(field)
                if (
                    type(configured) is not float
                    or type(recorded) is not float
                    or configured != expected
                    or recorded != expected
                ):
                    raise ValueError(
                        f"recovered trace {field} differs from original experiment config"
                    )
            _validate_recovered_shared_execution_config(experiment)
            frozen_budget = main_input_contract.FROZEN_SOURCE_BUDGETS[variant]
            if (type(experiment.get("source_budget")) is not int
                    or experiment["source_budget"] != frozen_budget):
                raise ValueError("recovered experiment budget differs from frozen arm")
            for trace_field, csv_field in TRACE_TO_MAIN_MEASUREMENTS:
                observed = trace.get(trace_field)
                expected = frozen_row.get(csv_field)
                if (type(observed) is not int or observed < 0
                        or str(observed) != expected):
                    raise ValueError(
                        f"recovered trace {trace_field} differs from frozen "
                        f"treatment CSV {csv_field}"
                    )
            run_starts[(variant, task_id)] = _validate_recovered_start_time(trace)
            _validate_recovered_llm_controls(trace)
            _validate_recovered_treatment_verification(trace, variant=variant)
            _validate_recovered_source_ledgers(trace, variant=variant)
            _validate_recovered_derived_telemetry(trace)
            _validate_recovered_search_provenance(trace)
            _validate_recovered_query_budget_allocation(trace, variant=variant)
            _validate_recovered_context_words(trace)
            _validate_recovered_provider_usage(trace)
            _validate_recovered_trace_cost_provenance(trace)
            _validate_recovered_efficiency_measurements(
                trace, frozen_row, pricing_models=pricing_models
            )
            run_latencies[(variant, task_id)] = trace["latency_seconds"]
            run_recordings[(variant, task_id)] = _validate_recovered_persistence_time(
                payload, started_at=run_starts[(variant, task_id)],
                latency_seconds=trace["latency_seconds"],
            )
            _validate_recovered_provider_model_identity(trace)
            _validate_recovered_model_call_roles(trace, variant=variant)
            declared_report = trace.get("report_path")
            if not isinstance(declared_report, str):
                raise ValueError("trace has no valid original report path")
            recorded_path = Path(unquote(declared_report))
            if recorded_path.suffix.lower() == ".pdf":
                recorded_path = recorded_path.with_suffix(".md")
            if recorded_path != Path("outputs") / run_id / "research_report.md":
                raise ValueError("recorded report path does not bind the trace run")
            report_text = report_bytes.decode("utf-8")
            if not report_text.strip():
                raise ValueError("recovered Markdown report is empty or not UTF-8")
            # logic.run records len(report.split()) before persisting the
            # unchanged Markdown via write_md_to_pdf/write_to_file. A different
            # (even nonempty) report with a different length is not that run's
            # original report. This is a consistency check, NOT a content hash.
            if len(report_text.split()) != trace["report_words"]:
                raise ValueError(
                    "recovered report word count differs from the frozen "
                    "treatment trace and CSV"
                )
            # Structural/measurement agreement does not establish that the
            # original question and Markdown are safe to show blinded raters.
            # Reuse the packet builder's treatment/coordinator-leakage audit,
            # including rendered Markdown, attributes, HTML and image checks.
            packet_builder.validate_annotator_facing_content(
                [{"question": trace["question"],
                  "report_markdown": report_text.strip()}],
                label="recovered research report",
            )
        except (OSError, ValueError, UnicodeDecodeError, KeyError) as exc:
            return {"status": "invalid_or_mismatched_trace_report_content",
                    "checked": checked, "expected": EXPECTED_TRACES,
                    "first_failure": f"{variant}/{run_id}: {exc}"}
        checked += 1

    # The pinned c3c15e46 runner executes D3, D6, P6, P6V sequentially for
    # each task in manifest order; it does not run all cells variant-first.
    # An internally coherent 40-cell archive with reversed starts must not
    # be mistaken for the original time-ordered execution.
    previous_start: datetime | None = None
    previous_latency: float | None = None
    previous_recording: datetime | None = None
    for task_id in task_manifest["tasks"]:
        for variant in VARIANTS:
            current_start = run_starts[(variant, task_id)]
            if previous_start is not None:
                if current_start <= previous_start:
                    return {
                        "status": "invalid_or_mismatched_trace_report_content",
                        "checked": checked, "expected": EXPECTED_TRACES,
                        "first_failure": (
                            f"{variant}/{matrix[(variant, task_id)]['run_id']}: "
                            "recovered trace started_at_utc violates original "
                            "task-interleaved treatment execution order"
                        ),
                    }
                # The source runner awaited each completed run before starting
                # the next. Its perf_counter duration cannot grossly exceed
                # the wall-clock gap between consecutive UTC run starts. These
                # clocks are not identical: allow five seconds of drift instead
                # of requiring exact start+duration equality.
                elapsed = (current_start - previous_start).total_seconds()
                if elapsed + ORIGINAL_RUN_CLOCK_DRIFT_ALLOWANCE_SECONDS < previous_latency:
                    return {
                        "status": "invalid_or_mismatched_trace_report_content",
                        "checked": checked, "expected": EXPECTED_TRACES,
                        "first_failure": (
                            f"{variant}/{matrix[(variant, task_id)]['run_id']}: "
                            "recovered completed treatment run implausibly "
                            "overlaps previous run duration"
                        ),
                    }
            # Historical save_run_trace writes each completed trace before the
            # next sequential run begins. A forged save timestamp can disagree
            # with that order while starts, durations and frozen metrics agree.
            if (
                previous_recording is not None
                and (previous_recording - current_start).total_seconds()
                    > ORIGINAL_RUN_CLOCK_DRIFT_ALLOWANCE_SECONDS
            ):
                return {
                    "status": "invalid_or_mismatched_trace_report_content",
                    "checked": checked, "expected": EXPECTED_TRACES,
                    "first_failure": (
                        f"{variant}/{matrix[(variant, task_id)]['run_id']}: "
                        "recovered recorded_at_utc implausibly follows "
                        "the next sequential treatment start"
                    ),
                }
            previous_start = current_start
            previous_latency = run_latencies[(variant, task_id)]
            previous_recording = run_recordings[(variant, task_id)]

    try:
        _verify_recovery_candidate_window(candidate_pins)
        # Per-file pins do not cover directory membership: an extra trace
        # or variant directory can appear without changing any pinned file.
        # Reuse the bounded inventory check after the full content window.
        final_inventory, final_ids = _trace_status(trace_root)
        if (
            final_inventory["status"] != "40_matrix_candidates_unverified"
            or final_ids != located_ids
        ):
            raise ValueError(
                "recovered trace inventory changed during matrix audit: "
                f"{final_inventory['status']}"
            )
    except (OSError, ValueError) as exc:
        return {
            "status": "recovered_candidates_changed_during_audit",
            "checked": checked, "expected": EXPECTED_TRACES,
            "reason": str(exc),
        }
    # Candidate fingerprints alone do not cover the frozen question,
    # measurement, and pricing inputs that governed the content checks.
    try:
        _verify_frozen_content_input_window(repo_root)
    except (OSError, ValueError) as exc:
        return {
            "status": "invalid_frozen_task_or_evaluator",
            "checked": checked, "expected": EXPECTED_TRACES,
            "reason": str(exc),
        }
    return {"status": "40_trace_report_contents_align_to_frozen_cells_not_authenticated",
            "checked": checked, "expected": EXPECTED_TRACES}


def _expected_recovery_paths(
    *,
    repo_root: Path,
    trace_root: Path,
    report_root: Path,
    published_input_anchor: str,
) -> dict:
    """Identify exact missing original files even when fewer than 40 survive.

    The published, fingerprint-verified common-evaluator CSV supplies the
    historical (treatment, task, run_id) mapping. A partial or empty archive
    must not hide which files need retrieval from authorized backups.
    This inventory is coordinator-only and never authenticates candidate
    contents, report text, or archival custody.
    """
    result = {
        "status": "not_checked_without_published_input_anchor",
        "expected": EXPECTED_TRACES,
        "traces_present": 0,
        "reports_present": 0,
        "missing_traces": [],
        "missing_reports": [],
        "unsafe_traces": [],
        "unsafe_reports": [],
    }
    if published_input_anchor != "published_aggregate_matches":
        return result

    source = repo_root / lineage.SUPPORT_REL
    try:
        raw = _capture_published_csv(
            repo_root, lineage.SUPPORT_REL,
            label="published evaluator recovery target CSV"
        )
        rows = lineage._read_study_csv(raw, path=source)
        expected_cells = {
            (variant, task) for variant in VARIANTS for task in lineage.TASKS
        }
        matrix = lineage._matrix(
            rows, label="published recovery target run identities",
            expected_cells=expected_cells, run_identity=True,
        )
    except (OSError, ValueError):
        return {**result, "status": "invalid_published_evaluator_run_ids"}

    for (variant, task_id), row in sorted(matrix.items()):
        run_id = row["run_id"]
        for label, relative, root in (
            ("traces", Path(variant) / f"{run_id}.json", trace_root),
            ("reports", Path(run_id) / "research_report.md", report_root),
        ):
            status = _file_status(root / relative)
            if status == "present_unverified":
                result[f"{label}_present"] += 1
                continue
            target = {
                "variant_id": variant,
                "task_id": task_id,
                "run_id": run_id,
                "relative_path": relative.as_posix(),
                "reason": status,
            }
            destination = "missing" if status == "missing" else "unsafe"
            result[f"{destination}_{label}"].append(target)

    incomplete = any(
        result[key] for key in (
            "missing_traces", "missing_reports", "unsafe_traces", "unsafe_reports"
        )
    )
    result["status"] = (
        "expected_paths_missing_or_unsafe" if incomplete
        else "expected_paths_present_not_authenticated"
    )
    return result


def audit_archive_readiness(
    *,
    repo_root: Path = ROOT,
    trace_root: Path | None = None,
    report_root: Path | None = None,
    packet_root: Path | None = None,
    canonical_root: Path | None = None,
    reverse_root: Path | None = None,
    research_manifest_path: Path | None = None,
    research_manifest_sha256: str | None = None,
    coordinator_manifest_sha256: str | None = None,
) -> dict:
    """Enumerate missing custody inputs without generating or changing evidence."""
    root = Path(repo_root)
    packet = Path(packet_root) if packet_root is not None else root / "outputs/human_eval"
    canonical = (Path(canonical_root) if canonical_root is not None
                 else packet / "annotator-canonical-v1")
    reverse = (Path(reverse_root) if reverse_root is not None
               else packet / "annotator-reverse-v1")
    manifest = (Path(research_manifest_path) if research_manifest_path is not None
                else root / published.MANIFEST)

    sources = {
        "research_manifest": manifest,
        "frozen_task_manifest": root / "experiments/main_budget_tasks.json",
        "frozen_annotator_guide": root / "paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md",
        "treatment_csv": root / published.FROZEN_INPUTS[0],
        "common_evaluator_csv": root / published.FROZEN_INPUTS[1],
    }
    for artifact in exporter.COORDINATOR_ARTIFACTS:
        sources[f"coordinator/{artifact}"] = packet / artifact
    for order, bundle in (("canonical", canonical), ("reverse", reverse)):
        for artifact in exporter.ANNOTATOR_ARTIFACTS:
            sources[f"{order}/{artifact}"] = bundle / artifact

    resources = _resource_inventory(sources)
    traces = Path(trace_root) if trace_root is not None else root / "outputs/experiment_traces"
    reports = Path(report_root) if report_root is not None else root / "outputs"
    trace_candidates, located_ids = _trace_status(traces)
    report_candidates = _report_status(
        reports, tuple(run_id for _variant, run_id in located_ids)
    )
    pins = {
        "research_manifest_file": _pin_status(
            research_manifest_sha256, manifest
        ),
        "coordinator_manifest_file": _pin_status(
            coordinator_manifest_sha256, packet / "manifest.json"
        ),
    }
    # The repository's canonical CSVs and manifest can be verified even when
    # the original report archive is unavailable; never infer report validity.
    if all(resources[label] == "present_unverified" for label in (
        "research_manifest", "treatment_csv", "common_evaluator_csv"
    )):
        try:
            published.verify_published_frozen_inputs(
                repo_root=root, manifest_path=manifest
            )
        except (OSError, ValueError, json.JSONDecodeError):
            input_anchor = "verification_failed"
        else:
            input_anchor = "published_aggregate_matches"
    else:
        input_anchor = "cannot_verify_missing_or_unsafe_input"

    # The treatment/evaluator CSV fingerprint does not cover the task list.
    # Anchor those question bytes separately to the original treatment-run
    # source revision before declaring recovered trace/question concordance.
    try:
        frozen_tasks.verify_frozen_task_manifest(repo_root=root)
    except (OSError, ValueError, UnicodeDecodeError):
        task_anchor = "verification_failed_or_missing"
    else:
        task_anchor = "original_treatment_run_task_manifest_matches"

    run_alignment = _trace_run_alignment(
        repo_root=root, trace_status=trace_candidates["status"],
        located_ids=located_ids, published_input_anchor=input_anchor,
    )
    content_status = _trace_report_content_status(
        repo_root=root, trace_root=traces, report_root=reports,
        located_ids=located_ids, run_alignment_status=run_alignment["status"],
        task_anchor_status=task_anchor,
    )
    recovery_targets = _expected_recovery_paths(
        repo_root=root, trace_root=traces, report_root=reports,
        published_input_anchor=input_anchor,
    )
    gaps = [label for label, status in resources.items() if status != "present_unverified"]
    if trace_candidates["status"] != "40_matrix_candidates_unverified":
        gaps.append("original_experiment_trace_candidates")
    if report_candidates["status"] != "40_report_candidates_unverified":
        gaps.append("original_markdown_report_candidates")
    gaps.extend(label for label, status in pins.items()
                if status != "pin_matches_file_not_authenticated")
    if input_anchor != "published_aggregate_matches":
        gaps.append("published_automated_input_anchor")
    if task_anchor != "original_treatment_run_task_manifest_matches":
        gaps.append("original_experiment_task_manifest_anchor")
    if run_alignment["status"] in (
        "candidate_run_identity_mismatch", "invalid_published_evaluator_run_ids"
    ):
        gaps.append("original_trace_to_evaluator_run_identity")

    if content_status["status"] in (
        "invalid_frozen_task_or_evaluator",
        "invalid_or_mismatched_trace_report_content",
        "invalid_content_validator_contract",
        "recovered_candidates_changed_during_audit",
    ):
        gaps.append("original_trace_report_content_alignment")

    if recovery_targets["status"] in (
        "invalid_published_evaluator_run_ids",
        "expected_paths_missing_or_unsafe",
    ):
        gaps.append("original_expected_run_archive_paths")

    # A complete matrix can take much longer to validate than the initial
    # inventory and pin reads. Before reporting zero blockers, recheck the
    # required resource paths and both manifest pins. Never upgrade an
    # initially blocked observation just because a resource appeared later.
    if not gaps:
        resources = _resource_inventory(sources)
        pins = {
            "research_manifest_file": _pin_status(research_manifest_sha256, manifest),
            "coordinator_manifest_file": _pin_status(
                coordinator_manifest_sha256, packet / "manifest.json"
            ),
        }
        gaps.extend(label for label, status in resources.items()
                    if status != "present_unverified")
        gaps.extend(label for label, status in pins.items()
                    if status != "pin_matches_file_not_authenticated")

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "blocked" if gaps else "candidate_inputs_present_not_verified",
        "resources": resources,
        "trace_candidates": trace_candidates,
        "report_candidates": report_candidates,
        "trace_to_published_evaluator": run_alignment,
        "trace_report_content": content_status,
        "expected_recovery_paths": recovery_targets,
        "independent_pins": pins,
        "published_automated_input_anchor": input_anchor,
        "frozen_task_manifest_anchor": task_anchor,
        "blockers": sorted(gaps),
        "handoff_verified": False,
        "human_ratings_used": False,
        "treatments_rerun": False,
        "interpretation": (
            "Recovery inventory only. Even with zero blockers, independently "
            "run the integrated source-pinned handoff verifier on the original "
            "archive; no human validation or historical authenticity is claimed."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--trace-root", type=Path)
    parser.add_argument("--report-root", type=Path)
    parser.add_argument("--packet-root", type=Path)
    parser.add_argument("--canonical-root", type=Path)
    parser.add_argument("--reverse-root", type=Path)
    parser.add_argument("--research-manifest", type=Path)
    parser.add_argument("--research-manifest-sha256")
    parser.add_argument("--coordinator-manifest-sha256")
    parser.add_argument("--require-candidates", action="store_true",
                        help="Exit nonzero unless all evidence candidates and pins are supplied")
    args = parser.parse_args()
    result = audit_archive_readiness(
        repo_root=args.repo_root, trace_root=args.trace_root,
        report_root=args.report_root, packet_root=args.packet_root,
        canonical_root=args.canonical_root, reverse_root=args.reverse_root,
        research_manifest_path=args.research_manifest,
        research_manifest_sha256=args.research_manifest_sha256,
        coordinator_manifest_sha256=args.coordinator_manifest_sha256,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(args.require_candidates and result["status"] == "blocked")


if __name__ == "__main__":
    raise SystemExit(main())
