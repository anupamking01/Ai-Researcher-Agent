"""Fail-closed candidate schema and lossless local backend-pool provenance.

The backend pool is the metasearch adapter's selected *request pool*, not
proof of which external search engine produced any individual result.
"""

from __future__ import annotations

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


_AMBIGUOUS_NUMERIC_HOST = re.compile(
    r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+)){0,3}\Z"
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
        ascii_host = host.rstrip(".").encode("idna").decode("ascii").lower()
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
        if type(url) is not str or not url.strip() or any(
            0xD800 <= ord(char) <= 0xDFFF for char in url
        ):
            raise ValueError(f"Search candidate {index} must contain a text href")
        _require_external_web_url(url, index=index)
        pool = item.get("_search_backend_pool")
        if pool is not None and (type(pool) is not str or not pool.strip()):
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
SEARCH_TRACE_PROVENANCE_SCHEMA = 1


def validate_search_trace_provenance(trace: dict) -> None:
    """Conserve ordered query, candidate, scheduled-source and browse ledgers."""
    if type(trace) is not dict or (
        type(trace.get("search_provenance_schema")) is not int
        or trace["search_provenance_schema"] != SEARCH_TRACE_PROVENANCE_SCHEMA
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
        query_cursor += 1
        cu, su = record.get("candidate_urls"), record.get("scheduled_urls")
        cs, ss = record.get("candidate_sources"), record.get("scheduled_sources")
        if any(type(x) is not list for x in (cu, su, cs, ss)):
            raise ValueError(f"search record {index} missing source arrays")
        for entry in cs + ss:
            if (
                type(entry) is not dict
                or type(entry.get("url")) is not str
                or not entry["url"].strip()
                or "backend_pool" not in entry
                or (entry["backend_pool"] is not None and (
                    type(entry["backend_pool"]) is not str
                    or not entry["backend_pool"].strip()
                ))
            ):
                raise ValueError(f"search record {index} invalid source metadata")
            _require_external_web_url(entry["url"], index=index)
        if [entry["url"] for entry in cs] != cu:
            raise ValueError(f"search record {index} candidate URL mismatch")
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
