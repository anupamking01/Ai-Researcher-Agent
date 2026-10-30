"""Compare original/recovery treatment sources in two historical VERA ZIPs.

The source bytes must be unchanged across evaluator-only recovery. Both ZIPs
are individually checked against GitHub's *same-provider* historical job-log
fingerprints before comparing all 40 trace/report hashes. A match is NOT an
independent historical custody attestation or permission to distribute human
evaluation packets. No extraction, evaluator runs, or treatments occur.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile
from urllib.parse import unquote

from scripts import audit_human_eval_archive_readiness as readiness
from scripts import audit_recovered_artifact_treatment_matrix as matrix
from scripts import preflight_recovered_artifact_zip as preflight
from scripts import verify_frozen_main_study_tasks as frozen_tasks
from logic.prompts import generate_verification_prompt


class RecoveryConcordanceError(ValueError):
    """Original and evaluator-recovery experimental sources differ."""


def _archive_source_snapshot(path: Path) -> tuple[tuple[int, ...], str]:
    """Capture a stable, no-follow ZIP generation and its current byte digest.

    Unlike each individual ZIP preflight, this snapshot also bounds the
    *combined* two-archive comparison window. It does not authenticate custody.
    """
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as handle:
            before = os.fstat(handle.fileno())
            pathname = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or not preflight._unchanged(before, pathname):
                raise RecoveryConcordanceError(
                    "archive source must be an unchanged regular file, not a link"
                )
            if not 0 < before.st_size <= preflight.MAX_ARCHIVE_BYTES:
                raise RecoveryConcordanceError("archive source size outside preflight bounds")
            digest = preflight._fingerprint(handle)
            if (
                not preflight._unchanged(before, os.fstat(handle.fileno()))
                or not preflight._unchanged(before, os.stat(path, follow_symlinks=False))
            ):
                raise RecoveryConcordanceError("archive changed during source snapshot")
    except OSError as exc:
        raise RecoveryConcordanceError(
            f"cannot safely capture archive source {path}: {exc}"
        ) from exc
    generation = (
        before.st_dev, before.st_ino, before.st_mode, before.st_size,
        before.st_mtime_ns, before.st_ctime_ns,
    )
    return generation, digest



def _frozen_questions_snapshot(
    repo_root: Path,
) -> tuple[dict[str, str], tuple[int, ...], str]:
    """Capture the ten original-run questions from the SHA-256-pinned task file.

    This is a Git-revision source anchor, not an independent historical archive.
    Rechecking the file generation also protects the combined ZIP comparison
    against same-byte replacement of this additional governing input.
    """
    path = Path(repo_root) / frozen_tasks.TASK_MANIFEST_REL
    try:
        before = matrix._generation(path)
        raw = matrix.packet_builder._read_regular_file_captured(
            path, label="original treatment-run task manifest"
        )
        after = matrix._generation(path)
    except (OSError, ValueError) as exc:
        raise RecoveryConcordanceError(
            "cannot safely capture original treatment-run task manifest"
        ) from exc
    if before != after:
        raise RecoveryConcordanceError(
            "original treatment-run task manifest changed during capture"
        )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != frozen_tasks.ORIGINAL_TASK_MANIFEST_SHA256:
        raise RecoveryConcordanceError(
            "original treatment-run source task manifest differs from pinned bytes"
        )
    # The pinned bytes must also retain the original ten-task question contract.
    manifest = json.loads(raw)
    task_rows = manifest.get("tasks") if type(manifest) is dict else None
    if (
        type(manifest) is not dict
        or manifest.get("task_set_id") != "main-budget-v1-2026-09-11"
        or manifest.get("frozen_before_execution") is not True
        or type(task_rows) is not list
        or len(task_rows) != 10
    ):
        raise RecoveryConcordanceError(
            "original treatment-run task manifest contract is invalid"
        )
    questions = {}
    for number, task in enumerate(task_rows, 1):
        task_id = f"main-{number:02d}"
        if (
            type(task) is not dict
            or task.get("id") != task_id
            or type(task.get("question")) is not str
            or not task["question"].strip()
        ):
            raise RecoveryConcordanceError(
                "original treatment-run task question contract is invalid"
            )
        questions[task_id] = task["question"]
    return questions, after, digest


def _frozen_pricing_snapshot(repo_root: Path) -> tuple[dict, tuple[int, ...], str]:
    """Pin the original-run uncached price table across both archive audits.

    Reuse the historical readiness validator's SHA-256-pinned pricing loader,
    while monitoring the on-disk generation for swaps during verification.
    """
    path = Path(repo_root) / readiness.FROZEN_PRICING_REL
    try:
        before = matrix._generation(path)
        pricing_models = readiness._load_original_run_pricing(repo_root)
        after = matrix._generation(path)
    except (OSError, ValueError) as exc:
        raise RecoveryConcordanceError(
            "cannot safely capture original treatment-run pricing table"
        ) from exc
    if before != after:
        raise RecoveryConcordanceError(
            "original treatment-run pricing table changed during capture"
        )
    return pricing_models, after, readiness.ORIGINAL_PRICING_SHA256


# This treatment export is pinned by the published analysis input manifest.
# Its correspondence check is not independently authenticated archive custody.
PUBLISHED_TREATMENT_CSV_SHA256 = (
    "966ea80519af5ea7b832c86d7868525a4ef75874f396f242291e3be949382a0e"
)
TREATMENT_RESOURCE_FIELDS = {
    "source_budget": "source_budget",
    "successful_sources": "successful_source_count",
    "failed_sources": "failed_source_count",
    "search_calls": "search_call_count",
    "model_calls": "model_call_count",
    "total_tokens": "total_tokens",
    "report_words": "report_words",
}


def _frozen_treatment_snapshot(
    repo_root: Path,
) -> tuple[dict[tuple[str, str], dict[str, str]], tuple[int, ...], str]:
    """Pin published treatment-resource counts across the two-ZIP audit.

    These historical export fields were produced from the archived traces.
    Hash-pinned comparison catches contradictory resource-ledger claims even
    when two archive copies are internally consistent and byte-identical.
    """
    path = Path(repo_root) / matrix.lineage.MAIN_REL
    try:
        before = matrix._generation(path)
        raw = matrix.packet_builder._read_regular_file_captured(
            path, label="published treatment resource CSV",
        )
        after = matrix._generation(path)
    except (OSError, ValueError) as exc:
        raise RecoveryConcordanceError(
            "cannot safely capture published treatment resource CSV"
        ) from exc
    if before != after:
        raise RecoveryConcordanceError(
            "published treatment CSV changed during capture"
        )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PUBLISHED_TREATMENT_CSV_SHA256:
        raise RecoveryConcordanceError(
            "published treatment CSV differs from frozen analysis input fingerprint"
        )
    rows = matrix.lineage._matrix(
        matrix.lineage._read_study_csv(raw, path=path),
        label="frozen published treatment resources",
        expected_cells=matrix.EXPECTED_CELLS,
        run_identity=False,
    )
    return rows, after, digest


# The original 2026-09-13 evaluator-only recovery workflow explicitly
# documented this missing set before any recovery evaluator calls. It is
# an operational lineage anchor, not a new research-analysis selection.
RECOVERY_ONLY_EVALUATOR_CELLS = frozenset({
    ("P6V", "main-02"),
    ("P6V", "main-08"),
    ("P6V", "main-10"),
})


def _evaluator_cache_map(
    audit: dict, expected_cells: set[tuple[str, str]],
) -> dict[tuple[str, str], tuple[str, int]]:
    """Locate all evaluator caches without ignoring alternate ZIP layouts."""
    prefix = audit["source_layout_prefix"]
    expected_paths = {
        f"{prefix}posthoc_evaluations/{variant}/{task}": (variant, task)
        for variant, task in expected_cells
    }
    expected_paths = {
        path + ".json": identity for path, identity in expected_paths.items()
    }
    observed = {}
    for member in audit["observed_evaluator_cache_members"]:
        path = member["path"]
        if path not in expected_paths:
            raise RecoveryConcordanceError(
                "unselected or mixed-layout evaluator cache member: " + path
            )
        identity = expected_paths[path]
        if identity in observed:
            raise RecoveryConcordanceError("duplicate evaluator cache identity")
        observed[identity] = (member["sha256"], member["uncompressed_bytes"])
    return observed


def _verify_evaluator_cache_continuity(
    original: dict, recovered: dict,
) -> tuple[int, int]:
    """Check 37 historical evaluator caches survived the 3-cell resume.

    This checks decompressed bytes and membership, not whether any evaluator
    JSON is semantically valid or independently authentic.
    """
    cells = original["observed_source_content_manifest"]["cells"]
    expected = {(cell["treatment"], cell["task_id"]) for cell in cells}
    if len(expected) != 40 or not RECOVERY_ONLY_EVALUATOR_CELLS <= expected:
        raise RecoveryConcordanceError("frozen evaluator cell matrix is incomplete")
    original_cache = _evaluator_cache_map(original, expected)
    recovery_cache = _evaluator_cache_map(recovered, expected)
    preserved = expected - RECOVERY_ONLY_EVALUATOR_CELLS
    if set(original_cache) != preserved:
        raise RecoveryConcordanceError(
            "original evaluator cache is not the historical 37-cell partial state"
        )
    if set(recovery_cache) != expected:
        raise RecoveryConcordanceError(
            "recovered evaluator cache is not the complete 40-cell state"
        )
    for identity in sorted(preserved):
        if original_cache[identity] != recovery_cache[identity]:
            raise RecoveryConcordanceError(
                "preserved evaluator cache bytes changed for "
                + "/".join(identity)
            )
    return len(preserved), len(RECOVERY_ONLY_EVALUATOR_CELLS)



# A recovered cache record is expected to be small. Bound the second, semantic
# inspection independently of the already-bounded structural ZIP preflight.
MAX_EVALUATOR_CACHE_JSON_BYTES = 4 * 1024 * 1024


def _unique_json_pairs(pairs: list[tuple[str, object]]) -> dict:
    """Do not let JSON's last-key-wins behavior spoof evaluator identities."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryConcordanceError("duplicate key in evaluator cache JSON")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> None:
    raise RecoveryConcordanceError(
        "nonfinite numeric token in evaluator cache JSON: " + value
    )


