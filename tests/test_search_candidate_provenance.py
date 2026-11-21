"""Synthetic metasearch candidate custody; never contacts a web provider."""
import ast
import json
from pathlib import Path

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


def test_search_request_candidate_ceiling_is_lossless_at_boundary():
    raw = json.dumps([
        {"href": "https://a.test/1", "_search_backend_pool": "first"},
        {"href": "https://a.test/1", "_search_backend_pool": "second"},
        {"href": "https://b.test/2"},
    ])
    assert parse_search_candidates(raw, expected_limit=3) == parse_search_candidates(raw)


@pytest.mark.parametrize("limit, count", [(1, 2), (3, 4), (20, 21)])
def test_search_request_overproduction_fails_whole_batch(limit, count):
    raw = json.dumps([
        {"href": f"https://a.test/{i}"} for i in range(count)
    ])
    with pytest.raises(ValueError, match="requested candidate limit"):
        parse_search_candidates(raw, expected_limit=limit)


@pytest.mark.parametrize("limit", [0, -1, True, False, 2.0, "2", 129])
def test_invalid_requested_search_limit_fails_before_parsing(limit):
    with pytest.raises(ValueError, match="positive bounded integer"):
        parse_search_candidates("not even JSON", expected_limit=limit)


def test_actual_agent_search_path_forwards_its_request_limit_to_parser():
    # Source-level wiring guard avoids importing browser/provider modules in
    # firewalled lightweight CI; parser behavior is tested independently above.
    agent_path = Path(__file__).resolve().parents[1] / "logic" / "research_agent.py"
    tree = ast.parse(agent_path.read_text(encoding="utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "parse_search_candidates"
    ]
    assert len(calls) == 1
    assert any(
        keyword.arg == "expected_limit"
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == "candidate_limit"
        for keyword in calls[0].keywords
    )


def _search_custody_fixture():
    return {
        "search_provenance_schema": 1, "query_count": 2,
        "search_call_count": 2, "source_count": 1,
        "completed": True,
        "successful_source_count": 1, "failed_source_count": 0,
        "source_success_rate": 1.0,
        "successful_urls": ["https://example.org/one"], "failed_urls": [],
        "search_queries": ["q1", "q2"],
        "scheduled_urls": ["https://example.org/one"],
        "search_records": [
            {
                "query": "q1",
                "candidate_urls": ["https://example.org/one"] * 2,
                "candidate_sources": [
                    {"url": "https://example.org/one", "backend_pool": "pool-a"},
                    {"url": "https://example.org/one", "backend_pool": "pool-b"},
                ],
                "scheduled_urls": ["https://example.org/one"],
                "scheduled_sources": [
                    {"url": "https://example.org/one", "backend_pool": "pool-a"},
                ],
            },
            {
                "query": "q2", "candidate_urls": [], "candidate_sources": [],
                "scheduled_urls": [], "scheduled_sources": [],
                "search_error": "synthetic outage",
            },
        ],
    }


def test_versioned_search_custody_accepts_duplicate_candidates_and_failed_query():
    from logic.search_provenance import validate_search_trace_provenance
    validate_search_trace_provenance(_search_custody_fixture())


def test_versioned_search_custody_accepts_skipped_planner_query():
    from logic.search_provenance import validate_search_trace_provenance
    t = _search_custody_fixture()
    t["search_queries"].insert(1, "zero budget query")
    t["query_count"] += 1
    validate_search_trace_provenance(t)


@pytest.mark.parametrize("mutate", [
    lambda t: t.update(search_provenance_schema=True),
    lambda t: t.update(search_provenance_schema=3),
    lambda t: t.update(query_count=1),
    lambda t: t.update(search_call_count=1),
    lambda t: t.update(source_count=2),
    lambda t: t["search_records"].reverse(),
    lambda t: t["search_records"][0].update(candidate_urls=[]),
    lambda t: t["search_records"][0]["scheduled_sources"][0].update(backend_pool="pool-b"),
    lambda t: t["search_records"][0]["scheduled_urls"].append("https://missing.test"),
    lambda t: t["search_records"][0]["candidate_sources"][0].update(url="http://127.0.0.1"),
    lambda t: t["search_records"][0]["scheduled_sources"][0].update(backend_pool=False),
    lambda t: t["search_records"][0].update(search_error="inconsistent"),
    lambda t: t["search_records"][1].update(candidate_urls=["https://unexpected.test"]),
    lambda t: t["search_records"][0].update(candidate_sources=None),
    lambda t: t.update(scheduled_urls=["https://forged.test"]),
    lambda t: t.update(scheduled_urls=["https://example.org/one"] * 2, source_count=2),
])
def test_versioned_search_custody_rejects_inconsistent_sources(mutate):
    from copy import deepcopy
    from logic.search_provenance import validate_search_trace_provenance
    t = deepcopy(_search_custody_fixture())
    mutate(t)
    with pytest.raises(ValueError):
        validate_search_trace_provenance(t)


def _mixed_browse_outcomes():
    """Three ordered attempts with interleaved successes and a failure."""
    from copy import deepcopy
    t = deepcopy(_search_custody_fixture())
    record = t["search_records"][0]
    extra = [
        {"url": "https://example.org/two", "backend_pool": "pool-a"},
        {"url": "https://example.org/three", "backend_pool": "pool-a"},
    ]
    record["candidate_sources"].extend(extra)
    record["candidate_urls"].extend(entry["url"] for entry in extra)
    record["scheduled_sources"].extend(extra)
    record["scheduled_urls"].extend(entry["url"] for entry in extra)
    t["scheduled_urls"].extend(entry["url"] for entry in extra)
    t["source_count"] = 3
    t["successful_urls"] = [
        "https://example.org/one", "https://example.org/three",
    ]
    t["failed_urls"] = ["https://example.org/two"]
    t["successful_source_count"] = 2
    t["failed_source_count"] = 1
    t["source_success_rate"] = 2 / 3
    return t


def test_browse_outcome_custody_preserves_interleaved_attempt_order():
    from logic.search_provenance import validate_search_trace_provenance
    validate_search_trace_provenance(_mixed_browse_outcomes())


@pytest.mark.parametrize("mutate", [
    lambda t: t["successful_urls"].reverse(),  # same URLs and counts, wrong order
    lambda t: t["failed_urls"].append("https://example.org/three"),
    lambda t: t["failed_urls"].append("https://example.org/unselected"),
    lambda t: t["successful_urls"].append("https://example.org/one"),
    lambda t: t["successful_urls"].pop(),
    lambda t: t.update(successful_source_count=3),
    lambda t: t.update(failed_source_count=True),
    lambda t: t.update(source_success_rate=1.0),
    lambda t: t.update(source_success_rate=float("nan")),
    lambda t: t.update(source_success_rate=True),
    lambda t: t.pop("source_success_rate"),
    lambda t: t.pop("successful_urls"),
    lambda t: t.update(completed="true"),
])
def test_browse_outcome_custody_rejects_mismatched_identity_order_or_rate(mutate):
    from logic.search_provenance import validate_search_trace_provenance
    t = _mixed_browse_outcomes()
    mutate(t)
    with pytest.raises(ValueError, match="browse"):
        validate_search_trace_provenance(t)


def test_incomplete_trace_may_leave_pending_attempt_without_claiming_success():
    # A future failed/timeout trace can conserve observed classifications
    # without fabricating completion of unresolved browsing calls.
    from logic.search_provenance import validate_search_trace_provenance
    t = _mixed_browse_outcomes()
    t["completed"] = False
    t["failed_urls"] = []
    t["failed_source_count"] = 0
    validate_search_trace_provenance(t)


def test_zero_attempt_incomplete_trace_has_zero_not_nan_success_rate():
    from logic.search_provenance import validate_search_trace_provenance
    t = _search_custody_fixture()
    t.update(
        completed=False, source_count=0,
        scheduled_urls=[], successful_urls=[], failed_urls=[],
        successful_source_count=0, failed_source_count=0,
        source_success_rate=0.0,
    )
    t["search_records"][0]["scheduled_urls"] = []
    t["search_records"][0]["scheduled_sources"] = []
    validate_search_trace_provenance(t)


def test_versioned_search_trace_is_emitted_and_checked_by_runner():
    import ast
    root = Path(__file__).resolve().parents[1]
    run_text = (root / "logic/run.py").read_text(encoding="utf-8")
    runner_text = (root / "scripts/run_budget_main_study.py").read_text(encoding="utf-8")
    run_ast = ast.parse(run_text)
    stamped = [
        n for n in ast.walk(run_ast)
        if isinstance(n, ast.Assign) and any(
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == "trace_payload"
            and isinstance(target.slice, ast.Constant)
            and target.slice.value == "search_provenance_schema"
            for target in n.targets
        )
    ]
    assert len(stamped) == 1
    assert 'validate_search_trace_provenance(trace, experiment=experiment)' in runner_text


def _request_bound_search_custody_fixture():
    """Synthetic schema-2 trace with two one-attempt query slots."""
    from copy import deepcopy
    trace = deepcopy(_search_custody_fixture())
    trace.update(
        search_provenance_schema=2,
        source_budget=2,
        search_candidate_multiplier=2,
    )
    for record in trace["search_records"]:
        record["requested_candidate_limit"] = 2
    return trace


def test_schema2_reconciles_request_limits_to_frozen_budget_and_candidate_records():
    from logic.search_provenance import validate_search_trace_provenance
    validate_search_trace_provenance(_request_bound_search_custody_fixture())


@pytest.mark.parametrize("mutate", [
    lambda t: t["search_records"][0].pop("requested_candidate_limit"),
    lambda t: t["search_records"][0].update(requested_candidate_limit=True),
    lambda t: t["search_records"][0].update(requested_candidate_limit=3),
    lambda t: t["search_records"][0].update(requested_candidate_limit=1),
    lambda t: t["search_records"][1].update(requested_candidate_limit=0),
    lambda t: t.update(search_candidate_multiplier=3),
    lambda t: t.update(search_candidate_multiplier=0),
    lambda t: t.update(search_candidate_multiplier=True),
    lambda t: t.update(source_budget=1),
    lambda t: t.update(source_budget=True),
])
def test_schema2_rejects_forged_request_bound_or_experiment_controls(mutate):
    from logic.search_provenance import validate_search_trace_provenance
    trace = _request_bound_search_custody_fixture()
    mutate(trace)
    with pytest.raises(ValueError):
        validate_search_trace_provenance(trace)


def test_schema2_rejects_candidate_overproduction_even_with_valid_scheduled_counts():
    from logic.search_provenance import validate_search_trace_provenance
    trace = _request_bound_search_custody_fixture()
    extra = {"url": "https://example.org/unscheduled", "backend_pool": "pool"}
    trace["search_records"][0]["candidate_sources"].append(extra)
    trace["search_records"][0]["candidate_urls"].append(extra["url"])
    with pytest.raises(ValueError, match="requested candidate limit"):
        validate_search_trace_provenance(trace)


def test_schema2_rejects_search_of_a_zero_budget_planner_slot():
    from logic.search_provenance import validate_search_trace_provenance
    trace = _request_bound_search_custody_fixture()
    trace["search_queries"].insert(1, "skipped by planner budget")
    trace["query_count"] = 3
    # With two total attempts and three queries, the third query has no slot.
    with pytest.raises(ValueError, match="no query browse budget"):
        validate_search_trace_provenance(trace)


def test_schema2_request_metadata_is_emitted_on_success_error_and_trace():
    root = Path(__file__).resolve().parents[1]
    agent_source = (root / "logic" / "research_agent.py").read_text(encoding="utf-8")
    run_source = (root / "logic" / "run.py").read_text(encoding="utf-8")
    assert agent_source.count('"requested_candidate_limit": candidate_limit') == 2
    assert (
        'trace_payload["search_candidate_multiplier"] = config.search_candidate_multiplier'
        in run_source
    )

# Prospective per-query allocation conservation: search-call cardinality alone
# must not allow a completed report to silently omit a funded planner query.
@pytest.mark.parametrize("omitted_record", [0, 1])
def test_schema2_completed_trace_rejects_unattempted_funded_query(omitted_record):
    from logic.search_provenance import validate_search_trace_provenance
    trace = _request_bound_search_custody_fixture()
    trace["search_records"].pop(omitted_record)
    trace["search_call_count"] -= 1
    with pytest.raises(ValueError, match="omits funded planned queries"):
        validate_search_trace_provenance(trace)


def test_schema2_completed_trace_allows_trailing_zero_budget_query_slot():
    from logic.search_provenance import validate_search_trace_provenance
    trace = _request_bound_search_custody_fixture()
    trace["search_queries"].append("intentionally unfunded third query")
    trace["query_count"] += 1
    # Two available attempts fund q1 and q2, but not q3.
    validate_search_trace_provenance(trace)


def test_schema2_completed_trace_rejects_zero_query_plans():
    from logic.search_provenance import validate_search_trace_provenance
    trace = _request_bound_search_custody_fixture()
    trace.update(
        search_queries=[], query_count=0, search_records=[],
        search_call_count=0, source_count=0, scheduled_urls=[],
        successful_urls=[], failed_urls=[], successful_source_count=0,
        failed_source_count=0, source_success_rate=0.0,
    )
    with pytest.raises(ValueError, match="omits funded planned queries"):
        validate_search_trace_provenance(trace)


def test_schema2_rejects_per_query_overspend_even_when_global_count_is_bounded():
    from logic.search_provenance import validate_search_trace_provenance
    trace = _request_bound_search_custody_fixture()
    # Four global browse slots split 2+2. q1 improperly spends 3 and q2
    # records a real search outage. The former validator accepted this:
    # requests and all run-level URL/count ledgers are self-consistent.
    trace["source_budget"] = 4
    candidates = [
        {"url": f"https://example.org/{suffix}", "backend_pool": "pool"}
        for suffix in ("one", "two", "three")
    ]
    first, second = trace["search_records"]
    first.update(
        requested_candidate_limit=4,
        candidate_urls=[c["url"] for c in candidates],
        candidate_sources=candidates,
        scheduled_urls=[c["url"] for c in candidates],
        scheduled_sources=[dict(c) for c in candidates],
    )
    # With three attempts already recorded, q2 could request two candidates.
    second["requested_candidate_limit"] = 2
    trace.update(
        scheduled_urls=[c["url"] for c in candidates],
        source_count=3,
        successful_urls=[candidates[0]["url"]],
        failed_urls=[candidates[1]["url"], candidates[2]["url"]],
        successful_source_count=1, failed_source_count=2,
        source_success_rate=1 / 3,
    )
    with pytest.raises(ValueError, match="exceeds allocated query browse budget"):
        validate_search_trace_provenance(trace)

# Schema 3 independently checks the original experiment's plan identity,
# beyond candidate-request and source-budget arithmetic.
def _treatment_bound_planner_fixture():
    trace = _request_bound_search_custody_fixture()
    trace.update(
        search_provenance_schema=3, planning_mode="planner",
        question="What is the research question?",
    )
    # Two scheduled slots fund q1/q2; q3/q4 remain legitimately unfunded.
    trace["search_queries"].extend(["q3", "q4"])
    trace["query_count"] = 4
    return trace


def _treatment_bound_direct_fixture():
    trace = _request_bound_search_custody_fixture()
    trace.update(
        search_provenance_schema=3, planning_mode="direct",
        question="q1", search_queries=["q1"], query_count=1,
        source_budget=1, search_call_count=1,
    )
    trace["search_records"] = trace["search_records"][:1]
    return trace


def test_schema3_accepts_original_direct_question_and_four_planner_queries():
    from logic.search_provenance import validate_search_trace_provenance
    validate_search_trace_provenance(_treatment_bound_direct_fixture())
    validate_search_trace_provenance(_treatment_bound_planner_fixture())


def test_schema3_preserves_duplicate_planned_queries_as_distinct_slots():
    from logic.search_provenance import validate_search_trace_provenance
    trace = _treatment_bound_planner_fixture()
    trace["search_queries"][1] = "q1"
    trace["search_records"][1]["query"] = "q1"
    validate_search_trace_provenance(trace)


@pytest.mark.parametrize("alteration", [
    lambda t: t.update(question="different research question"),
    lambda t: t.update(question="q1 "),
    lambda t: t.update(question=""),
    lambda t: t.pop("question"),
    lambda t: t.update(planning_mode="planner"),
    lambda t: t.update(planning_mode=None),
    lambda t: t.pop("planning_mode"),
])
def test_schema3_rejects_direct_query_identity_or_mode_changes(alteration):
    from logic.search_provenance import validate_search_trace_provenance
    trace = _treatment_bound_direct_fixture()
    alteration(trace)
    with pytest.raises(ValueError, match="search plan"):
        validate_search_trace_provenance(trace)


@pytest.mark.parametrize("alteration", [
    lambda t: (t["search_queries"].pop(), t.update(query_count=3)),
    lambda t: (t["search_queries"].append("q5"), t.update(query_count=5)),
    lambda t: t.update(question=" "),
    lambda t: t.pop("question"),
    lambda t: t.update(planning_mode="direct"),
    lambda t: t.update(planning_mode=False),
    lambda t: t.pop("planning_mode"),
])
def test_schema3_rejects_planner_arity_or_treatment_identity_changes(alteration):
    from logic.search_provenance import validate_search_trace_provenance
    trace = _treatment_bound_planner_fixture()
    alteration(trace)
    with pytest.raises(ValueError, match="search plan"):
        validate_search_trace_provenance(trace)


def test_schema2_is_not_retroactively_certified_for_plan_arity():
    from logic.search_provenance import validate_search_trace_provenance
    trace = _request_bound_search_custody_fixture()
    validate_search_trace_provenance(trace)


def test_schema3_incomplete_plan_is_preserved_without_fabricating_queries():
    from logic.search_provenance import validate_search_trace_provenance
    trace = _treatment_bound_direct_fixture()
    trace.update(completed=False, planning_mode=None, question=None)
    validate_search_trace_provenance(trace)


# Schema 4: the trace's treatment factors and the independently persisted
# ExperimentConfig envelope must both match the fixed four-arm assignment.
# All synthetic records are offline; no treatment or evaluator is executed.
def _factor_bound_fixture(variant):
    from copy import deepcopy
    factors = {
        "D3": ("direct", 3, "none"),
        "D6": ("direct", 6, "none"),
        "P6": ("planner", 6, "none"),
        "P6V": ("planner", 6, "verify"),
    }
    mode, budget, verification = factors[variant]
    trace = deepcopy(
        _treatment_bound_direct_fixture() if mode == "direct"
        else _treatment_bound_planner_fixture()
    )
    trace.update(
        search_provenance_schema=4,
        variant_id=variant,
        source_budget=budget,
        verification_mode=verification,
    )
    if mode == "direct":
        trace["search_records"][0]["requested_candidate_limit"] = min(budget * 2, 20)
    else:
        # Six slots over four planner queries: 2, 2, 1, 1. All funded
        # searches must appear, even when the provider returns an outage.
        trace["search_records"][0]["requested_candidate_limit"] = 4
        trace["search_records"][1]["requested_candidate_limit"] = 4
        for query in ("q3", "q4"):
            trace["search_records"].append({
                "query": query,
                "requested_candidate_limit": 2,
                "candidate_urls": [], "candidate_sources": [],
                "scheduled_urls": [], "scheduled_sources": [],
                "search_error": "synthetic provider outage",
            })
        trace["search_call_count"] = 4
    experiment = {
        "variant_id": variant,
        "planning_mode": mode,
        "source_budget": budget,
        "verification_mode": verification,
    }
    return trace, experiment


@pytest.mark.parametrize("variant", ["D3", "D6", "P6", "P6V"])
def test_schema4_accepts_all_frozen_treatment_factor_assignments(variant):
    from logic.search_provenance import validate_search_trace_provenance
    trace, experiment = _factor_bound_fixture(variant)
    validate_search_trace_provenance(trace, experiment=experiment)


@pytest.mark.parametrize("mutate", [
    lambda t: t.update(variant_id="D6"),
    lambda t: t.update(variant_id="unknown"),
    lambda t: t.update(verification_mode="verify"),
    lambda t: t.update(verification_mode=None),
    lambda t: t.update(source_budget=6),
    lambda t: t.update(source_budget=True),
    lambda t: t.pop("variant_id"),
])
def test_schema4_rejects_forged_completed_trace_factors(mutate):
    from logic.search_provenance import validate_search_trace_provenance
    trace, experiment = _factor_bound_fixture("D3")
    mutate(trace)
    with pytest.raises(ValueError, match="treatment factor"):
        validate_search_trace_provenance(trace, experiment=experiment)


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(variant_id="P6V"),
    lambda e: e.update(planning_mode="direct"),
    lambda e: e.update(verification_mode="verify"),
    lambda e: e.update(source_budget=3),
    lambda e: e.update(source_budget=True),
    lambda e: e.pop("source_budget"),
])
def test_schema4_rejects_conflicting_persisted_experiment_envelope(mutate):
    from logic.search_provenance import validate_search_trace_provenance
    trace, experiment = _factor_bound_fixture("P6")
    mutate(experiment)
    with pytest.raises(ValueError, match="treatment factor"):
        validate_search_trace_provenance(trace, experiment=experiment)


