"""Synthetic metasearch candidate custody; never contacts a web provider."""
import json

import pytest

from logic.search_provenance import (
    MAX_SEARCH_CANDIDATES,
    MAX_SEARCH_JSON_NUMBER_TOKEN_CHARS,
    MAX_SEARCH_RESULTS_JSON_BYTES,
    parse_search_candidates,
    selected_search_sources,
)


def test_preserves_order_duplicates_unicode_and_reported_backend_pools():
    raw = json.dumps([
        {"href": "https://example.org/α", "_search_backend_pool": "bing,google,brave", "title": "a"},
        {"href": "https://example.org/β", "_search_backend_pool": "duckduckgo"},
        {"href": "https://example.org/α", "_search_backend_pool": "duckduckgo"},
    ])
    assert parse_search_candidates(raw) == [
        {"url": "https://example.org/α", "backend_pool": "bing,google,brave"},
        {"url": "https://example.org/β", "backend_pool": "duckduckgo"},
        {"url": "https://example.org/α", "backend_pool": "duckduckgo"},
    ]


def test_legacy_missing_pool_is_unknown_not_guessed():
    entries = parse_search_candidates('[{"href":"https://a.test"}]')
    assert entries == [{"url": "https://a.test", "backend_pool": None}]
    assert selected_search_sources(entries, ["https://a.test"]) == entries


def test_selected_sources_follow_actual_scheduling_and_first_matching_candidate():
    candidates = parse_search_candidates(json.dumps([
        {"href": "https://a.test", "_search_backend_pool": "pool-a"},
        {"href": "https://b.test", "_search_backend_pool": "pool-b"},
        {"href": "https://a.test", "_search_backend_pool": "pool-c"},
        {"href": "https://c.test"},
    ]))
    assert selected_search_sources(candidates, ["https://c.test", "https://a.test"]) == [
        {"url": "https://c.test", "backend_pool": None},
        {"url": "https://a.test", "backend_pool": "pool-a"},
    ]
    assert selected_search_sources(candidates, []) == []


@pytest.mark.parametrize("raw", [
    None, b'[]', 17, "", "{bad", '{"href":"https://a.test"}',
    'null', '"https://a.test"', "true", "NaN", "Infinity",
    '[{"href":"https://a.test","href":"https://b.test"}]',
    '[{"href":"https://a.test","other":{"x":1,"x":2}}]',
    '[{"href":"https://a.test","other":NaN}]',
])
def test_rejects_ambiguous_or_nonarray_json_without_silent_zero_sources(raw):
    with pytest.raises(ValueError):
        parse_search_candidates(raw)


@pytest.mark.parametrize("bad_item", [None, False, 2, [], "https://a.test"])
def test_rejects_nonobject_candidate(bad_item):
    with pytest.raises(ValueError, match="must be a JSON object"):
        parse_search_candidates(json.dumps([bad_item]))


@pytest.mark.parametrize("bad_url", [None, False, 123, [], {}, "", " \t", "\ud800"])
def test_rejects_invalid_url_without_coercion(bad_url):
    with pytest.raises(ValueError, match="text href"):
        parse_search_candidates(json.dumps([{"href": bad_url}]))


@pytest.mark.parametrize("bad_pool", [False, 0, [], {}, "", " \n"])
def test_rejects_invalid_present_pool_label(bad_pool):
    with pytest.raises(ValueError, match="backend pool label"):
        parse_search_candidates(json.dumps([{
            "href": "https://a.test", "_search_backend_pool": bad_pool,
        }]))


@pytest.mark.parametrize("scheduled", [
    ["https://missing.test"], ["https://a.test", "https://a.test"],
])
def test_rejects_unattributable_or_duplicate_scheduled_urls(scheduled):
    candidates = parse_search_candidates('[{"href":"https://a.test"}]')
    with pytest.raises(ValueError, match="duplicate or absent"):
        selected_search_sources(candidates, scheduled)


def test_selection_copies_metadata_instead_of_aliasing_mutable_candidate():
    entries = parse_search_candidates('[{"href":"https://a.test","_search_backend_pool":"p"}]')
    chosen = selected_search_sources(entries, ["https://a.test"])
    chosen[0]["backend_pool"] = "changed"
    assert entries[0]["backend_pool"] == "p"


@pytest.mark.parametrize("valid_url", [
    "https://a.test/path?q=α", "http://8.8.8.8/",
    "https://[2606:4700:4700::1111]/",
    "https://münchen.de/über", "https://example.org./path",
])
def test_external_web_candidate_keeps_exact_original_url(valid_url):
    entries = parse_search_candidates(json.dumps([{"href": valid_url}]))
    assert entries == [{"url": valid_url, "backend_pool": None}]


