"""Pure schema validation for prospective planner-generated search queries.

A malformed response must not be silently converted into valid-looking search
queries; no retry or replacement-selection policy is introduced here.
"""

from __future__ import annotations

import json

PLANNED_QUERY_COUNT = 4


def parse_planned_search_queries(raw: str) -> list[str]:
    """Preserve four ordered text queries, rejecting invalid planner structure.

    Whitespace trimming matches the legacy behavior. Repeated *valid* queries
    are retained: semantic quality or redundancy is not a post-hoc exclusion
    criterion for prospective treatment execution.
    """
    if type(raw) is not str:
        raise ValueError("Planner did not return a JSON text list of queries")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Planner did not return a JSON text list of queries") from exc
    if type(parsed) is not list:
        raise ValueError("Planner output must be a JSON list")
    if len(parsed) != PLANNED_QUERY_COUNT:
        raise ValueError(
            f"Planner must return exactly {PLANNED_QUERY_COUNT} query entries; "
            f"got {len(parsed)}"
        )

    queries: list[str] = []
    for index, query in enumerate(parsed, start=1):
        if type(query) is not str or not query.strip():
            raise ValueError(f"Planner query {index} must be nonempty text")
        queries.append(query.strip())
    return queries