def _finite_evaluator_cache_json_float(token: str) -> float:
    """Reject JSON exponent overflow even in non-score evaluator metadata."""
    value = float(token)
    if not math.isfinite(value):
        raise RecoveryConcordanceError(
            "nonfinite exponent in evaluator cache JSON: " + token
        )
    return value


def _verify_historical_evaluator_examples(payload: dict, *, path: str) -> None:
    """Match the original normalized cache's bounded qualitative-examples shape.

    Historical verifier normalization always saved a list of at most eight
    examples, even if the model supplied none or an invalid examples field.
    Shape verification does not corroborate the model's claim judgments.
    """
    examples = payload.get("examples")
    if type(examples) is not list or len(examples) > 8:
        raise RecoveryConcordanceError(
            "historical evaluator examples must be a list of at most eight items: "
            + path
        )


# The CSV is the published, byte-fingerprint-pinned automated measurement export.
# Compare archived measurements to it, without recomputing or optimizing any scores.
PUBLISHED_EVALUATOR_COUNT_FIELDS = (
    "claims_checked", "supported", "partially_supported",
    "unsupported", "contradicted", "total_tokens",
)
PUBLISHED_EVALUATOR_DECIMAL_FIELDS = (
    "strict_support_rate", "estimated_cost_usd",
)


def _verify_published_evaluator_measurements(
    payload: dict, published: dict[str, str], *, path: str,
) -> None:
    """Reject a cache whose recorded measurements disagree with frozen CSV.

    Exact numeric correspondence is not independent scoring validation:
    the archive and published CSV could share an upstream error.
    """
    for field in PUBLISHED_EVALUATOR_COUNT_FIELDS:
        value = payload.get(field)
        try:
            expected = int(published[field])
        except (ValueError, TypeError, KeyError) as exc:
            raise RecoveryConcordanceError(
                "published evaluator has an invalid integer field: " + field
            ) from exc
        if type(value) is not int or value != expected:
            raise RecoveryConcordanceError(
                f"archived evaluator {field} differs from published CSV: {path}"
            )

    checked = payload["claims_checked"]
    categories = ("supported", "partially_supported", "unsupported", "contradicted")
    if (
        not 0 < checked <= 12
        or payload["total_tokens"] < 0
        or any(payload[field] < 0 for field in categories)
        or sum(payload[field] for field in categories) != checked
    ):
        raise RecoveryConcordanceError(
            "archived evaluator claim accounting is inconsistent: " + path
        )

    for field in PUBLISHED_EVALUATOR_DECIMAL_FIELDS:
        value = payload.get(field)
        if type(value) not in (int, float):
            raise RecoveryConcordanceError(
                f"archived evaluator {field} must be numeric: {path}"
            )
        try:
            observed = Decimal(str(value))
            expected = Decimal(published[field])
        except (InvalidOperation, TypeError, KeyError, ValueError) as exc:
            raise RecoveryConcordanceError(
                f"invalid published evaluator decimal value for {field}: {path}"
            ) from exc
        if not observed.is_finite() or not expected.is_finite() or observed != expected:
            raise RecoveryConcordanceError(
                f"archived evaluator {field} differs from published CSV: {path}"
            )

    if (
        not Decimal(0) <= Decimal(str(payload["strict_support_rate"])) <= Decimal(1)
        or Decimal(str(payload["estimated_cost_usd"])) < 0
        or float(payload["strict_support_rate"]) != payload["supported"] / checked
    ):
        raise RecoveryConcordanceError(
            "archived evaluator support rate or cost is inconsistent: " + path
        )
    if published.get("evidence_status") == "zero_successful_sources" and (
        payload["unsupported"] != checked
        or any(payload[field] != 0 for field in (
            "supported", "partially_supported", "contradicted",
        ))
    ):
        raise RecoveryConcordanceError(
            "zero-source published evaluator cell has unsupported score: " + path
        )




# The original treatment and evaluator-recovery workflow revisions
# c3c15e46a8eec3a8bbc24c968eedc0548172a897 and
# 8733ce492abc74e7b2966ed22ce08d3fddec43ca render the same 12-claim
# prompt. Pin a rendered canary independently of future template edits.
# This anchors the prompt contract, not the model's response or historical custody.
# Workflow source revisions c3c15e46 and 8733ce49 fixed the evaluator's
# environment to this model/temperature and its record-writing cost label.
# These are metadata checks, not proof of a remote model request or billing.
HISTORICAL_EVALUATOR_MODEL = "gpt-5.6-terra"
HISTORICAL_EVALUATOR_TEMPERATURE = 1.0
HISTORICAL_EVALUATOR_COST_METHOD = "frozen uncached rates"
HISTORICAL_EVALUATOR_MAX_CLAIMS = 12
HISTORICAL_EVALUATOR_PROMPT_CANARY_SHA256 = (
    "cdc7a77cb3e8334722d768afbd71a033c51a2006793992ab670a1ff10c4aac4f"
)