@pytest.mark.parametrize("invalid_url", [
    "file:///etc/passwd", "javascript:alert(1)", "data:text/plain,hello",
    "//example.org/path", "https:///missing-host", "https://localhost/",
    "https://sub.localhost/", "http://router.local/",
    "https://printer.internal/", "https://router.home.arpa/",
    "http://127.0.0.1/", "http://10.4.5.6/",
    "http://169.254.169.254/latest/meta-data/",
    "http://192.168.1.1/", "http://[::1]/",
    "http://[fe80::1]/", "http://[::ffff:127.0.0.1]/",
    "http://2130706433/", "http://127.1/",
    "http://0x7f000001/", "http://0x7f.0.0.1/",
    "https://ⓛocalhost/", "http://example.org:0/",
    "http://example.org:99999/",
    "https://user:pass@example.org/",
    "https://example.org/has space", "https://example.org/\npath",
    "https://example.org/\tpath",
])
def test_rejects_unsafe_or_nonweb_candidate_before_browser_scheduling(invalid_url):
    with pytest.raises(ValueError, match=r"external HTTP\(S\) href"):
        parse_search_candidates(json.dumps([{"href": invalid_url}]))


def test_one_unsafe_candidate_fails_entire_batch_without_silent_filtering():
    raw = json.dumps([
        {"href": "https://example.org/a", "_search_backend_pool": "pool-a"},
        {"href": "http://127.1/private", "_search_backend_pool": "pool-a"},
        {"href": "https://example.org/b", "_search_backend_pool": "pool-a"},
    ])
    with pytest.raises(ValueError, match="Search candidate 2"):
        parse_search_candidates(raw)


def test_oversized_ascii_search_batch_fails_before_parse_without_partial_candidates():
    raw = json.dumps([
        {"href": "https://example.org/a", "title": "x" * MAX_SEARCH_RESULTS_JSON_BYTES},
    ])
    with pytest.raises(ValueError, match="JSON byte limit"):
        parse_search_candidates(raw)


def test_utf8_wire_size_not_character_count_controls_search_batch_limit():
    # Fewer code points than the limit, but more than 1 MiB of UTF-8.
    title = "界" * (MAX_SEARCH_RESULTS_JSON_BYTES // 3 + 1)
    raw = json.dumps([{"href": "https://example.org/a", "title": title}], ensure_ascii=False)
    assert len(raw) < MAX_SEARCH_RESULTS_JSON_BYTES
    with pytest.raises(ValueError, match="JSON byte limit"):
        parse_search_candidates(raw)


def test_rejects_unencodable_search_response_even_if_url_is_valid():
    with pytest.raises(ValueError, match="UTF-8 JSON text"):
        parse_search_candidates('[{"href":"https://example.org/","title":"' + chr(0xD800) + '"}]')


def test_overlarge_search_candidate_batch_is_not_silently_truncated():
    raw = json.dumps([
        {"href": f"https://example.org/{i}"} for i in range(MAX_SEARCH_CANDIDATES + 1)
    ])
    with pytest.raises(ValueError, match="candidate count limit"):
        parse_search_candidates(raw)


def test_exact_candidate_ceiling_is_preserved_without_reordering():
    raw = json.dumps([
        {"href": f"https://example.org/{i}"} for i in range(MAX_SEARCH_CANDIDATES)
    ])
    candidates = parse_search_candidates(raw)
    assert len(candidates) == MAX_SEARCH_CANDIDATES
    assert candidates[0]["url"] == "https://example.org/0"
    assert candidates[-1]["url"] == f"https://example.org/{MAX_SEARCH_CANDIDATES - 1}"


@pytest.mark.parametrize("numeric_json", [
    "1e10000",
    "9" * (MAX_SEARCH_JSON_NUMBER_TOKEN_CHARS + 1),
    "1." + "2" * MAX_SEARCH_JSON_NUMBER_TOKEN_CHARS,
])
def test_unbounded_or_nonfinite_metadata_numbers_fail_closed(numeric_json):
    raw = '[{"href":"https://example.org/","metadata":' + numeric_json + '}]'
    with pytest.raises(ValueError, match="JSON number"):
        parse_search_candidates(raw)


def test_finite_metadata_numbers_remain_backward_compatible():
    raw = '[{"href":"https://example.org/","priority":1,"weight":0.5}]'
    assert parse_search_candidates(raw) == [
        {"url": "https://example.org/", "backend_pool": None}
    ]


def test_pathologically_nested_provider_json_fails_as_validation_not_recursion_crash():
    raw = "[" * 1300 + "0" + "]" * 1300
    with pytest.raises(ValueError, match="valid bounded JSON text"):
        parse_search_candidates(raw)