def test_schema4_missing_envelope_is_not_silently_certified():
    from logic.search_provenance import validate_search_trace_provenance
    trace, _ = _factor_bound_fixture("P6V")
    with pytest.raises(ValueError, match="treatment factor"):
        validate_search_trace_provenance(trace)


def test_schema4_incomplete_trace_does_not_invent_missing_factors():
    from logic.search_provenance import validate_search_trace_provenance
    trace, _ = _factor_bound_fixture("D3")
    trace.update(completed=False, variant_id=None, verification_mode=None)
    validate_search_trace_provenance(trace)


def test_schema3_remains_valid_without_schema4_envelope_certification():
    from logic.search_provenance import validate_search_trace_provenance
    trace = _treatment_bound_direct_fixture()
    validate_search_trace_provenance(trace)


# Schema 5: source-independent, outcome-blind proof that a claimed verifier
# treatment has a retained JSON receipt consistent with the trace ledger.
def _verifier_bound_fixture(variant="P6V", *, status="ok"):
    import hashlib
    from logic.search_provenance import VERIFIER_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA

    trace, experiment = _factor_bound_fixture(variant)
    trace["search_provenance_schema"] = VERIFIER_BOUND_SEARCH_TRACE_PROVENANCE_SCHEMA
    counters = {
        "citation_count": 0, "supported_claim_count": 0,
        "partially_supported_claim_count": 0,
        "unsupported_claim_count": 0, "contradicted_claim_count": 0,
    }
    trace.update(counters)
    if variant != "P6V":
        trace.update(
            verification_status="not_requested",
            verification_artifact_sha256=None,
        )
        return trace, experiment, None

    receipt = {
        "status": status, "claims_checked": 2,
        "supported": 1, "partially_supported": 1,
        "unsupported": 0, "contradicted": 0, "examples": [],
    }
    if status == "parse_error":
        receipt.update(
            claims_checked=0, supported=0, partially_supported=0,
            error="ValueError",
        )
    raw = json.dumps(receipt, ensure_ascii=False).encode("utf-8")
    trace.update(
        verification_status=status,
        verification_artifact_sha256=hashlib.sha256(raw).hexdigest(),
        citation_count=receipt["claims_checked"],
        supported_claim_count=receipt["supported"],
        partially_supported_claim_count=receipt["partially_supported"],
    )
    return trace, experiment, raw


