from __future__ import annotations

import json
import time
from typing import Iterable

from ddgs import DDGS


# Keep the provider pool explicit for reproducibility. If the primary pool
# returns no usable results, try a second fixed pool, then DuckDuckGo alone.
# The pool string is attached to each result and persisted in experiment traces.
_BACKEND_POOLS = (
    "bing,google,brave",
    "mojeek,startpage,yahoo",
    "duckduckgo",
)
_SEARCH_ATTEMPTS = 2
_SEARCH_RETRY_DELAY_SECONDS = 1.0


def _normalize_results(
    results: Iterable[dict],
    *,
    backend_pool: str,
    limit: int,
) -> list[dict]:
    normalized = []
    seen_urls = set()
    for result in results or []:
        if not isinstance(result, dict):
            continue
        href = (result.get("href") or result.get("url") or "").strip()
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)
        item = dict(result)
        item["href"] = href
        item["_search_backend_pool"] = backend_pool
        normalized.append(item)
        if len(normalized) >= limit:
            break
    return normalized


def web_search(query: str, num_results: int = 4) -> str:
    """Search the web using fixed metasearch backend pools.

    A fresh DDGS client is created for each backend attempt to avoid carrying a
    rate-limited client state across pilot queries. The same frozen backend
    pools are retried once after a short delay because the public metasearch
    providers can transiently return an empty page or connection error. This is
    an infrastructure retry only: the query, backend pools, and requested result
    count are unchanged.
    """
    print(f"Searching with query {query}...")
    if not query or num_results <= 0:
        return "[]"

    errors = []
    for attempt in range(1, _SEARCH_ATTEMPTS + 1):
        for backend_pool in _BACKEND_POOLS:
            try:
                results = DDGS(timeout=20).text(
                    query=query,
                    region="us-en",
                    safesearch="moderate",
                    max_results=num_results,
                    backend=backend_pool,
                )
                normalized = _normalize_results(
                    results,
                    backend_pool=backend_pool,
                    limit=num_results,
                )
                if normalized:
                    return json.dumps(normalized, ensure_ascii=False, indent=4)
                message = f"attempt {attempt}: no results"
                errors.append(f"{backend_pool}: {message}")
                print(f"Search backend pool returned no results ({backend_pool}, {message})")
            except Exception as exc:
                message = f"attempt {attempt}: {type(exc).__name__}: {exc}"
                errors.append(f"{backend_pool}: {message}")
                print(f"Search backend pool failed ({backend_pool}, attempt {attempt}): {exc}")

        if attempt < _SEARCH_ATTEMPTS:
            time.sleep(_SEARCH_RETRY_DELAY_SECONDS)

    raise RuntimeError(
        "All frozen metasearch backend pools failed after retries for query. "
        + " | ".join(errors)
    )