def _verify_historical_evaluator_prompt_canary() -> None:
    rendered = generate_verification_prompt(
        "VERA_QUESTION_CANARY", "VERA_REPORT_CANARY", "VERA_EVIDENCE_CANARY",
        max_claims=HISTORICAL_EVALUATOR_MAX_CLAIMS,
    )
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    if digest != HISTORICAL_EVALUATOR_PROMPT_CANARY_SHA256:
        raise RecoveryConcordanceError(
            "current evaluator prompt template differs from historical 12-claim canary"
        )


# Mirror the historical evaluator's saved research-query text contract without
# collecting new evidence. Bounds are separate from the whole-ZIP preflight.
MAX_EVALUATOR_EVIDENCE_FILES_PER_RUN = 64
MAX_EVALUATOR_EVIDENCE_MEMBER_BYTES = 8 * 1024 * 1024
MAX_EVALUATOR_EVIDENCE_TOTAL_BYTES = 32 * 1024 * 1024
MAX_EVALUATOR_PROMPT_REPORT_BYTES = 16 * 1024 * 1024
FROZEN_NO_EVIDENCE_SENTINEL = (
    "[NO RETRIEVED EVIDENCE WAS AVAILABLE FOR THIS TREATMENT RUN. "
    "The run recorded zero successful retrieved sources. Do not use outside knowledge.]"
)


def _snapshot_archived_evaluator_evidence(
    archive: Path,
    audit: dict,
    published_treatments: dict[tuple[str, str], dict[str, str]],
    published_evaluators: dict[tuple[str, str], dict[str, str]],
    frozen_questions: dict[str, str],
) -> dict[tuple[str, str], dict]:
    """Preserve raw evidence files and reconstruct the frozen evaluator input.

    This checks source consistency, not the truth of retrieved statements,
    original ZIP custody or whether schema-v1 evaluation actually used them.
    """
    cells = audit["observed_source_content_manifest"]["cells"]
    if len(cells) != 40:
        raise RecoveryConcordanceError("historical evaluator evidence matrix is incomplete")
    prefix = audit["source_layout_prefix"]
    result = {}
    try:
        with zipfile.ZipFile(archive, "r") as source:
            names = source.namelist()
            for cell in cells:
                variant, task, run_id = (
                    cell["treatment"], cell["task_id"], cell["run_id"]
                )
                identity = (variant, task)
                root = f"{prefix}{run_id}/"
                selected = sorted(
                    name for name in names
                    if name.startswith(root)
                    and "/" not in name[len(root):]
                    and name[len(root):].startswith("research-query-")
                    and name.endswith(".txt")
                )
                if len(selected) > MAX_EVALUATOR_EVIDENCE_FILES_PER_RUN:
                    raise RecoveryConcordanceError(
                        f"too many historical evaluator evidence files: {variant}/{task}"
                    )
                raw_members = []
                parts = []
                total = 0
                for name in selected:
                    info = source.getinfo(name)
                    if not 0 <= info.file_size <= MAX_EVALUATOR_EVIDENCE_MEMBER_BYTES:
                        raise RecoveryConcordanceError(
                            f"historical evaluator evidence member exceeds bound: {name}"
                        )
                    total += info.file_size
                    if total > MAX_EVALUATOR_EVIDENCE_TOTAL_BYTES:
                        raise RecoveryConcordanceError(
                            f"historical evaluator evidence aggregate exceeds bound: {variant}/{task}"
                        )
                    with source.open(name, "r") as member:
                        raw = member.read(info.file_size + 1)
                    if len(raw) != info.file_size:
                        raise RecoveryConcordanceError(
                            f"historical evaluator evidence ZIP size mismatch: {name}"
                        )
                    try:
                        stripped = raw.decode("utf-8").strip()
                    except UnicodeDecodeError as exc:
                        raise RecoveryConcordanceError(
                            f"historical evaluator evidence is not UTF-8: {name}"
                        ) from exc
                    raw_members.append((
                        name[len(root):], len(raw), hashlib.sha256(raw).hexdigest()
                    ))
                    if stripped:
                        parts.append(stripped)
                joined = "\n\n".join(parts)
                if joined:
                    evidence = joined
                    evidence_status = "retrieved_evidence"
                else:
                    try:
                        successful = int(published_treatments[identity]["successful_sources"])
                    except (KeyError, ValueError, TypeError) as exc:
                        raise RecoveryConcordanceError(
                            "frozen treatment successful-source accounting is invalid"
                        ) from exc
                    if successful != 0:
                        raise RecoveryConcordanceError(
                            f"historical evaluator has no saved evidence despite "
                            f"successful treatment retrievals: {variant}/{task}"
                        )
                    evidence = FROZEN_NO_EVIDENCE_SENTINEL
                    evidence_status = "zero_successful_sources"
                published_status = published_evaluators[identity].get("evidence_status")
                if published_status not in ("", evidence_status):
                    raise RecoveryConcordanceError(
                        f"archived evaluator evidence status differs from frozen "
                        f"published evaluation: {variant}/{task}"
                    )
                # An evaluator's schema-v2 prompt hash must describe the
                # *rendered historical 12-claim rubric*, not an arbitrary
                # plausible SHA. Preserve Markdown newlines exactly as read
                # by _report_text in the original evaluator.
                report_path = f"{root}research_report.md"
                report_size = cell["report_uncompressed_bytes"]
                if not 0 < report_size <= MAX_EVALUATOR_PROMPT_REPORT_BYTES:
                    raise RecoveryConcordanceError(
                        f"historical evaluator prompt report exceeds bound: {report_path}"
                    )
                with source.open(report_path, "r") as member:
                    report_raw = member.read(report_size + 1)
                if (
                    len(report_raw) != report_size
                    or hashlib.sha256(report_raw).hexdigest() != cell["report_sha256"]
                ):
                    raise RecoveryConcordanceError(
                        f"historical prompt report disagrees with verified ZIP scan: {report_path}"
                    )
                try:
                    report_text = report_raw.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise RecoveryConcordanceError(
                        f"historical evaluator prompt report is not UTF-8: {report_path}"
                    ) from exc
                prompt = generate_verification_prompt(
                    frozen_questions[task], report_text, evidence,
                    max_claims=HISTORICAL_EVALUATOR_MAX_CLAIMS,
                )
                raw_evidence = evidence.encode("utf-8")
                raw_prompt = prompt.encode("utf-8")
                result[identity] = {
                    "member_fingerprints": tuple(raw_members),
                    "input_fingerprint": {
                        "byte_size": len(raw_evidence),
                        "sha256": hashlib.sha256(raw_evidence).hexdigest(),
                    },
                    "prompt_fingerprint": {
                        "byte_size": len(raw_prompt),
                        "sha256": hashlib.sha256(raw_prompt).hexdigest(),
                    },
                    "evidence_status": evidence_status,
                }
    except (zipfile.BadZipFile, KeyError) as exc:
        raise RecoveryConcordanceError(
            "historical evaluator evidence members cannot be read from verified ZIP"
        ) from exc
    if len(result) != 40:
        raise RecoveryConcordanceError("historical evaluator evidence identities are incomplete")
    return result



