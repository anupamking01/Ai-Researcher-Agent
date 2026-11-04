"""Prospective treatment-order design: offline synthetic contract tests only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import plan_counterbalanced_replication as plan
from scripts import verify_frozen_main_study_tasks as original_tasks


def _payload():
    return {
        "schema_version": 1,
        "task_set_id": "independent-task-set-v2",
        "frozen_before_execution": True,
        "tasks": [
            {"id": f"fresh-{index:02d}", "category": "research",
             "question": f"New independently selected question {index}?"}
            for index in range(1, 11)
        ],
    }


def _raw(payload=None):
    if payload is None:
        payload = _payload()
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")



def _frozen_2026_questions():
    path = original_tasks.ROOT / original_tasks.TASK_MANIFEST_REL
    raw = path.read_bytes()
    # A change to the supposed original manifest must fail rather than
    # silently teach the new-study guard a revised set of historical prompts.
    assert hashlib.sha256(raw).hexdigest() == (
        original_tasks.ORIGINAL_TASK_MANIFEST_SHA256
    )
    payload = json.loads(raw)
    assert payload["task_set_id"] == plan.ORIGINAL_TASK_SET_ID
    assert len(payload["tasks"]) == 10
    return payload["tasks"]


def test_historical_prompt_fingerprints_match_byte_pinned_original_source():
    original = _frozen_2026_questions()
    assert {row["id"] for row in original} == plan.ORIGINAL_2026_TASK_IDS
    assert {
        plan._normalized_question_sha256(row["question"]) for row in original
    } == plan.ORIGINAL_2026_QUESTION_SHA256
    assert len(plan.ORIGINAL_2026_QUESTION_SHA256) == 10


@pytest.mark.parametrize("original_index", range(10))
def test_reusing_historical_question_with_new_task_identity_is_rejected(original_index):
    candidate = _payload()
    old_question = _frozen_2026_questions()[original_index]["question"]
    candidate["tasks"][original_index]["question"] = old_question
    # The prospective identifier and freeze flag are otherwise valid.
    with pytest.raises(plan.DesignError, match="repeats a frozen 2026"):
        plan.build_plan(_raw(candidate))


@pytest.mark.parametrize("rewriter", [
    lambda text: (" " + chr(10) + chr(9)).join(text.upper().split()),
    lambda text: text.replace("For", "Ｆｏｒ", 1),
])
def test_whitespace_case_and_nfkc_variants_of_original_question_are_blocked(rewriter):
    candidate = _payload()
    candidate["tasks"][0]["question"] = rewriter(
        _frozen_2026_questions()[0]["question"]
    )
    with pytest.raises(plan.DesignError, match="repeats a frozen 2026"):
        plan.build_plan(_raw(candidate))


@pytest.mark.parametrize("rewrite", [
    # Distinct IDs and byte strings must not masquerade as ten independent tasks.
    lambda text: " \t\n ".join(text.upper().split()),
    lambda text: text.replace("New", "Ｎｅｗ", 1),
])
def test_within_new_manifest_normalized_duplicate_question_is_rejected(rewrite):
    candidate = _payload()
    candidate["tasks"][1]["question"] = rewrite(candidate["tasks"][0]["question"])
    assert candidate["tasks"][1]["question"] != candidate["tasks"][0]["question"]
    with pytest.raises(plan.DesignError, match="normalized-equivalent questions"):
        plan.build_plan(_raw(candidate))


def test_within_new_manifest_unicode_casefold_equivalence_is_rejected():
    candidate = _payload()
    candidate["tasks"][0]["question"] = "Is the Straße closed?"
    candidate["tasks"][1]["question"] = "IS THE STRASSE CLOSED?"
    with pytest.raises(plan.DesignError, match="normalized-equivalent questions"):
        plan.build_plan(_raw(candidate))


def test_reusing_original_task_id_with_new_question_is_rejected():
    candidate = _payload()
    candidate["tasks"][0]["id"] = "main-01"
    with pytest.raises(plan.DesignError, match="reserved 2026"):
        plan.build_plan(_raw(candidate))


def test_schedule_balances_every_position_and_every_pair_without_outcomes():
    result = plan.build_plan(_raw())
    assert result["classification"] == "prospective_design_only_no_executions"
    assert result["task_set_id"] == "independent-task-set-v2"
    assert result["task_count"] == 10
    assert result["treatment_cells_planned"] == 40
    assert [row["task_id"] for row in result["schedule"]] == [
        item["id"] for item in _payload()["tasks"]
    ]
    assert all(len(row["arm_order"]) == 4 and
               set(row["arm_order"]) == set(plan.VARIANTS)
               for row in result["schedule"])
    for counts in result["position_counts"].values():
        assert sorted(counts) == [2, 2, 3, 3]
    assert len(result["pairwise_precedence_counts"]) == 6
    assert set(result["pairwise_precedence_counts"].values()) == {5}
    assert result["historical_2026_study_replaced"] is False
    assert result["historical_design_causal_limitation_resolved"] is False
    assert result["independent_replication_or_human_validation_performed"] is False


def test_future_williams_schedule_balances_directed_first_order_carryover():
    # 10 rows x 3 neighbors = 30 transitions over 12 directed pairs.
    schedule = plan.build_plan(_raw())["schedule"]
    observed = plan._directed_carryover_counts(schedule)
    assert len(observed) == 12
    assert sum(observed.values()) == 30
    assert sorted(observed.values()) == [2] * 6 + [3] * 6
    plan._require_carryover_balance(schedule)


def test_precedence_and_position_balance_do_not_guarantee_carryover():
    # Five reversed pairs force perfect 5:5 precedence. This explicit
    # counterexample also has 2/3 positional balance, yet some neighboring
    # directed transitions occur only once and others five times.
    seeds = (
        ("P6", "D6", "D3", "P6V"),
        ("P6V", "D3", "P6", "D6"),
        ("D3", "P6V", "D6", "P6"),
        ("D6", "P6", "P6V", "D3"),
        ("P6", "D3", "P6V", "D6"),
    )
    orders = [order for seed in seeds for order in (seed, seed[::-1])]
    schedule = [
        {"task_id": f"fresh-{index:02d}", "arm_order": list(order)}
        for index, order in enumerate(orders, start=1)
    ]
    assert len(schedule) == 10
    for variant in plan.VARIANTS:
        assert sorted(
            sum(row["arm_order"][position] == variant for row in schedule)
            for position in range(4)
        ) == [2, 2, 3, 3]
    for index, before in enumerate(plan.VARIANTS):
        for after in plan.VARIANTS[index + 1:]:
            assert sum(
                row["arm_order"].index(before) < row["arm_order"].index(after)
                for row in schedule
            ) == 5
    counts = plan._directed_carryover_counts(schedule)
    assert sorted(counts.values()) == [1] * 4 + [2] * 4 + [4] * 2 + [5] * 2
    with pytest.raises(plan.DesignError, match="first-order carryover"):
        plan._require_carryover_balance(schedule)


def test_design_receipt_and_order_are_byte_deterministic():
    source = _raw()
    first = plan.build_plan(source)
    second = plan.build_plan(source)
    assert first == second
    assert first["source_manifest_sha256"] == hashlib.sha256(source).hexdigest()
    receipt = first.copy()
    digest = receipt.pop("design_receipt_sha256")
    assert digest == hashlib.sha256(json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()




def test_semantically_identical_json_formatting_does_not_select_a_new_order():
    compact = _raw()
    pretty = (json.dumps(_payload(), indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    a, b = plan.build_plan(compact), plan.build_plan(pretty)
    assert a["source_manifest_sha256"] != b["source_manifest_sha256"]
    assert a["semantic_task_manifest_sha256"] == b["semantic_task_manifest_sha256"]
    assert a["schedule"] == b["schedule"]
    assert a["pairwise_precedence_counts"] == b["pairwise_precedence_counts"]
    assert a["design_receipt_sha256"] != b["design_receipt_sha256"]

def test_source_byte_change_changes_provenance_even_without_outcome_measurements():
    initial = _payload()
    edited = _payload()
    edited["tasks"][0]["question"] = "A separate new independently selected question?"
    assert plan.build_plan(_raw(initial))["source_manifest_sha256"] != (
        plan.build_plan(_raw(edited))["source_manifest_sha256"]
    )


@pytest.mark.parametrize("mutate,pattern", [
    (lambda x: x.update(task_set_id=plan.ORIGINAL_TASK_SET_ID), "NEW task_set_id"),
    (lambda x: x.update(frozen_before_execution=False), "frozen_before_execution"),
    (lambda x: x.update(tasks=x["tasks"][:-1]), "exactly 10"),
    (lambda x: x["tasks"][1].update(id=x["tasks"][0]["id"]), "duplicate"),
    (lambda x: x["tasks"][1].update(question=x["tasks"][0]["question"]), "duplicate"),
    (lambda x: x["tasks"][0].update(category="  "), "no category"),
    (lambda x: x["tasks"][0].update(id="../unsafe"), "unsafe identifier"),
    (lambda x: x.update(observed_results={"D3": 1}), "design-only schema"),
    (lambda x: x["tasks"][0].update(strict_support_rate=0.9), "id/category/question"),
    (lambda x: x.update(schema_version=True), "design-only schema"),
])
def test_bad_or_outcome_bearing_new_manifest_fails_closed(mutate, pattern):
    candidate = _payload()
    mutate(candidate)
    with pytest.raises(plan.DesignError, match=pattern):
        plan.build_plan(_raw(candidate))


@pytest.mark.parametrize("data,pattern", [
    (b'{"schema_version":1,"schema_version":1}', "duplicate"),
    (b'{"schema_version":NaN}', "nonstandard"),
    (b'{"schema_version":1e999}', "not finite"),
    (b'not json', "UTF-8 JSON"),
    (b'', "outside supported range"),
    (b'[]', "JSON object"),
])
def test_ambiguous_or_invalid_json_rejected(data, pattern):
    with pytest.raises(plan.DesignError, match=pattern):
        plan.build_plan(data)


def test_manifest_read_is_byte_exact_and_bounded(tmp_path):
    source = _raw()
    file = tmp_path / "new_tasks.json"
    file.write_bytes(source)
    assert plan.read_manifest(file) == source
    file.write_bytes(b"x" * (plan.MAX_MANIFEST_BYTES + 1))
    with pytest.raises(plan.DesignError, match="bounded regular"):
        plan.read_manifest(file)


def test_manifest_read_rejects_symlink_and_nonregular_source(tmp_path):
    file = tmp_path / "new_tasks.json"
    file.write_bytes(_raw())
    linked = tmp_path / "link.json"
    linked.symlink_to(file)
    with pytest.raises(plan.DesignError, match="non-symlink"):
        plan.read_manifest(linked)
    with pytest.raises(plan.DesignError, match="non-symlink"):
        plan.read_manifest(tmp_path)


def test_manifest_read_accepts_ordinary_nested_directory(tmp_path):
    directory = tmp_path / "a" / "b"
    directory.mkdir(parents=True)
    source = directory / "tasks.json"
    source.write_bytes(_raw())
    assert plan.read_manifest(source) == _raw()


def test_manifest_read_rejects_symlinked_parent_and_ancestor(tmp_path):
    real = tmp_path / "real"
    nested = real / "nested"
    nested.mkdir(parents=True)
    source = nested / "tasks.json"
    source.write_bytes(_raw())
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    # The real bytes are valid, but the submitted pathname passes through
    # a redirect; a later handoff could resolve to a different task set.
    with pytest.raises(plan.DesignError, match="symlinked parent"):
        plan.read_manifest(alias / "nested" / source.name)
    nested_alias = real / "nested_alias"
    nested_alias.symlink_to(nested, target_is_directory=True)
    with pytest.raises(plan.DesignError, match="symlinked parent"):
        plan.read_manifest(nested_alias / source.name)


def test_manifest_read_detects_parent_directory_swap_during_capture(
    tmp_path, monkeypatch,
):
    original = tmp_path / "source"
    replacement = tmp_path / "replacement"
    original.mkdir()
    replacement.mkdir()
    source = original / "tasks.json"
    source.write_bytes(_raw())
    (replacement / source.name).write_bytes(_raw())
    original_read = plan.os.read
    replaced = False

    def swap_on_read(fd, amount):
        nonlocal replaced
        if not replaced:
            original.rename(tmp_path / "old_source")
            replacement.rename(original)
            replaced = True
        return original_read(fd, amount)

    monkeypatch.setattr(plan.os, "read", swap_on_read)
    with pytest.raises(plan.DesignError, match="parent directory changed during capture"):
        plan.read_manifest(source)
    assert replaced


def test_cli_is_offline_print_only_without_automatic_treatment_execution(
    tmp_path, capsys, monkeypatch
):
    file = tmp_path / "future_manifest.json"
    file.write_bytes(_raw())
    monkeypatch.setattr(
        plan, "__name__", "scripts.plan_counterbalanced_replication"
    )
    monkeypatch.setattr(
        "sys.argv",
        ["plan_counterbalanced_replication.py", "--task-manifest", str(file)],
    )
    assert plan.main() == 0
    published = json.loads(capsys.readouterr().out)
    assert published == plan.build_plan(_raw())
    assert list(tmp_path.iterdir()) == [file]

@pytest.mark.parametrize(
    ("character_name", "character"),
    [
        ("zero_width_space", "\u200b"),
        ("zero_width_joiner", "\u200d"),
        ("word_joiner", "\u2060"),
        ("byte_order_mark", "\ufeff"),
        ("bidi_override", "\u202e"),
        ("bidi_isolate", "\u2066"),
        ("combining_grapheme_joiner", "\u034f"),
        ("variation_selector", "\ufe0f"),
        ("supplementary_variation_selector", "\U000e0100"),
        ("mongolian_variation_selector", "\u180b"),
        ("nul", "\x00"),
        ("escape", "\x1b"),
        ("c1_control", "\u0085"),
        ("backspace", "\x08"),
        ("delete", "\x7f"),
    ],
)
@pytest.mark.parametrize("field", ("question", "category"))
def test_future_task_manifest_rejects_hidden_unicode_controls(
    character_name, character, field
):
    candidate = _payload()
    candidate["tasks"][0][field] += character
    with pytest.raises(plan.DesignError, match=rf"task 1 {field} contains invisible/control Unicode"):
        plan.build_plan(_raw(candidate))



@pytest.mark.parametrize("surrogate", ("\ud800", "\udfff"))
@pytest.mark.parametrize("field", ("question", "category"))
def test_lone_json_surrogate_escape_fails_closed_before_prospective_hash(
    field, surrogate
):
    # json.dumps emits a syntactically legal ASCII \u escape; json.loads
    # reconstructs a non-scalar surrogate that UTF-8 cannot encode.
    # Report a design error, never a hashing/assignment traceback.
    candidate = _payload()
    candidate["tasks"][0][field] += surrogate
    raw = _raw(candidate)
    assert b"\\ud" in raw
    with pytest.raises(
        plan.DesignError,
        match=rf"task 1 {field} contains invisible/control Unicode",
    ):
        plan.build_plan(raw)


def test_independent_prospective_receipt_verifier_rejects_lone_surrogate():
    from scripts import verify_counterbalanced_replication_plan as verifier

    original = _raw()
    receipt = json.dumps(plan.build_plan(original), sort_keys=True).encode("utf-8")
    altered = _payload()
    altered["tasks"][0]["question"] += "\udc00"
    with pytest.raises(plan.DesignError, match="question contains invisible/control Unicode"):
        verifier.verify_plan(_raw(altered), receipt)


def test_json_escaped_valid_surrogate_pair_remains_supported():
    from scripts import verify_counterbalanced_replication_plan as verifier

    candidate = _payload()
    candidate["tasks"][0]["question"] += " \U0001f680"
    candidate["tasks"][0]["category"] += " \U0001f680"
    raw = _raw(candidate)
    assert b"\\ud83d\\ude80" in raw
    receipt = json.dumps(plan.build_plan(raw), sort_keys=True).encode("utf-8")
    assert verifier.verify_plan(raw, receipt)


def test_hidden_historical_question_reuse_cannot_enter_prospective_plan():
    candidate = _payload()
    original = _frozen_2026_questions()[0]["question"]
    candidate["tasks"][0]["question"] = original[:12] + "\u200b" + original[12:]
    with pytest.raises(plan.DesignError, match="task 1 question contains invisible/control Unicode"):
        plan.build_plan(_raw(candidate))


def test_independent_plan_verification_rejects_invisible_manifest_revision():
    from scripts import verify_counterbalanced_replication_plan as verifier

    original = _raw()
    receipt = json.dumps(plan.build_plan(original), sort_keys=True).encode("utf-8")
    revised = _payload()
    revised["tasks"][0]["category"] += "\u2060"
    with pytest.raises(plan.DesignError, match="task 1 category contains invisible/control Unicode"):
        verifier.verify_plan(_raw(revised), receipt)


def test_legitimate_multilingual_accents_and_linebreaks_remain_supported():
    candidate = _payload()
    candidate["tasks"][0]["category"] = "étude"
    candidate["tasks"][0]["question"] = "What does the e\u0301vidence show?\nCompare both approaches."
    candidate["tasks"][1]["question"] = "What does the evidence show?\nCompare both approaches."
    # Meaningful accent distinctions are not silently erased or recoded.
    result = plan.build_plan(_raw(candidate))
    assert result["task_count"] == 10
    assert result["classification"] == "prospective_design_only_no_executions"

