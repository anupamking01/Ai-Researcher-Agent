"""Fail-closed candidate schema and lossless local backend-pool provenance.

The backend pool is the metasearch adapter's selected *request pool*, not
proof of which external search engine produced any individual result.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from ipaddress import ip_address
from urllib.parse import urlsplit


# Browsers recognize shortened, numeric and hexadecimal IPv4 authorities that
# ipaddress deliberately does not parse as ordinary dotted-quad literals.
# Prospective bounds are far above the frozen metasearch adapter's four
# candidates per query; they limit untrusted JSON resource consumption without
# trimming or replacing any search evidence. Over-limit batches fail intact.
MAX_SEARCH_RESULTS_JSON_BYTES = 1024 * 1024
MAX_SEARCH_CANDIDATES = 128
MAX_SEARCH_JSON_NUMBER_TOKEN_CHARS = 128
MAX_SEARCH_JSON_NESTING_DEPTH = 128


_AMBIGUOUS_NUMERIC_HOST = re.compile(
    r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+)){0,3}\Z"
)


def _is_nonblank_scalar_text(value: object) -> bool:
    """Text that can be persisted unchanged in the UTF-8 trace envelope."""
    return (
        type(value) is str
        and bool(value.strip())
        and not any(0xD800 <= ord(char) <= 0xDFFF for char in value)
    )


def _require_external_web_url(url: str, *, index: int) -> None:
    """Reject non-web and explicitly local URLs before source scheduling.

    This is a syntactic candidate gate, NOT a DNS, redirect or network-egress
    policy. Preserve accepted URL bytes unchanged for reproducible traces.
    """
    message = f"Search candidate {index} must have an external HTTP(S) href"
    # urlsplit silently strips some ASCII control characters; reject first.
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url):
        raise ValueError(message)
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port  # Forces validation of malformed/out-of-range ports.
        has_userinfo = parts.username is not None or parts.password is not None
    except ValueError as exc:
        raise ValueError(message) from exc
    if parts.scheme not in ("http", "https") or not host or has_userinfo or port == 0:
        raise ValueError(message)
    try:
        # IDNA maps Unicode DNS separators (e.g. U+3002) to ASCII dots.
        # Strip the root dot again *after* normalization, or local and
        # numeric hosts can evade the checks below via a Unicode root dot.
        ascii_host = host.rstrip(".").encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise ValueError(message) from exc
    if (
        not ascii_host
        or any(char in ascii_host for char in ("%", "/", "\\", "@"))
        or ascii_host == "localhost"
        or ascii_host.endswith((".localhost", ".local", ".internal", ".home.arpa"))
    ):
        raise ValueError(message)
    try:
        address = ip_address(ascii_host)
    except ValueError:
        if _AMBIGUOUS_NUMERIC_HOST.fullmatch(ascii_host):
            raise ValueError(message)
    else:
        if not address.is_global or address.is_multicast or address.is_reserved:
            raise ValueError(message)


def _unique_object_members(pairs: list[tuple[str, object]]) -> dict:
    members = {}
    for name, value in pairs:
        if name in members:
            raise ValueError(f"Ambiguous search result JSON key {name!r}")
        members[name] = value
    return members


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"Non-finite search result JSON constant {token!r}")


def _bounded_json_int(token: str) -> int:
    if len(token) > MAX_SEARCH_JSON_NUMBER_TOKEN_CHARS:
        raise ValueError("Search results contain an oversized JSON number")
    return int(token)


def _bounded_json_float(token: str) -> float:
    if len(token) > MAX_SEARCH_JSON_NUMBER_TOKEN_CHARS:
        raise ValueError("Search results contain an oversized JSON number")
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("Search results contain a nonfinite JSON number")
    return value


def _require_bounded_json_nesting(raw: str) -> None:
    """Enforce an input-depth ceiling independent of the Python stack limit.

    Count JSON containers, including the root, only outside quoted strings.
    This is a linear lexical guard; json.loads still validates JSON syntax.
    """
    depth = 0
    in_string = False
    escaped = False
    for char in raw:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_SEARCH_JSON_NESTING_DEPTH:
                raise ValueError(
                    "Search results must be valid bounded JSON text: nesting depth limit"
                )
        elif char in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("Search results must be valid bounded JSON text")


def parse_search_candidates(
    raw: str, *, expected_limit: int | None = None
) -> list[dict[str, str | None]]:
    """Extract ordered candidate URLs and *reported* pools without coercion.

    Missing pool labels remain ``None`` for legacy search stubs. Invalid
    response shapes fail the prospective run rather than looking like an
    empty/unsuccessful search. No URLs are sorted, repaired or filtered.
    When provided, expected_limit pins the size to the actual search request,
    not merely the broad parser safety ceiling.
    """
    if expected_limit is not None and (
        type(expected_limit) is not int
        or not 1 <= expected_limit <= MAX_SEARCH_CANDIDATES
    ):
        raise ValueError("Requested candidate limit must be a positive bounded integer")
    if type(raw) is not str:
        raise ValueError("Search results must be JSON text")
    # Bound UTF-8 bytes, not just code points (a short-looking Unicode payload
    # can still be much larger on the wire). Check length first to avoid
    # encoding an obviously excessive string.
    if len(raw) > MAX_SEARCH_RESULTS_JSON_BYTES:
        raise ValueError("Search results exceed the JSON byte limit")
    try:
        byte_count = len(raw.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("Search results must be valid UTF-8 JSON text") from exc
    if byte_count > MAX_SEARCH_RESULTS_JSON_BYTES:
        raise ValueError("Search results exceed the JSON byte limit")
    _require_bounded_json_nesting(raw)
    try:
        results = json.loads(
            raw,
            object_pairs_hook=_unique_object_members,
            parse_constant=_reject_json_constant,
            parse_int=_bounded_json_int,
            parse_float=_bounded_json_float,
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Search results must be valid bounded JSON text") from exc
    if type(results) is not list:
        raise ValueError("Search results must be a JSON array")
    if len(results) > MAX_SEARCH_CANDIDATES:
        raise ValueError("Search results exceed the candidate count limit")
    if expected_limit is not None and len(results) > expected_limit:
        raise ValueError("Search results exceed the requested candidate limit")

    candidates = []
    for index, item in enumerate(results, start=1):
        if type(item) is not dict:
            raise ValueError(f"Search candidate {index} must be a JSON object")
        url = item.get("href")
        if not _is_nonblank_scalar_text(url):
            raise ValueError(f"Search candidate {index} must contain a text href")
        _require_external_web_url(url, index=index)
        pool = item.get("_search_backend_pool")
        if pool is not None and not _is_nonblank_scalar_text(pool):
            raise ValueError(
                f"Search candidate {index} has an invalid backend pool label"
            )
        candidates.append({"url": url, "backend_pool": pool})
    return candidates


def selected_search_sources(
    candidates: list[dict[str, str | None]], scheduled_urls: list[str]
) -> list[dict[str, str | None]]:
    """Bind actual scheduled URLs to the first matching raw candidate record."""
    first_occurrence = {}
    for entry in candidates:
        first_occurrence.setdefault(entry["url"], entry)

    selected = []
    seen = set()
    for url in scheduled_urls:
        if url in seen or url not in first_occurrence:
            raise ValueError("Scheduled source is duplicate or absent from candidates")
        seen.add(url)
        selected.append(dict(first_occurrence[url]))
    return selected


# Explicitly prospective; historical traces without the marker are not certified.
SEARCH_TRACE_PROVENANCE_SCHEMA = 6
REPORT_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA = 6
VERIFIER_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA = 5
# Historical prospective versions retain their original, narrower contracts.
FACTOR_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA = 4
TREATMENT_PLAN_SEARCH_TRACE_PROVENANCE_SCHEMA = 3
REQUEST_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA = 2
LEGACY_SEARCH_TRACE_PROVENANCE_SCHEMA = 1

# Frozen main-study assignments. Checked independently of the claimed
# treatment trace and persisted ExperimentConfig envelope, so a valid-looking
# retrieval ledger cannot be attributed to a different experimental arm.
_FROZEN_TREATMENT_FACTORS = {
    "D3": ("direct", 3, "none"),
    "D6": ("direct", 6, "none"),
    "P6": ("planner", 6, "none"),
    "P6V": ("planner", 6, "verify"),
}


def validate_search_trace_provenance(
    trace: dict, *, experiment: dict | None = None
) -> None:
    """Conserve ordered retrieval ledgers and prospective treatment identity.

    Schema 4+ additionally requires the persisted experiment envelope.
    Schema 5+ binds verifier treatments to retained verifier receipts.
    Schema 6 binds completed report content to exact retained Markdown bytes.
    Earlier schemas are not retroactively certified.
    """
    if type(trace) is not dict or (
        type(trace.get("search_provenance_schema")) is not int
        or trace["search_provenance_schema"] not in (
            LEGACY_SEARCH_TRACE_PROVENANCE_SCHEMA,
            REQUEST_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA,
            TREATMENT_PLAN_SEARCH_TRACE_PROVENANCE_SCHEMA,
            FACTOR_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA,
            VERIFIER_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA,
            SEARCH_TRACE_PROVENANCE_SCHEMA,
        )
    ):
        raise ValueError("unsupported search provenance schema")
    queries = trace.get("search_queries")
    records = trace.get("search_records")
    scheduled = trace.get("scheduled_urls")
    if any(type(x) is not list for x in (queries, records, scheduled)):
        raise ValueError("search provenance ledgers must be arrays")
    if any(type(q) is not str or not q.strip() for q in queries):
        raise ValueError("invalid planned query")
    if any(type(url) is not str or not url.strip() for url in scheduled):
        raise ValueError("invalid run scheduled URL")
    if (
        type(trace.get("query_count")) is not int
        or len(queries) != trace["query_count"]
        or type(trace.get("search_call_count")) is not int
        or len(records) != trace["search_call_count"]
        or type(trace.get("source_count")) is not int
        or len(scheduled) != trace["source_count"]
    ):
        raise ValueError("search/browse count ledger mismatch")

    # Schema 3 binds the completed query plan to the experimental treatment.
    # Direct retrieval searches the exact original question. The planner
    # produces four ordered strings; legitimate duplicates remain distinct.
    # Preserve incomplete runs even when planning could not finish, and do
    # not retroactively strengthen earlier schemas.
    if (
        trace["search_provenance_schema"] >= TREATMENT_PLAN_SEARCH_TRACE_PROVENANCE_SCHEMA
        and trace.get("completed") is True
    ):
        mode = trace.get("planning_mode")
        question = trace.get("question")
        if type(question) is not str or not question.strip():
            raise ValueError("completed search plan missing original question")
        if mode == "direct":
            if queries != [question]:
                raise ValueError("direct search plan differs from task question")
        elif mode == "planner":
            if len(queries) != 4:
                raise ValueError("planner search plan must contain exactly four queries")
        else:
            raise ValueError("completed search plan has invalid planning mode")

    # Schema 4 ties the persisted experimental arm to BOTH the trace factors
    # and the independent ExperimentConfig envelope. A correctly accounted
    # direct search must not be misreported as a verification treatment, and
    # the envelope cannot silently disagree with the serialized trace.
    if (
        trace["search_provenance_schema"] >= FACTOR_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA
        and trace.get("completed") is True
    ):
        variant = trace.get("variant_id")
        factors = (
            _FROZEN_TREATMENT_FACTORS.get(variant)
            if type(variant) is str else None
        )
        if factors is None or type(experiment) is not dict:
            raise ValueError("completed treatment factor identity or envelope missing")
        planning_mode, budget, verification_mode = factors
        for source in (trace, experiment):
            if (
                source.get("variant_id") != variant
                or source.get("planning_mode") != planning_mode
                or type(source.get("source_budget")) is not int
                or source["source_budget"] != budget
                or source.get("verification_mode") != verification_mode
            ):
                raise ValueError("completed treatment factors disagree with frozen arm")
        # The per-query request arithmetic alone cannot detect a multiplier
        # and all its derived limits being changed together. Bind the control
        # to the independently serialized ExperimentConfig as well.
        multiplier = experiment.get("search_candidate_multiplier")
        if (
            type(multiplier) is not int or multiplier <= 0
            or type(trace.get("search_candidate_multiplier")) is not int
            or trace["search_candidate_multiplier"] != multiplier
        ):
            raise ValueError("completed search candidate multiplier disagrees with experiment")

    # Schema 5 requires a retained verifier artifact for successful P6V
    # treatments. A verification flag alone cannot establish that the
    # verifier produced any output. Failed/incomplete traces are preserved.
    if (
        trace["search_provenance_schema"] >= VERIFIER_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA
        and trace.get("completed") is True
    ):
        status = trace.get("verification_status")
        digest = trace.get("verification_artifact_sha256")
        count_fields = (
            "citation_count", "supported_claim_count",
            "partially_supported_claim_count", "unsupported_claim_count",
            "contradicted_claim_count",
        )
        if any(
            type(trace.get(name)) is not int or trace[name] < 0
            for name in count_fields
        ):
            raise ValueError("completed verification counts must be nonnegative integers")
        checked, supported, partial, unsupported, contradicted = (
            trace[name] for name in count_fields
        )
        if trace["verification_mode"] == "none":
            if status != "not_requested" or digest is not None or any(
                (checked, supported, partial, unsupported, contradicted)
            ):
                raise ValueError("non-verifier arm claims verification evidence")
        else:
            if (
                status not in ("ok", "parse_error")
                or type(digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or checked > 20
                or checked != supported + partial + unsupported + contradicted
                or (status == "parse_error" and checked != 0)
            ):
                raise ValueError("verifier arm missing or contradictory verification receipt")

    # Schema 6 introduces a separate content-addressed report boundary.
    # A matching word count cannot detect same-length Markdown substitution;
    # the runner subsequently checks the exact retained report bytes.
    if (
        trace["search_provenance_schema"] >= REPORT_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA
        and trace.get("completed") is True
    ):
        digest = trace.get("report_artifact_sha256")
        if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("completed report artifact SHA-256 missing or malformed")

    # Schema 2+ binds the requested candidate count to the allocated query
    # slot and remaining browse budget. Schema 1 cannot establish this.
    request_bound = (
        trace["search_provenance_schema"]
        >= REQUEST_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA
    )
    if request_bound:
        budget = trace.get("source_budget")
        multiplier = trace.get("search_candidate_multiplier")
        if type(budget) is not int or budget <= 0:
            raise ValueError("invalid provenance source budget")
        if type(multiplier) is not int or multiplier <= 0:
            raise ValueError("invalid provenance search candidate multiplier")
        per_query_budgets = [
            budget // len(queries) + (index < budget % len(queries))
            for index in range(len(queries))
        ]
        # In a completed prospective run, every query assigned a positive
        # browse slot must have an attempted search record, including outages.
        # The production agent cannot exhaust a later funded slot early:
        # each earlier query is individually capped at its own allocation.
        if trace.get("completed") is True and (
            not any(per_query_budgets)
            or len(records) != sum(slot > 0 for slot in per_query_budgets)
        ):
            raise ValueError("completed search trace omits funded planned queries")

    query_cursor = 0
    accumulated = []
    for index, record in enumerate(records, start=1):
        if type(record) is not dict:
            raise ValueError(f"search record {index} must be an object")
        query = record.get("query")
        if type(query) is not str or not query.strip():
            raise ValueError(f"search record {index} has invalid query")
        while query_cursor < len(queries) and queries[query_cursor] != query:
            query_cursor += 1
        if query_cursor == len(queries):
            raise ValueError(f"search record {index} violates query order")
        query_index = query_cursor
        query_cursor += 1
        cu, su = record.get("candidate_urls"), record.get("scheduled_urls")
        cs, ss = record.get("candidate_sources"), record.get("scheduled_sources")
        if any(type(x) is not list for x in (cu, su, cs, ss)):
            raise ValueError(f"search record {index} missing source arrays")
        if request_bound:
            # The agent caps overfetch at 20, based on the allocated query slot
            # and the unspent attempt budget. A search for an exhausted/zero
            # slot or an overproduced response must not be accepted as evidence.
            allowed = min(per_query_budgets[query_index], budget - len(accumulated))
            if allowed <= 0:
                raise ValueError(f"search record {index} has no query browse budget")
            requested = min(allowed * multiplier, 20)
            if (
                type(record.get("requested_candidate_limit")) is not int
                or record["requested_candidate_limit"] != requested
                or len(cs) > requested
            ):
                raise ValueError(f"search record {index} violates requested candidate limit")
            # Candidate requests may overfetch, but actual browsing cannot
            # consume another planned query's separately allocated slot.
            if len(su) > allowed:
                raise ValueError(f"search record {index} exceeds allocated query browse budget")
        for entry in cs + ss:
            if (
                type(entry) is not dict
                or not _is_nonblank_scalar_text(entry.get("url"))
                or "backend_pool" not in entry
                or (entry["backend_pool"] is not None
                    and not _is_nonblank_scalar_text(entry["backend_pool"]))
            ):
                raise ValueError(f"search record {index} invalid source metadata")
            _require_external_web_url(entry["url"], index=index)
        if [entry["url"] for entry in cs] != cu:
            raise ValueError(f"search record {index} candidate URL mismatch")
        # A completed request-bound ledger must reproduce the producer's
        # first-unseen selection, not merely contain an eligible subset.
        # Prior scheduled attempts count as visited even if browsing failed.
        # Leave schema 1 and incomplete traces under their narrower contract.
        if request_bound and trace.get("completed") is True:
            prior = set(accumulated)
            expected_urls = [
                url for url in dict.fromkeys(cu) if url not in prior
            ][:allowed]
            if su != expected_urls:
                raise ValueError(
                    f"search record {index} violates deterministic candidate selection"
                )
        try:
            expected = selected_search_sources(cs, su)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"search record {index} unattributable scheduling") from exc
        if expected != ss:
            raise ValueError(f"search record {index} scheduled source mismatch")
        if "search_error" in record and (
            type(record["search_error"]) is not str
            or not record["search_error"].strip()
            or any((cu, su, cs, ss))
        ):
            raise ValueError(f"search record {index} contradictory error status")
        accumulated.extend(su)
    if accumulated != scheduled or len(set(accumulated)) != len(accumulated):
        raise ValueError("per-query and run-level scheduled URLs disagree")

    # A completed report must also conserve which *scheduled* browse attempts
    # succeeded and failed. Sets alone lose the recorded encounter order:
    # an altered outcome list could appear valid despite reordered source use.
    successful = trace.get("successful_urls")
    failed = trace.get("failed_urls")
    if type(successful) is not list or type(failed) is not list:
        raise ValueError("browse outcome URL ledgers must be arrays")
    for urls, count_name in (
        (successful, "successful_source_count"),
        (failed, "failed_source_count"),
    ):
        count = trace.get(count_name)
        if type(count) is not int or count < 0 or len(urls) != count:
            raise ValueError("browse outcome count ledger mismatch")
    outcome_urls = successful + failed
    if any(type(url) is not str for url in outcome_urls):
        raise ValueError("browse outcomes must reference scheduled URLs")
    successful_set, failed_set = set(successful), set(failed)
    scheduled_set = set(scheduled)
    if (
        len(successful_set) != len(successful)
        or len(failed_set) != len(failed)
        or successful_set & failed_set
        or not (successful_set | failed_set) <= scheduled_set
        or [url for url in scheduled if url in successful_set] != successful
        or [url for url in scheduled if url in failed_set] != failed
    ):
        raise ValueError("browse outcomes contradict scheduled source order")
    if type(trace.get("completed")) is not bool:
        raise ValueError("browse completion status must be a boolean")
    if trace["completed"] and (successful_set | failed_set) != scheduled_set:
        raise ValueError("completed browse outcomes leave unclassified sources")
    actual_rate = trace.get("source_success_rate")
    expected_rate = len(successful) / len(scheduled) if scheduled else 0.0
    if (
        type(actual_rate) not in (int, float)
        or not math.isfinite(actual_rate)
        or actual_rate != expected_rate
    ):
        raise ValueError("browse success rate disagrees with source outcomes")


# This verifier is deliberately separate from treatment-label and retrieval
# validation. The noncanonical runner reads *retained file bytes* through its
# bounded, no-follow evidence reader before using this function.
MAX_VERIFICATION_ARTIFACT_BYTES = 1024 * 1024


def validate_verifier_artifact(trace: dict, raw: bytes) -> None:
    """Cross-check retained verifier bytes against a completed schema-5 trace.

    This attests internal file/trace continuity, not external provider
    execution or the correctness of the verifier's judgments.
    """
    if (
        type(trace) is not dict
        or trace.get("search_provenance_schema") not in (
            VERIFIER_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA,
            SEARCH_TRACE_PROVENANCE_SCHEMA,
        )
        or trace.get("completed") is not True
        or trace.get("verification_mode") != "verify"
    ):
        raise ValueError("verifier artifact requires a completed schema-5 verifier run")
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_VERIFICATION_ARTIFACT_BYTES:
        raise ValueError("verifier artifact must be bounded nonempty bytes")
    if hashlib.sha256(raw).hexdigest() != trace.get("verification_artifact_sha256"):
        raise ValueError("verifier artifact SHA-256 differs from trace")
    try:
        receipt = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object_members,
            parse_constant=_reject_json_constant,
            parse_int=_bounded_json_int,
            parse_float=_bounded_json_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("verifier artifact must contain strict UTF-8 JSON") from exc
    if type(receipt) is not dict or receipt.get("status") != trace.get("verification_status"):
        raise ValueError("verifier artifact status differs from trace")
    fields = (
        ("claims_checked", "citation_count"),
        ("supported", "supported_claim_count"),
        ("partially_supported", "partially_supported_claim_count"),
        ("unsupported", "unsupported_claim_count"),
        ("contradicted", "contradicted_claim_count"),
    )
    if any(
        type(receipt.get(source)) is not int
        or receipt[source] != trace.get(target)
        for source, target in fields
    ):
        raise ValueError("verifier artifact claim counts differ from trace")
    # Match the producer's normalized receipt, not just its counters. The
    # successful normalizer retains at most eight illustrative examples;
    # a parse failure writes none and reports an explicit error type.
    examples = receipt.get("examples")
    if type(examples) is not list or len(examples) > 8:
        raise ValueError("verifier artifact examples must be an array of at most eight")
    if receipt["status"] == "parse_error":
        if examples or any(receipt[name] for name, _ in fields):
            raise ValueError("verifier artifact parse error must not contain claims or examples")
        if not _is_nonblank_scalar_text(receipt.get("error")):
            raise ValueError("verifier parse-error artifact needs its error type")
    elif receipt["status"] != "ok" or "error" in receipt:
        raise ValueError("verifier artifact has contradictory success/error status")


# Separate from the verifier JSON receipt: this binds the exact report text
# given to human-evaluation tooling, not merely its length/word count.
MAX_REPORT_ARTIFACT_BYTES = 8 * 1024 * 1024


def validate_report_artifact(trace: dict, raw: bytes) -> None:
    """Match a prospective completed trace to the exact retained Markdown bytes.

    This is source-file continuity, not scientific correctness, external
    archival custody, or independent authentication of provider execution.
    """
    if (
        type(trace) is not dict
        or trace.get("search_provenance_schema") != REPORT_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA
        or trace.get("completed") is not True
    ):
        raise ValueError("report artifact requires a completed schema-6 trace")
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REPORT_ARTIFACT_BYTES:
        raise ValueError("report artifact must be bounded nonempty bytes")
    if hashlib.sha256(raw).hexdigest() != trace.get("report_artifact_sha256"):
        raise ValueError("report artifact SHA-256 differs from trace")