def _verify_historical_evaluator_configuration(
    payload: dict, *, expected_evidence_status: str, path: str,
) -> None:
    """Check the fixed post-hoc measurement configuration in archived caches.

    Source revisions c3c15e46 and 8733ce49 use the same model, temperature,
    12-claim cap and frozen-cost label. The original schema-v1 record writer
    omitted evidence_status; schema-v2 requires it, and any recorded status
    must agree with the reconstructed archived evidence, not merely a CSV.
    This checks recorded metadata, not remote API requests or billed costs.
    """
    if payload.get("evaluator_model") != HISTORICAL_EVALUATOR_MODEL:
        raise RecoveryConcordanceError(
            "historical evaluator_model differs from frozen common evaluator: " + path
        )
    temperature = payload.get("temperature")
    if (
        type(temperature) not in (int, float)
        or not math.isfinite(temperature)
        or float(temperature) != HISTORICAL_EVALUATOR_TEMPERATURE
    ):
        raise RecoveryConcordanceError(
            "historical evaluator temperature differs from frozen common evaluator: " + path
        )
    if (
        type(payload.get("max_claims")) is not int
        or payload["max_claims"] != HISTORICAL_EVALUATOR_MAX_CLAIMS
    ):
        raise RecoveryConcordanceError(
            "historical evaluator max_claims differs from frozen rubric: " + path
        )
    if payload.get("cost_method") != HISTORICAL_EVALUATOR_COST_METHOD:
        raise RecoveryConcordanceError(
            "historical evaluator cost_method differs from frozen accounting: " + path
        )
    status = payload.get("evidence_status")
    if (
        (status is None and payload["schema_version"] != 1)
        or (status is not None and status != expected_evidence_status)
    ):
        raise RecoveryConcordanceError(
            "historical evaluator evidence_status disagrees with archived retrieval inputs: "
            + path
        )


def _verify_historical_evaluator_provider_usage(
    payload: dict, *, path: str,
) -> None:
    """Check the recorded one-call evaluator token ledger, not remote billing.

    Original treatment/recovery evaluator writers persisted UsageTracker.by_model.
    A matching published total alone does not establish a consistent recorded
    prompt/completion split or that usage was attributed to the frozen model.
    """
    ledgers = payload.get("provider_usage_by_model")
    if (
        type(ledgers) is not dict
        or set(ledgers) != {HISTORICAL_EVALUATOR_MODEL}
        or type(ledgers[HISTORICAL_EVALUATOR_MODEL]) is not dict
    ):
        raise RecoveryConcordanceError(
            "historical evaluator provider_usage_by_model must contain exactly "
            "the frozen evaluator model: " + path
        )
    usage = ledgers[HISTORICAL_EVALUATOR_MODEL]
    for field in (
        "model_calls", "unavailable_calls", "prompt_tokens",
        "completion_tokens", "total_tokens",
    ):
        value = usage.get(field)
        if type(value) is not int or value < 0:
            raise RecoveryConcordanceError(
                f"historical evaluator provider_usage_by_model.{field} "
                f"must be a nonnegative integer: {path}"
            )
    if usage["model_calls"] != 1 or usage["unavailable_calls"] != 0:
        raise RecoveryConcordanceError(
            "historical evaluator provider usage requires exactly one model "
            "call with no unavailable usage: " + path
        )
    computed_total = usage["prompt_tokens"] + usage["completion_tokens"]
    if (
        computed_total <= 0
        or usage["total_tokens"] != computed_total
        or type(payload.get("total_tokens")) is not int
        or payload["total_tokens"] != computed_total
    ):
        raise RecoveryConcordanceError(
            "historical evaluator provider token sums disagree with published "
            "total_tokens: " + path
        )