@pytest.mark.parametrize("variant", ["D3", "D6", "P6", "P6V"])
def test_schema5_valid_frozen_arm_verification_receipts(variant):
    from logic.search_provenance import (
        validate_search_trace_provenance, validate_verifier_artifact,
    )
    trace, experiment, raw = _verifier_bound_fixture(variant)
    validate_search_trace_provenance(trace, experiment=experiment)
    if raw is not None:
        validate_verifier_artifact(trace, raw)


def test_schema5_accepts_retained_verifier_parse_error_without_inventing_claims():
    from logic.search_provenance import (
        validate_search_trace_provenance, validate_verifier_artifact,
    )
    trace, experiment, raw = _verifier_bound_fixture(status="parse_error")
    validate_search_trace_provenance(trace, experiment=experiment)
    validate_verifier_artifact(trace, raw)


@pytest.mark.parametrize("mutate", [
    lambda t: t.update(verification_status="not_requested"),
    lambda t: t.update(verification_status="repaired"),
    lambda t: t.update(verification_artifact_sha256=None),
    lambda t: t.update(verification_artifact_sha256="0" * 64),
    lambda t: t.update(verification_artifact_sha256=True),
    lambda t: t.update(citation_count=3),
    lambda t: t.update(supported_claim_count=0),
    lambda t: t.update(contradicted_claim_count=True),
])
def test_schema5_rejects_forged_verifier_trace_ledger(mutate):
    from logic.search_provenance import validate_search_trace_provenance
    trace, experiment, _ = _verifier_bound_fixture()
    mutate(trace)
    if trace.get("verification_artifact_sha256") == "0" * 64:
        # A syntactically valid but forged digest is rejected against bytes
        # by the separate retained-artifact validator, not the schema check.
        from logic.search_provenance import validate_verifier_artifact
        validate_search_trace_provenance(trace, experiment=experiment)
        with pytest.raises(ValueError, match="SHA-256"):
            validate_verifier_artifact(trace, _verifier_bound_fixture()[2])
    else:
        with pytest.raises(ValueError, match="verif"):
            validate_search_trace_provenance(trace, experiment=experiment)


