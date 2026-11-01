"""Prospective treatment-order design: offline synthetic contract tests only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import plan_counterbalanced_replication as plan


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
