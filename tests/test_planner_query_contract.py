"""Synthetic-only tests for planner query identity before retrieval scheduling."""

import json

import pytest

from logic.planner_queries import parse_planned_search_queries


def test_preserves_order_unicode_trim_and_valid_duplicates():
    queries = ["  first topic  ", "α topic", "α topic", "last topic\t"]
    assert parse_planned_search_queries(json.dumps(queries)) == [
        "first topic", "α topic", "α topic", "last topic"
    ]


@pytest.mark.parametrize("value", [None, False, 12, b'["a","b","c","d"]'])
def test_rejects_nontext_provider_payload(value):
    with pytest.raises(ValueError, match="JSON text list"):
        parse_planned_search_queries(value)


@pytest.mark.parametrize("raw", ["{", "not JSON", "['a', 'b', 'c', 'd']"])
def test_rejects_malformed_json(raw):
    with pytest.raises(ValueError, match="JSON text list"):
        parse_planned_search_queries(raw)


@pytest.mark.parametrize("raw", ['{"queries": ["a", "b", "c", "d"]}', 'null', '"a"', 'NaN'])
def test_rejects_non_list_root(raw):
    with pytest.raises(ValueError, match="JSON list"):
        parse_planned_search_queries(raw)


@pytest.mark.parametrize("queries", [
    ["a", "b", "c"],
    ["a", "b", "c", "d", ""],
    ["a", "b", "c", "d", "e"],
    [],
])
def test_rejects_wrong_cardinality_without_discarding_entries(queries):
    with pytest.raises(ValueError, match="exactly 4 query entries"):
        parse_planned_search_queries(json.dumps(queries))


@pytest.mark.parametrize("bad", [None, False, 0, 1.5, {"q": "text"}, ["text"], "", "  \t  "])
def test_rejects_invalid_query_element_instead_of_coercing_or_filtering(bad):
    with pytest.raises(ValueError, match="Planner query 3 must be nonempty text"):
        parse_planned_search_queries(json.dumps(["a", "b", bad, "d"]))


def test_five_entries_with_blank_fails_instead_of_inflating_a_four_query_plan():
    with pytest.raises(ValueError, match="exactly 4 query entries; got 5"):
        parse_planned_search_queries(json.dumps(["a", "b", "", "c", "d"]))