@pytest.mark.parametrize("mutate", [
    lambda t: t.update(verification_status="ok"),
    lambda t: t.update(verification_artifact_sha256="a" * 64),
    lambda t: t.update(citation_count=1),
])
def test_schema5_non_verifier_arms_cannot_claim_verification(mutate):
    from logic.search_provenance import validate_search_trace_provenance
    trace, experiment, _ = _verifier_bound_fixture("D3")
    mutate(trace)
    with pytest.raises(ValueError, match="non-verifier"):
        validate_search_trace_provenance(trace, experiment=experiment)


@pytest.mark.parametrize("malformed", [
    b"", b"not-json",
    b'{"status":"ok","status":"ok"}',
    b'{"status":"ok","examples":NaN}',
])
def test_schema5_rejects_malformed_retained_verifier_evidence(malformed):
    import hashlib
    from logic.search_provenance import validate_verifier_artifact
    trace, _, _ = _verifier_bound_fixture()
    trace["verification_artifact_sha256"] = hashlib.sha256(malformed).hexdigest()
    with pytest.raises(ValueError, match="verifier artifact"):
        validate_verifier_artifact(trace, malformed)


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(claims_checked=4),
    lambda r: r.update(supported=0),
    lambda r: r.update(status="parse_error"),
    lambda r: r.update(examples="not-an-array"),
])
def test_schema5_rejects_digest_rebound_but_inconsistent_verifier_receipt(mutation):
    import hashlib
    from logic.search_provenance import validate_verifier_artifact
    trace, _, raw = _verifier_bound_fixture()
    receipt = json.loads(raw)
    mutation(receipt)
    corrupt = json.dumps(receipt).encode("utf-8")
    trace["verification_artifact_sha256"] = hashlib.sha256(corrupt).hexdigest()
    with pytest.raises(ValueError, match="verifier artifact"):
        validate_verifier_artifact(trace, corrupt)


