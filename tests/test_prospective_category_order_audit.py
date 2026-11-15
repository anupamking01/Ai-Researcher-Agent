"""Pre-execution category order diagnostics, all on synthetic proposed tasks."""
from __future__ import annotations

import copy
import hashlib
import json
import sys

import pytest

from scripts import audit_prospective_category_order as audit
from scripts import plan_counterbalanced_replication as design


def _manifest(categories=None):
    if categories is None:
        categories = ["research"] * 10
    return json.dumps({
        "schema_version": 1,
        "task_set_id": "independent-category-order-probe",
        "frozen_before_execution": True,
        "tasks": [
            {
                "id": f"fresh-{index:02d}",
                "category": category,
                "question": f"Independently formulated future question {index}?",
            }
            for index, category in enumerate(categories, 1)
        ],
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _receipt(manifest):
    return json.dumps(
        design.build_plan(manifest), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def test_single_stratum_reconciles_global_williams_margins_without_outcomes():
    manifest = _manifest()
    report = audit.audit_category_order(manifest, _receipt(manifest))
    assert report["classification"] == (
        "prospective_outcome_blind_category_order_diagnostic_only"
    )
    assert report["task_count"] == 10
    assert report["category_count"] == 1
    category = report["category_summaries"][0]
    assert category["category"] == "research"
    assert category["task_count"] == 10
    assert all(sorted(counts) == [2, 2, 3, 3]
               for counts in category["position_counts"].values())
    assert set(category["pairwise_precedence_counts"].values()) == {5}
    assert category["max_position_spread"] == 1
    assert category["max_pairwise_precedence_direction_gap"] == 0
    # Global first-order carryover is 30 transitions among 12 directed pairs:
    # six twice, six three times. This is not proof of actual carryover.
    adjacent = category["directed_adjacent_transition_counts"]
    assert sorted(adjacent.values()) == [2] * 6 + [3] * 6
    assert category["total_directed_adjacent_transitions"] == 30
    assert category["max_directed_adjacent_transition_count_spread"] == 1
    assert adjacent == report["global_directed_adjacent_transition_counts"]
    assert report["global_order_balance_does_not_guarantee_category_balance"] is True
    assert report["category_selection_or_executions_authenticated"] is False
    assert report["historical_2026_study_reanalyzed"] is False
    assert report["human_validation_performed"] is False


def test_multiple_frozen_categories_reconcile_each_position_and_pair():
    manifest = _manifest(["science"] * 3 + ["policy"] * 5 + ["medicine"] * 2)
    expected = design.build_plan(manifest)
    report = audit.audit_category_order(manifest, _receipt(manifest))
    strata = report["category_summaries"]
    assert [row["category"] for row in strata] == [
        "medicine", "policy", "science"
    ]
    assert [row["task_count"] for row in strata] == [2, 5, 3]
    for variant in design.VARIANTS:
        assert [
            sum(row["position_counts"][variant][slot] for row in strata)
            for slot in range(4)
        ] == expected["position_counts"][variant]
    for pair_name, total in expected["pairwise_precedence_counts"].items():
        assert sum(
            row["pairwise_precedence_counts"][pair_name] for row in strata
        ) == total
    # Independent direct scan of the immutable schedule (not the production
    # carryover helper): each pair's category counts must sum to the global
    # occurrence count, even if the category-level balance is poor.
    expected_adjacency = {
        f"{left}_to_{right}": sum(
            a == left and b == right
            for schedule_row in expected["schedule"]
            for a, b in zip(
                schedule_row["arm_order"], schedule_row["arm_order"][1:]
            )
        )
        for left in design.VARIANTS
        for right in design.VARIANTS if left != right
    }
    assert report["global_directed_adjacent_transition_counts"] == expected_adjacency
    for name, count in expected_adjacency.items():
        assert sum(
            row["directed_adjacent_transition_counts"][name] for row in strata
        ) == count
    assert sum(
        row["total_directed_adjacent_transitions"] for row in strata
    ) == 30
    for row in strata:
        n = row["task_count"]
        assert all(sum(values) == n for values in row["position_counts"].values())
        assert row["max_position_spread"] == max(
            max(values) - min(values)
            for values in row["position_counts"].values()
        )
        assert row["max_pairwise_precedence_direction_gap"] == max(
            abs(2 * count - n)
            for count in row["pairwise_precedence_counts"].values()
        )
        adjacent = row["directed_adjacent_transition_counts"]
        assert set(adjacent) == set(expected_adjacency)
        assert row["total_directed_adjacent_transitions"] == 3 * n
        assert row["max_directed_adjacent_transition_count_spread"] == (
            max(adjacent.values()) - min(adjacent.values())
        )


def test_category_order_diagnostic_is_deterministic_and_preserves_plan_receipt():
    manifest = _manifest(["science"] * 5 + ["policy"] * 5)
    receipt = _receipt(manifest)
    assert audit.audit_category_order(manifest, receipt) == (
        audit.audit_category_order(manifest, receipt)
    )
    assert hashlib.sha256(receipt).hexdigest() == (
        audit.audit_category_order(manifest, receipt)["plan_file_sha256"]
    )
    assert _receipt(manifest) == receipt


def test_rejects_modified_mapping_even_with_unchanged_global_margins():
    manifest = _manifest()
    payload = design.build_plan(manifest)
    falsified = copy.deepcopy(payload)
    falsified["schedule"][0]["arm_order"], falsified["schedule"][1]["arm_order"] = (
        falsified["schedule"][1]["arm_order"], falsified["schedule"][0]["arm_order"]
    )
    # Swapping two complete Williams orders preserves global position and
    # precedence counts but must not allow a different category assignment.
    assert falsified["schedule"] != payload["schedule"]
    with pytest.raises(design.DesignError, match="schedule receipt differs"):
        audit.audit_category_order(
            manifest, json.dumps(falsified, sort_keys=True).encode("utf-8")
        )


def test_independent_byte_pins_are_checked_before_category_reporting():
    manifest = _manifest()
    receipt = _receipt(manifest)
    report = audit.audit_category_order(
        manifest, receipt,
        expected_task_manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        expected_plan_file_sha256=hashlib.sha256(receipt).hexdigest(),
    )
    assert report["supplied_task_manifest_pin_matched"] is True
    assert report["supplied_plan_file_pin_matched"] is True
    with pytest.raises(design.DesignError, match="task manifest SHA-256 differs"):
        audit.audit_category_order(
            manifest, receipt, expected_task_manifest_sha256="0" * 64
        )


def test_changed_task_category_invalidates_existing_receipt():
    old = _manifest()
    changed = _manifest(["science"] + ["research"] * 9)
    with pytest.raises(design.DesignError, match="schedule receipt differs"):
        audit.audit_category_order(changed, _receipt(old))


def test_cli_is_read_only_diagnostic_with_no_treatment_execution(
    tmp_path, monkeypatch, capsys
):
    manifest = _manifest(["research"] * 6 + ["policy"] * 4)
    receipt = _receipt(manifest)
    manifest_file = tmp_path / "future.json"
    plan_file = tmp_path / "plan.json"
    manifest_file.write_bytes(manifest)
    plan_file.write_bytes(receipt)
    monkeypatch.setattr(
        sys, "argv",
        ["audit_prospective_category_order.py",
         "--task-manifest", str(manifest_file),
         "--plan-file", str(plan_file)],
    )
    assert audit.main() == 0
    assert json.loads(capsys.readouterr().out) == (
        audit.audit_category_order(manifest, receipt)
    )
    assert {path.name for path in tmp_path.iterdir()} == {
        "future.json", "plan.json"
    }


def test_blocked_frozen_category_order_exposes_task_major_time_concentration():
    # Same category marginals can be clustered in successive task-major
    # positions, even though every Williams treatment order remains fixed.
    labels = ["science"] * 3 + ["policy"] * 5 + ["medicine"] * 2
    manifest = _manifest(labels)
    report = audit.audit_category_order(manifest, _receipt(manifest))
    by_name = {item["category"]: item for item in report["category_summaries"]}
    assert report["task_order_same_category_adjacent_boundaries"] == 7
    assert report["task_order_category_switch_boundaries"] == 2
    assert report["task_order_category_clustering_is_descriptive_only"] is True
    assert {
        name: (entry["first_task_index"], entry["last_task_index"],
               entry["first_half_task_count"], entry["second_half_task_count"],
               entry["longest_consecutive_task_run"],
               entry["adjacent_same_category_task_boundaries"])
        for name, entry in by_name.items()
    } == {
        "science": (1, 3, 3, 0, 3, 2),
        "policy": (4, 8, 2, 3, 5, 4),
        "medicine": (9, 10, 0, 2, 2, 1),
    }


def test_alternating_category_order_has_no_same_category_task_boundaries():
    labels = ["science", "policy"] * 5
    manifest = _manifest(labels)
    report = audit.audit_category_order(manifest, _receipt(manifest))
    by_name = {item["category"]: item for item in report["category_summaries"]}
    assert report["task_order_same_category_adjacent_boundaries"] == 0
    assert report["task_order_category_switch_boundaries"] == 9
    assert [by_name[name]["longest_consecutive_task_run"]
            for name in ("science", "policy")] == [1, 1]
    assert [by_name[name]["first_half_task_count"]
            for name in ("science", "policy")] == [3, 2]
    assert [by_name[name]["second_half_task_count"]
            for name in ("science", "policy")] == [2, 3]
    assert sum(row["adjacent_same_category_task_boundaries"]
               for row in by_name.values()) == 0


def test_task_category_sequence_metric_is_not_only_a_stratum_size_metric():
    blocked = _manifest(["science"] * 5 + ["policy"] * 5)
    alternated = _manifest(["science", "policy"] * 5)
    blocked_report = audit.audit_category_order(blocked, _receipt(blocked))
    alternated_report = audit.audit_category_order(alternated, _receipt(alternated))
    assert [entry["task_count"] for entry in blocked_report["category_summaries"]] == [5, 5]
    assert [entry["task_count"] for entry in alternated_report["category_summaries"]] == [5, 5]
    assert blocked_report["task_order_same_category_adjacent_boundaries"] == 8
    assert alternated_report["task_order_same_category_adjacent_boundaries"] == 0
    assert sum(entry["first_half_task_count"]
               for entry in blocked_report["category_summaries"]) == 5
    assert sum(entry["second_half_task_count"]
               for entry in blocked_report["category_summaries"]) == 5