def _verify_historical_evaluator_estimated_cost(
    payload: dict, *, pricing_models: dict, path: str,
) -> None:
    """Reprice the saved evaluator token split using original uncached rates.

    The published evaluator CSV stores one cost per run, but cannot reveal
    whether its archived provider-usage prompt/completion split supports it.
    This duplicates no model request and verifies no provider invoice.
    """
    from scripts.summarize_pilot import _estimate_reported_token_cost

    # The preceding provider-usage gate has already validated one model call,
    # the exact model name, and nonnegative integer prompt/completion counts.
    try:
        expected, method = _estimate_reported_token_cost(
            payload["provider_usage_by_model"], {"models": pricing_models},
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise RecoveryConcordanceError(
            "historical evaluator cost cannot be repriced from recorded usage: " + path
        ) from exc
    if (
        method != "estimated_from_frozen_uncached_rates"
        or expected is None
        or not math.isfinite(expected)
        or expected < 0
    ):
        raise RecoveryConcordanceError(
            "historical evaluator model has no valid original frozen price: " + path
        )
    stored = payload.get("estimated_cost_usd")
    # Original evaluator resume validation used this exact float calculation
    # and equality check, not a tolerance or a current-market rate.
    if (
        type(stored) not in (int, float)
        or not math.isfinite(stored)
        or float(stored) != expected
    ):
        raise RecoveryConcordanceError(
            "historical evaluator estimated_cost_usd differs from provider "
            "prompt/completion split at frozen rates: " + path
        )


def _verify_evaluator_report_input_fingerprint(
    payload: dict, source_cell: dict, *, expected_question: str,
    expected_evidence_fingerprint: dict, expected_prompt_fingerprint: dict,
    path: str,
) -> bool:
    """Bind schema-v2 evaluator inputs to the report and original task question.

    Schema v1 had no input fingerprints. Source-revision question binding is
    not independent evidence custody, nor authentication of prompt/evidence.
    """
    version = payload["schema_version"]
    if version == 1:
        if "input_fingerprints" in payload:
            raise RecoveryConcordanceError(
                "schema-version-1 evaluator cache cannot declare input fingerprints: " + path
            )
        return False
    fingerprints = payload.get("input_fingerprints")
    if (
        type(fingerprints) is not dict
        or set(fingerprints)
        != {"algorithm", "encoding", "question", "report", "evidence", "prompt"}
        or fingerprints.get("algorithm") != "sha256"
        or fingerprints.get("encoding") != "utf-8"
    ):
        raise RecoveryConcordanceError(
            "invalid schema-version-2 evaluator input_fingerprints: " + path
        )
    for name in ("question", "report", "evidence", "prompt"):
        entry = fingerprints.get(name)
        if (
            type(entry) is not dict
            or set(entry) != {"byte_size", "sha256"}
            or type(entry.get("byte_size")) is not int
            or entry["byte_size"] < 0
            or type(entry.get("sha256")) is not str
            or preflight.HEX_SHA256.fullmatch(entry["sha256"]) is None
        ):
            raise RecoveryConcordanceError(
                "invalid schema-version-2 evaluator input_fingerprints: " + path
            )
    report = fingerprints["report"]
    if (
        report["sha256"] != source_cell["report_sha256"]
        or report["byte_size"] != source_cell["report_uncompressed_bytes"]
    ):
        raise RecoveryConcordanceError(
            "evaluator input report fingerprint does not match archived source report: " + path
        )
    question_bytes = expected_question.encode("utf-8")
    question = fingerprints["question"]
    if (
        question["byte_size"] != len(question_bytes)
        or question["sha256"] != hashlib.sha256(question_bytes).hexdigest()
    ):
        raise RecoveryConcordanceError(
            "evaluator input question fingerprint does not match original frozen task: " + path
        )
    if fingerprints["evidence"] != expected_evidence_fingerprint:
        raise RecoveryConcordanceError(
            "evaluator input evidence fingerprint does not match archived retrieval text: " + path
        )
    if fingerprints["prompt"] != expected_prompt_fingerprint:
        raise RecoveryConcordanceError(
            "evaluator prompt fingerprint does not match the frozen 12-claim rubric and archived inputs: " + path
        )
    return True


def _verify_evaluator_cache_json_identities(
    archive: Path, audit: dict, published_rows: dict[tuple[str, str], dict[str, str]],
    frozen_questions: dict[str, str],
    evidence_snapshots: dict[tuple[str, str], dict],
    pricing_models: dict,
) -> tuple[int, int]:
    """Bind every archived evaluator record to its frozen execution identity.

    Audit identity and exact published numeric score/cost lineage. This does
    not independently score claims, validate input evidence, or prove custody.
    """
    cells = audit["observed_source_content_manifest"]["cells"]
    expected_run_ids = {
        (cell["treatment"], cell["task_id"]): cell["run_id"]
        for cell in cells
    }
    source_cells = {
        (cell["treatment"], cell["task_id"]): cell for cell in cells
    }
    if len(cells) != 40 or len(expected_run_ids) != 40:
        raise RecoveryConcordanceError("frozen evaluator run identities are incomplete")
    cache = _evaluator_cache_map(audit, set(expected_run_ids))
    prefix = audit["source_layout_prefix"]
    report_input_bindings_checked = 0
    try:
        with zipfile.ZipFile(archive, "r") as source:
            for (variant, task), (expected_digest, size) in sorted(cache.items()):
                path = f"{prefix}posthoc_evaluations/{variant}/{task}.json"
                if not 0 < size <= MAX_EVALUATOR_CACHE_JSON_BYTES:
                    raise RecoveryConcordanceError(
                        "evaluator cache JSON size outside semantic audit bound: " + path
                    )
                with source.open(path, "r") as member:
                    raw = member.read(size + 1)
                if len(raw) != size or hashlib.sha256(raw).hexdigest() != expected_digest:
                    raise RecoveryConcordanceError(
                        "evaluator cache bytes disagree with verified ZIP scan: " + path
                    )
                try:
                    payload = json.loads(
                        raw.decode("utf-8"),
                        object_pairs_hook=_unique_json_pairs,
                        parse_constant=_reject_nonfinite_json,
                        parse_float=_finite_evaluator_cache_json_float,
                    )
                except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
                    raise RecoveryConcordanceError(
                        "invalid evaluator cache JSON: " + path
                    ) from exc
                if type(payload) is not dict:
                    raise RecoveryConcordanceError(
                        "evaluator cache JSON must be an object: " + path
                    )
                if (
                    type(payload.get("schema_version")) is not int
                    or payload["schema_version"] not in (1, 2)
                ):
                    raise RecoveryConcordanceError(
                        "evaluator cache JSON schema_version must be 1 or 2: " + path
                    )
                expected_identity = {
                    "study_id": "budget-main-v1",
                    "variant_id": variant,
                    "task_id": task,
                    "run_id": expected_run_ids[(variant, task)],
                }
                for field, expected in expected_identity.items():
                    if payload.get(field) != expected:
                        raise RecoveryConcordanceError(
                            f"evaluator cache {field} differs from frozen run: {path}"
                        )
                _verify_published_evaluator_measurements(
                    payload, published_rows[(variant, task)], path=path,
                )
                _verify_historical_evaluator_examples(payload, path=path)
                _verify_historical_evaluator_configuration(
                    payload,
                    expected_evidence_status=evidence_snapshots[(variant, task)]["evidence_status"],
                    path=path,
                )
                _verify_historical_evaluator_provider_usage(
                    payload, path=path,
                )
                _verify_historical_evaluator_estimated_cost(
                    payload, pricing_models=pricing_models, path=path,
                )
                if _verify_evaluator_report_input_fingerprint(
                    payload, source_cells[(variant, task)],
                    expected_question=frozen_questions[task],
                    expected_evidence_fingerprint=evidence_snapshots[(variant, task)]["input_fingerprint"],
                    expected_prompt_fingerprint=evidence_snapshots[(variant, task)]["prompt_fingerprint"],
                    path=path,
                ):
                    report_input_bindings_checked += 1
    except (zipfile.BadZipFile, KeyError) as exc:
        raise RecoveryConcordanceError(
            "evaluator cache member cannot be read from verified ZIP"
        ) from exc
    return len(cache), report_input_bindings_checked


# The original treatment runner freezes the assigned experimental conditions.
# These are design checks, not observed-outcome filters or reexecution rules.
FROZEN_TREATMENT_ASSIGNMENTS = {
    "D3": ("direct", 3, "none"),
    "D6": ("direct", 6, "none"),
    "P6": ("planner", 6, "none"),
    "P6V": ("planner", 6, "verify"),
}
MAX_TREATMENT_TRACE_JSON_BYTES = 16 * 1024 * 1024
# Report bytes were already scanned under the ZIP preflight's member bound.
# This second read verifies trace-to-report consistency, not external custody.
MAX_TREATMENT_REPORT_BYTES = preflight.MAX_MEMBER_BYTES


def _verify_archived_report_trace_binding(
    source: zipfile.ZipFile, *, prefix: str, cell: dict, trace: dict,
) -> None:
    """Check the recorded report pointer and word count against the actual Markdown.

    Treatment instrumentation counts report_text.split() before writing that
    same string to research_report.md. Merely agreeing with the published CSV
    does not establish that the archived report is that treatment's output.
    """
    run_id = cell["run_id"]
    recorded = trace.get("report_path")
    if type(recorded) is not str or not recorded or recorded != recorded.strip():
        raise RecoveryConcordanceError(
            "historical treatment trace report_path is missing or invalid: " + run_id
        )
    decoded = unquote(recorded)
    if (
        decoded.startswith("/")
        or "\\" in decoded
        or PurePosixPath(decoded).parts not in (
            ("outputs", run_id, "research_report.pdf"),
            ("outputs", run_id, "research_report.md"),
        )
    ):
        raise RecoveryConcordanceError(
            "historical treatment trace report_path does not identify its run: " + run_id
        )
    path = f"{prefix}{run_id}/research_report.md"
    size = cell["report_uncompressed_bytes"]
    if not 0 < size <= MAX_TREATMENT_REPORT_BYTES:
        raise RecoveryConcordanceError(
            "historical Markdown report exceeds semantic size bound: " + path
        )
    with source.open(path, "r") as member:
        raw = member.read(size + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != cell["report_sha256"]:
        raise RecoveryConcordanceError(
            "historical Markdown report bytes disagree with ZIP preflight: " + path
        )
    try:
        word_count = len(raw.decode("utf-8").split())
    except UnicodeDecodeError as exc:
        raise RecoveryConcordanceError(
            "historical Markdown report must be UTF-8: " + path
        ) from exc
    if word_count == 0 or word_count != trace["report_words"]:
        raise RecoveryConcordanceError(
            "historical Markdown report word count disagrees with trace and "
            "published treatment CSV: " + path
        )


def _finite_trace_json_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise RecoveryConcordanceError("nonfinite number in archived treatment trace JSON")
    return value


def _verify_archived_treatment_trace_identities(
    archive: Path, audit: dict, frozen_questions: dict[str, str],
    published_treatments: dict[tuple[str, str], dict[str, str]],
    pricing_models: dict,
) -> int:
    """Validate the *contents* of the 40 preserved treatment trace JSONs.

    The matrix inventory previously proved only path and byte continuity: a
    trace could still claim a different task, condition or completion state.
    This is an offline source-consistency gate, not original-archive custody,
    validation of retrieved content, or evidence that the reports are correct.
    """
    cells = audit["observed_source_content_manifest"]["cells"]
    if len(cells) != 40:
        raise RecoveryConcordanceError("historical trace matrix is incomplete")
    prefix = audit["source_layout_prefix"]
    try:
        with zipfile.ZipFile(archive, "r") as source:
            for cell in cells:
                variant, task, run_id = (
                    cell["treatment"], cell["task_id"], cell["run_id"]
                )
                path = f"{prefix}experiment_traces/{variant}/{run_id}.json"
                size = cell["trace_uncompressed_bytes"]
                if not 0 < size <= MAX_TREATMENT_TRACE_JSON_BYTES:
                    raise RecoveryConcordanceError(
                        "historical treatment trace JSON exceeds semantic size bound: " + path
                    )
                with source.open(path, "r") as member:
                    raw = member.read(size + 1)
                if len(raw) != size or hashlib.sha256(raw).hexdigest() != cell["trace_sha256"]:
                    raise RecoveryConcordanceError(
                        "historical treatment trace bytes disagree with ZIP preflight: " + path
                    )
                try:
                    payload = json.loads(
                        raw.decode("utf-8"),
                        object_pairs_hook=_unique_json_pairs,
                        parse_constant=_reject_nonfinite_json,
                        parse_float=_finite_trace_json_float,
                    )
                except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
                    raise RecoveryConcordanceError(
                        "invalid historical treatment trace JSON: " + path
                    ) from exc
                if (
                    type(payload) is not dict
                    or type(payload.get("schema_version")) is not int
                    or payload["schema_version"] != 2
                    or type(payload.get("experiment")) is not dict
                    or type(payload.get("trace")) is not dict
                ):
                    raise RecoveryConcordanceError(
                        "historical treatment trace schema/metadata is invalid: " + path
                    )
                experiment, trace = payload["experiment"], payload["trace"]
                for label, record in (("experiment", experiment), ("trace", trace)):
                    for field, expected in (
                        ("variant_id", variant),
                        ("task_id", task),
                        ("task_set_id", "main-budget-v1-2026-09-11"),
                    ):
                        if record.get(field) != expected:
                            raise RecoveryConcordanceError(
                                f"historical treatment trace {label}.{field} disagrees with frozen run: {path}"
                            )
                if trace.get("run_id") != run_id:
                    raise RecoveryConcordanceError(
                        "historical treatment trace run_id disagrees with frozen run: " + path
                    )
                if trace.get("question") != frozen_questions[task]:
                    raise RecoveryConcordanceError(
                        "historical treatment trace question disagrees with pinned task: " + path
                    )
                if trace.get("completed") is not True:
                    raise RecoveryConcordanceError(
                        "historical treatment trace is not explicitly completed: " + path
                    )
                if trace.get("usage_accounting_status") != "provider_usage_complete":
                    raise RecoveryConcordanceError(
                        "historical treatment trace provider usage was not complete: " + path
                    )
                mode, budget, verification = FROZEN_TREATMENT_ASSIGNMENTS[variant]
                for field, expected in (
                    ("planning_mode", mode),
                    ("verification_mode", verification),
                    ("source_budget", budget),
                ):
                    value = experiment.get(field)
                    if type(value) != type(expected) or value != expected:
                        raise RecoveryConcordanceError(
                            f"historical treatment trace experiment.{field} contradicts frozen assignment: {path}"
                        )
                if type(trace.get("source_budget")) is not int or trace["source_budget"] != budget:
                    raise RecoveryConcordanceError(
                        "historical treatment trace source_budget contradicts frozen assignment: " + path
                    )
                for field in ("source_count", "successful_source_count", "failed_source_count"):
                    value = trace.get(field)
                    if type(value) is not int or value < 0:
                        raise RecoveryConcordanceError(
                            f"historical treatment trace {field} is not a nonnegative integer: {path}"
                        )
                if (
                    trace["source_count"] > budget
                    or trace["successful_source_count"] + trace["failed_source_count"]
                    != trace["source_count"]
                ):
                    raise RecoveryConcordanceError(
                        "historical treatment trace source ledger violates budget/completion: " + path
                    )
                # Internal count consistency is not enough: an original trace
                # must agree with its canonical published treatment-side row.
                published = published_treatments[(variant, task)]
                for published_field, trace_field in TREATMENT_RESOURCE_FIELDS.items():
                    try:
                        expected = int(published[published_field])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise RecoveryConcordanceError(
                            "invalid published treatment resource field: " + published_field
                        ) from exc
                    observed = trace.get(trace_field)
                    if type(observed) is not int or observed != expected:
                        raise RecoveryConcordanceError(
                            f"historical treatment trace {trace_field} differs "
                            f"from frozen treatment CSV: {path}"
                        )
                # Provenance of retrieval scheduling matters for the study's
                # retrieval-vs-planning contrast: published aggregate counts
                # alone do not enforce which queries scheduled which URLs.
                # Reuse the original-run contract already checked by the
                # extracted-archive readiness diagnostic; do not trust ZIP
                # filename/byte concordance as semantic provenance.
                try:
                    readiness._validate_recovered_source_ledgers(
                        trace, variant=variant,
                    )
                    readiness._validate_recovered_search_provenance(trace)
                    readiness._validate_recovered_query_budget_allocation(
                        trace, variant=variant,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise RecoveryConcordanceError(
                        "historical treatment source-query provenance violates "
                        f"original scheduling contract: {path}: {exc}"
                    ) from exc
                # Published aggregate tokens/model calls alone cannot establish
                # that each source trace preserves a complete per-model provider
                # ledger. Check the original runner's provider-usage contract
                # without recomputing, rerunning, or selecting any outcomes.
                try:
                    readiness._validate_recovered_provider_usage(trace)
                except (KeyError, TypeError, ValueError) as exc:
                    raise RecoveryConcordanceError(
                        "historical treatment provider usage ledger violates "
                        f"original run accounting: {path}: {exc}"
                    ) from exc
                # Token sums alone cannot anchor estimated treatment costs:
                # use the frozen original-run pricing method and latency.
                try:
                    readiness._validate_recovered_efficiency_measurements(
                        trace, published, pricing_models=pricing_models,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise RecoveryConcordanceError(
                        "historical treatment latency/cost disagrees with "
                        f"frozen treatment CSV or original pricing: {path}: {exc}"
                    ) from exc
                _verify_archived_report_trace_binding(
                    source, prefix=prefix, cell=cell, trace=trace,
                )
    except (zipfile.BadZipFile, KeyError) as exc:
        raise RecoveryConcordanceError(
            "historical treatment trace member cannot be reread from verified ZIP"
        ) from exc
    return len(cells)


def compare_recovered_treatment_sources(
    original_archive: Path,
    recovery_archive: Path,
    *,
    repo_root: Path = matrix.REPO_ROOT,
    original_expected_archive_sha256: str | None = None,
    recovery_expected_archive_sha256: str | None = None,
) -> dict:
    """Check distinct role-pinned ZIPs have identical frozen source bytes.

    Independently retained archive pins are optional caller claims, not inferred
    from the recovered archives or from GitHub's own job logs.
    """
    original_archive = Path(original_archive)
    recovery_archive = Path(recovery_archive)
    _verify_historical_evaluator_prompt_canary()
    if original_archive.samefile(recovery_archive):
        raise RecoveryConcordanceError(
            "original and recovery inputs must be distinct archive files"
        )
    # Snapshot all three governing sources before either expensive archive audit.
    # Individual per-ZIP custody checks cannot detect a source replaced in the
    # gap between two otherwise successful independent audits.
    original_start = _archive_source_snapshot(original_archive)
    recovery_start = _archive_source_snapshot(recovery_archive)
    evaluator_path = Path(repo_root) / matrix.lineage.SUPPORT_REL
    evaluator_start = matrix._capture_evaluator(evaluator_path)
    treatment_start = _frozen_treatment_snapshot(repo_root)
    frozen_pricing_start = _frozen_pricing_snapshot(repo_root)
    frozen_questions_start = _frozen_questions_snapshot(repo_root)
    frozen_questions = frozen_questions_start[0]
    published_rows = matrix.lineage._matrix(
        matrix.lineage._read_study_csv(evaluator_start[0], path=evaluator_path),
        label="frozen published evaluator",
        expected_cells=matrix.EXPECTED_CELLS, run_identity=True,
    )
    original = matrix.audit_recovered_treatment_matrix(
        original_archive,
        artifact_role="original_treatment",
        repo_root=repo_root,
        expected_archive_sha256=original_expected_archive_sha256,
    )
    recovered = matrix.audit_recovered_treatment_matrix(
        recovery_archive,
        artifact_role="evaluator_recovery",
        repo_root=repo_root,
        expected_archive_sha256=recovery_expected_archive_sha256,
    )
    original_manifest = original["observed_source_content_manifest"]
    recovered_manifest = recovered["observed_source_content_manifest"]
    before = original_manifest["cells"]
    after = recovered_manifest["cells"]
    differences = []
    for left, right in zip(before, after):
        identity = (left["treatment"], left["task_id"], left["run_id"])
        if identity != (right["treatment"], right["task_id"], right["run_id"]):
            raise RecoveryConcordanceError("published treatment identities differ")
        for source in ("trace", "report"):
            fields = (f"{source}_sha256", f"{source}_uncompressed_bytes")
            if any(left[field] != right[field] for field in fields):
                differences.append((identity, source))
    # Recheck both ZIPs and the frozen evaluator after *both* audits, including
    # replacement by a new inode containing the same bytes. Validate the
    # preflight digests against the initial snapshots as well.
    original_end = _archive_source_snapshot(original_archive)
    recovery_end = _archive_source_snapshot(recovery_archive)
    evaluator_end = matrix._capture_evaluator(evaluator_path)
    if (
        original_start != original_end
        or recovery_start != recovery_end
        or evaluator_start != evaluator_end
        or original["zip_sha256_observed_now"] != original_start[1]
        or recovered["zip_sha256_observed_now"] != recovery_start[1]
        or original_archive.samefile(recovery_archive)
        or _frozen_questions_snapshot(repo_root) != frozen_questions_start
        or _frozen_treatment_snapshot(repo_root) != treatment_start
        or _frozen_pricing_snapshot(repo_root) != frozen_pricing_start
    ):
        raise RecoveryConcordanceError(
            "original, recovery, or evaluator source changed during comparison"
        )
    if differences:
        sample = ", ".join(
            f"{treatment}/{task}/{run_id}:{source}"
            for (treatment, task, run_id), source in differences[:5]
        )
        raise RecoveryConcordanceError(
            f"original and evaluator-recovery source bytes differ in "
            f"{len(differences)} treatment source(s): {sample}"
        )
    if (
        len(before) != 40
        or len(after) != 40
        or original_manifest != recovered_manifest
        or original["observed_source_content_manifest_sha256"]
        != recovered["observed_source_content_manifest_sha256"]
    ):
        raise RecoveryConcordanceError("40-cell source manifest concordance failed")
    # The common evaluator consumed saved query snippets, not just reports.
    # Bind all 40 original/recovery raw evidence members and the reconstructed
    # input, then check schema-v2 evaluator-input fingerprints independently.
    original_evidence = _snapshot_archived_evaluator_evidence(
        original_archive, original, treatment_start[0], published_rows,
        frozen_questions,
    )
    recovered_evidence = _snapshot_archived_evaluator_evidence(
        recovery_archive, recovered, treatment_start[0], published_rows,
        frozen_questions,
    )
    if original_evidence != recovered_evidence:
        mismatches = [
            "/".join(identity) for identity in sorted(original_evidence)
            if original_evidence[identity] != recovered_evidence[identity]
        ]
        raise RecoveryConcordanceError(
            "original and evaluator-recovery saved evidence differs for "
            + ", ".join(mismatches[:5])
        )
    preserved_evidence_members = sum(
        len(item["member_fingerprints"]) for item in original_evidence.values()
    )
    # Evaluator-only recovery must add exactly the three declared missing
    # cache cells, without rewriting any of the 37 preserved JSON outputs.
    # This cannot be inferred from treatment-source hashes alone.
    preserved_count, new_count = _verify_evaluator_cache_continuity(
        original, recovered,
    )
    original_identity_count, original_report_binding_count = (
        _verify_evaluator_cache_json_identities(
            original_archive, original, published_rows, frozen_questions,
            original_evidence, frozen_pricing_start[0],
        )
    )
    recovered_identity_count, recovered_report_binding_count = (
        _verify_evaluator_cache_json_identities(
            recovery_archive, recovered, published_rows, frozen_questions,
            recovered_evidence, frozen_pricing_start[0],
        )
    )
    original_traces_checked = _verify_archived_treatment_trace_identities(
        original_archive, original, frozen_questions, treatment_start[0],
        frozen_pricing_start[0],
    )
    recovered_traces_checked = _verify_archived_treatment_trace_identities(
        recovery_archive, recovered, frozen_questions, treatment_start[0],
        frozen_pricing_start[0],
    )
    # The second ZIP read must be inside the same source-generation custody
    # window. A change during JSON inspection cannot authorize this receipt.
    if (
        _archive_source_snapshot(original_archive) != original_start
        or _archive_source_snapshot(recovery_archive) != recovery_start
        or matrix._capture_evaluator(evaluator_path) != evaluator_start
        or _frozen_questions_snapshot(repo_root) != frozen_questions_start
        or _frozen_treatment_snapshot(repo_root) != treatment_start
        or _frozen_pricing_snapshot(repo_root) != frozen_pricing_start
    ):
        raise RecoveryConcordanceError(
            "original, recovery, or evaluator source changed during comparison"
        )
    return {
        "schema_version": 1,
        "status": "original_and_evaluator_recovery_40_source_pairs_match_not_authenticated",
        "source_cells_compared": 40,
        "original_completed_treatment_trace_identities_checked": original_traces_checked,
        "recovery_completed_treatment_trace_identities_checked": recovered_traces_checked,
        "original_treatment_published_resource_ledgers_matched": original_traces_checked,
        "recovery_treatment_published_resource_ledgers_matched": recovered_traces_checked,
        "original_treatment_query_and_url_scheduling_checked": original_traces_checked,
        "recovery_treatment_query_and_url_scheduling_checked": recovered_traces_checked,
        "original_treatment_provider_usage_ledgers_checked": original_traces_checked,
        "recovery_treatment_provider_usage_ledgers_checked": recovered_traces_checked,
        "original_treatment_published_latency_and_cost_matched": original_traces_checked,
        "recovery_treatment_published_latency_and_cost_matched": recovered_traces_checked,
        "original_run_pricing_sha256": readiness.ORIGINAL_PRICING_SHA256,
        "original_trace_report_path_and_word_counts_matched": original_traces_checked,
        "recovery_trace_report_path_and_word_counts_matched": recovered_traces_checked,
        "published_treatment_csv_sha256": PUBLISHED_TREATMENT_CSV_SHA256,
        "trace_sources_unchanged": 40,
        "evaluator_evidence_source_cells_compared": len(original_evidence),
        "evaluator_evidence_source_members_byte_identical": preserved_evidence_members,
        "report_sources_unchanged": 40,
        "preserved_evaluator_cache_members_byte_identical": preserved_count,
        "recovery_only_evaluator_cache_members_present": new_count,
        "original_evaluator_cache_json_identities_checked": original_identity_count,
        "recovery_evaluator_cache_json_identities_checked": recovered_identity_count,
        "original_evaluator_cache_published_measurements_matched": original_identity_count,
        "recovery_evaluator_cache_published_measurements_matched": recovered_identity_count,
        "original_evaluator_normalized_examples_checked": original_identity_count,
        "recovery_evaluator_normalized_examples_checked": recovered_identity_count,
        "original_evaluator_frozen_configuration_matched": original_identity_count,
        "recovery_evaluator_frozen_configuration_matched": recovered_identity_count,
        "original_evaluator_provider_usage_ledgers_checked": original_identity_count,
        "recovery_evaluator_provider_usage_ledgers_checked": recovered_identity_count,
        "original_evaluator_frozen_costs_recomputed": original_identity_count,
        "recovery_evaluator_frozen_costs_recomputed": recovered_identity_count,
        "original_schema_v2_evaluator_report_input_fingerprints_matched": original_report_binding_count,
        "recovery_schema_v2_evaluator_report_input_fingerprints_matched": recovered_report_binding_count,
        "original_schema_v2_evaluator_evidence_input_fingerprints_matched": original_report_binding_count,
        "original_schema_v2_evaluator_question_input_fingerprints_matched": original_report_binding_count,
        "original_schema_v2_evaluator_prompt_input_fingerprints_matched": original_report_binding_count,
        "recovery_schema_v2_evaluator_evidence_input_fingerprints_matched": recovered_report_binding_count,
        "recovery_schema_v2_evaluator_question_input_fingerprints_matched": recovered_report_binding_count,
        "recovery_schema_v2_evaluator_prompt_input_fingerprints_matched": recovered_report_binding_count,
        "historical_evaluator_prompt_canary_sha256": HISTORICAL_EVALUATOR_PROMPT_CANARY_SHA256,
        "original_treatment_task_manifest_sha256": frozen_tasks.ORIGINAL_TASK_MANIFEST_SHA256,
        "schema_v1_evaluator_report_input_binding_unavailable": True,
        "schema_v1_evaluator_evidence_input_binding_unavailable": True,
        "schema_v1_evaluator_question_input_binding_unavailable": True,
        "schema_v1_evaluator_prompt_input_binding_unavailable": True,
        "evaluator_cache_json_duplicate_keys_rejected": True,
        "recovery_only_evaluator_cells": [
            {"treatment": variant, "task_id": task}
            for variant, task in sorted(RECOVERY_ONLY_EVALUATOR_CELLS)
        ],
        "evaluator_cache_payload_semantics_verified": False,
        "source_content_manifest_sha256": original[
            "observed_source_content_manifest_sha256"
        ],
        "published_evaluator_csv_sha256": original[
            "published_evaluator_csv_sha256"
        ],
        "original_zip_sha256_observed_now": original["zip_sha256_observed_now"],
        "recovery_zip_sha256_observed_now": recovered["zip_sha256_observed_now"],
        "original_github_job_log_correspondence": original[
            "github_job_log_zip_correspondence"
        ],
        "recovery_github_job_log_correspondence": recovered[
            "github_job_log_zip_correspondence"
        ],
        "caller_claimed_independent_original_zip_pin_matched": original[
            "caller_claimed_independent_zip_pin_matched"
        ],
        "caller_claimed_independent_recovery_zip_pin_matched": recovered[
            "caller_claimed_independent_zip_pin_matched"
        ],
        "independent_archive_custody_verified": False,
        "historical_evidence_authenticated": False,
        "human_evaluation_ready": False,
        "treatments_rerun": False,
        "evaluator_rerun": False,
        "human_ratings_generated": False,
        "interpretation": (
            "Both candidate ZIPs match their separate historical GitHub job-log "
            "fingerprints and have exactly equal decompressed trace/report source "
            "bytes for 40 frozen run identities; 37 pre-existing evaluator "
            "cache JSON byte streams also match, and only the three historically "
            "missing evaluator cache members appear in recovery. This checks "
            "cache membership, byte continuity, JSON/schema/run identity, plus "
            "original and recovery treatment trace completion, frozen task, "
            "treatment assignment, source-budget, query/URL scheduling, per-model provider usage "
            "aggregation, original-rate estimated cost and latency correspondence, "
            "and frozen-rate evaluator cost recomputation from the per-model "
            "prompt/completion split; and byte-identical saved retrieval snippets across original/recovery "
            "archives, with schema-v2 evaluator evidence-input correspondence; "
            "and report-pointer/actual-"
            "Markdown-word-count consistency; and "
            "exact published score/count/token/cost correspondence for 37 original "
            "plus 40 recovered caches. Schema-v2 report and original treatment-task "
            "question fingerprints are also checked against their distinct "
            "ZIP-member and Git-revision anchors; schema-v2 prompt hashes are "
            "recomputed using the original 12-claim rubric and the archived "
            "question, report and evidence inputs. This checks consistency, not " 
            "independent score correctness, evidence inputs, or prompt validity. "
            "Same-provider "
            "log anchors and "
            "present-day comparisons do not prove independently retained custody, "
            "historical report authenticity, or human-evaluation readiness."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-zip", required=True, type=Path)
    parser.add_argument("--recovery-zip", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=matrix.REPO_ROOT)
    parser.add_argument(
        "--original-expected-archive-sha256",
        help="optional independently retained original ZIP-byte fingerprint",
    )
    parser.add_argument(
        "--recovery-expected-archive-sha256",
        help="optional independently retained recovery ZIP-byte fingerprint",
    )
    args = parser.parse_args()
    try:
        result = compare_recovered_treatment_sources(
            args.original_zip,
            args.recovery_zip,
            repo_root=args.repo_root,
            original_expected_archive_sha256=args.original_expected_archive_sha256,
            recovery_expected_archive_sha256=args.recovery_expected_archive_sha256,
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"VERA RECOVERED SOURCE CONCORDANCE: FAIL: {exc}\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