def test_schema5_incomplete_verifier_trace_retains_uncertainty():
    from logic.search_provenance import validate_search_trace_provenance
    trace, experiment, _ = _verifier_bound_fixture()
    trace.update(
        completed=False, verification_status="not_requested",
        verification_artifact_sha256=None,
    )
    validate_search_trace_provenance(trace, experiment=experiment)


def test_schema4_remains_valid_without_physical_verifier_receipt():
    from logic.search_provenance import validate_search_trace_provenance
    trace, experiment = _factor_bound_fixture("P6V")
    validate_search_trace_provenance(trace, experiment=experiment)


def test_schema5_custody_wired_to_persisted_producer_and_runner():
    root = Path(__file__).resolve().parents[1]
    agent = (root / "logic/research_agent.py").read_text(encoding="utf-8")
    run = (root / "logic/run.py").read_text(encoding="utf-8")
    runner = (root / "scripts/run_budget_main_study.py").read_text(encoding="utf-8")
    assert 'self.verification_artifact_sha256 = hashlib.sha256(' in agent
    assert 'trace_payload["verification_artifact_sha256"] = getattr(' in run
    assert '_read_treatment_trace_bytes(evidence_path)' in runner
    assert 'validate_verifier_artifact(' in runner


# Schema 6: a completed report's UTF-8 content is part of its treatment
# evidence. A same-word-count substitution must fail independently of the
# verifier JSON (including for the three no-verification arms).
def _report_bound_fixture(variant="P6V"):
    import hashlib
    from logic.search_provenance import SEARCH_TRACE_PROVENANCE_SCHEMA

    trace, experiment, verifier_bytes = _verifier_bound_fixture(variant)
    report_bytes = b"# Synthetic report\\nalpha beta gamma\\n"
    trace["search_provenance_schema"] = SEARCH_TRACE_PROVENANCE_SCHEMA
    trace["report_artifact_sha256"] = hashlib.sha256(report_bytes).hexdigest()
    return trace, experiment, verifier_bytes, report_bytes


