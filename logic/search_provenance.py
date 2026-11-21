"""Fail-closed candidate schema and lossless local backend-pool provenance.

The backend pool is the metasearch adapter's selected *request pool*, not
proof of which external search engine produced any individual result.
"""

from __future__ import annotations

import json


def _unique_object_members(pairs: list[tuple[str, object]]) -> dict:
    members = {}
    for name, value in pairs:
        if name in members:
            raise ValueError(f"Ambiguous search result JSON key {name!r}")
        members[name] = value
    return members


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"Non-finite search result JSON constant {token!r}")


def parse_search_candidates(raw: str) -> list[dict[str, str | None]]:
    """Extract ordered candidate URLs and *reported* pools without coercion.

    Missing pool labels remain ``None`` for legacy search stubs. Invalid
    response shapes fail the prospective run rather than looking like an
    empty/unsuccessful search. No URLs are sorted, repaired or filtered.
    """
    if type(raw) is not str:
        raise ValueError("Search results must be JSON text")
    try:
        results = json.loads(
            raw,
            object_pairs_hook=_unique_object_members,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("Search results must be valid JSON text") from exc
    if type(results) is not list:
        raise ValueError("Search results must be a JSON array")

    candidates = []
    for index, item in enumerate(results, start=1):
        if type(item) is not dict:
            raise ValueError(f"Search candidate {index} must be a JSON object")
        url = item.get("href")
        if type(url) is not str or not url.strip() or any(
            0xD800 <= ord(char) <= 0xDFFF for char in url
        ):
            raise ValueError(f"Search candidate {index} must contain a text href")
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