@pytest.mark.parametrize("variant", ["D3", "D6", "P6", "P6V"])
def test_schema6_accepts_content_bound_report_for_all_treatments(variant):
    from logic.search_provenance import (
        validate_search_trace_provenance, validate_report_artifact,
        validate_verifier_artifact,
    )
    trace, experiment, verifier_bytes, report_bytes = _report_bound_fixture(variant)
    validate_search_trace_provenance(trace, experiment=experiment)
    validate_report_artifact(trace, report_bytes)
    if verifier_bytes is not None:
        validate_verifier_artifact(trace, verifier_bytes)


@pytest.mark.parametrize("mutation", [
    lambda t: t.pop("report_artifact_sha256"),
    lambda t: t.update(report_artifact_sha256=None),
    lambda t: t.update(report_artifact_sha256=True),
    lambda t: t.update(report_artifact_sha256="A" * 64),
    lambda t: t.update(report_artifact_sha256="short"),
])
def test_schema6_rejects_missing_or_invalid_completed_report_digest(mutation):
    from logic.search_provenance import validate_search_trace_provenance
    trace, experiment, _, _ = _report_bound_fixture("D6")
    mutation(trace)
    with pytest.raises(ValueError, match="report artifact SHA-256"):
        validate_search_trace_provenance(trace, experiment=experiment)


def test_schema6_rejects_same_word_count_report_substitution():
    import hashlib
    from logic.search_provenance import (
        validate_search_trace_provenance, validate_report_artifact,
    )
    trace, experiment, _, original = _report_bound_fixture("D3")
    substituted = original.replace(b"alpha", b"omega")
    assert len(original.split()) == len(substituted.split())
    validate_search_trace_provenance(trace, experiment=experiment)
    with pytest.raises(ValueError, match="report artifact SHA-256 differs"):
        validate_report_artifact(trace, substituted)
    # Digest rebound to different bytes is internally coherent, but cannot
    # independently authenticate who produced those bytes.
    trace["report_artifact_sha256"] = hashlib.sha256(substituted).hexdigest()
    validate_report_artifact(trace, substituted)


@pytest.mark.parametrize("bad_raw", [None, "", b"", b"x" * (8 * 1024 * 1024 + 1)])
def test_schema6_rejects_missing_or_unbounded_retained_report_bytes(bad_raw):
    from logic.search_provenance import validate_report_artifact
    trace, _, _, _ = _report_bound_fixture()
    with pytest.raises(ValueError, match="report artifact must be bounded"):
        validate_report_artifact(trace, bad_raw)


def test_schema6_does_not_retroactively_strengthen_schema5_or_incomplete_runs():
    from logic.search_provenance import (
        SEARCH_TRACE_PROVENANCE_SCHEMA, validate_search_trace_provenance,
    )
    trace, experiment, _ = _verifier_bound_fixture()
    assert "report_artifact_sha256" not in trace
    validate_search_trace_provenance(trace, experiment=experiment)
    trace["search_provenance_schema"] = SEARCH_TRACE_PROVENANCE_SCHEMA
    trace["completed"] = False
    validate_search_trace_provenance(trace, experiment=experiment)


def test_schema6_report_producer_trace_and_reader_are_wired():
    root = Path(__file__).resolve().parents[1]
    agent = (root / "logic/research_agent.py").read_text(encoding="utf-8")
    run = (root / "logic/run.py").read_text(encoding="utf-8")
    runner = (root / "scripts/run_budget_main_study.py").read_text(encoding="utf-8")
    assert "self.report_artifact_sha256 = hashlib.sha256(" in agent
    assert 'trace_payload["report_artifact_sha256"] = getattr(' in run
    assert "validate_report_artifact(trace, raw)" in runner
