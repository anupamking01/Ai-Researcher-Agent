"""Pilot-only source-selection integrity; all rows here are synthetic unless noted."""
import csv
from pathlib import Path

import pytest

from scripts import summarize_pilot as pilot


def row(variant, task, *, run_id=None, study="pilot-v1-test"):
    return {
        "variant_id": variant,
        "task_set_id": study,
        "task_id": task,
        "run_id": run_id or f"{variant}-{task}",
        "total_tokens": 10,
        "estimated_cost_usd": 0.01,
        "latency_seconds": 2.0,
        "model_call_count": 1,
        "successful_source_count": 1,
    }


def test_pilot_pairing_is_task_keyed_and_deterministic():
    rows = [
        row("P6", "task-02"), row("D6", "task-01"),
        row("P6", "task-01"), row("D6", "task-02"),
    ]
    rows[0]["total_tokens"] = 30
    rows[2]["total_tokens"] = 20
    result = pilot._paired_operational_differences(rows)["P6_minus_D6"]
    assert result["n_pairs"] == result["n_tasks_union"] == 2
    assert result["missing_left_task_ids"] == []
    assert result["missing_right_task_ids"] == []
    assert [pair["task_id"] for pair in result["pairs"]] == ["task-01", "task-02"]
    assert [pair["total_tokens_delta"] for pair in result["pairs"]] == [10, 20]


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([row("D6", "task-01"), row("D6", "task-01", run_id="retry")], "duplicate pilot treatment/task cell"),
        ([row("D6", "task-01"), row("P6", "task-01", run_id="D6-task-01")], "reused pilot run_id"),
        ([row("D6", "task-01"), row("P6", "task-01", study="another-study")], "mixed pilot task_set_id"),
        ([row("D3", "task-01")], "unexpected variant"),
        ([row("D6", "task-01", study="")], "invalid task_set_id"),
        ([row("D6", "task-01", run_id="  padded  ")], "invalid run_id"),
        ([row("D6", "")], "invalid task_id"),
        ([None], "not a record"),
    ],
)
def test_ambiguous_pilot_selection_rejected(rows, message):
    with pytest.raises(ValueError, match=message):
        pilot._paired_operational_differences(rows)


def test_missing_pilot_pair_is_explicitly_accounted_without_imputation():
    rows = [row("D6", "task-01"), row("P6", "task-02")]
    result = pilot._paired_operational_differences(rows)["P6_minus_D6"]
    assert result["n_tasks_union"] == 2
    assert result["n_pairs"] == 0
    assert result["missing_left_task_ids"] == ["task-02"]
    assert result["missing_right_task_ids"] == ["task-01"]
    assert result["avg_total_tokens_delta"] is None


def test_main_rejects_ambiguous_inputs_before_creating_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "_load_traces", lambda pricing, *, source_snapshot=None: [
        row("D6", "task-01"),
        row("D6", "task-01", run_id="retry"),
    ])
    monkeypatch.setattr(pilot, "PRICING_FILE", tmp_path / "pricing.json")
    pinned = Path(__file__).resolve().parents[1] / "experiments" / "openai_pricing_2026-09-08.json"
    pilot.PRICING_FILE.write_bytes(pinned.read_bytes())
    monkeypatch.setattr(pilot, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pilot, "OUTPUT_JSON", tmp_path / "pilot_summary.json")
    monkeypatch.setattr(pilot, "OUTPUT_CSV", tmp_path / "pilot_runs.csv")
    with pytest.raises(ValueError, match="duplicate pilot treatment/task cell"):
        pilot.main()
    assert not pilot.OUTPUT_JSON.exists()
    assert not pilot.OUTPUT_CSV.exists()


@pytest.mark.parametrize("content", ["not-json", "{}", '{"trace": [], "experiment": {}}'])
def test_loader_rejects_malformed_pilot_traces_instead_of_skipping(tmp_path, monkeypatch, content):
    trace_root = tmp_path / "traces"
    folder = trace_root / "D6"
    folder.mkdir(parents=True)
    (folder / "candidate.json").write_text(content, encoding="utf-8")
    monkeypatch.setattr(pilot, "TRACE_ROOT", trace_root)
    with pytest.raises(ValueError, match="(malformed pilot trace|invalid pilot trace structure)"):
        pilot._load_traces({"models": {}})


def test_loader_rejects_declared_variant_path_mismatch(tmp_path, monkeypatch):
    import json
    trace_root = tmp_path / "traces"
    folder = trace_root / "D6"
    folder.mkdir(parents=True)
    (folder / "candidate.json").write_text(
        json.dumps({"trace": {"variant_id": "P6"}, "experiment": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pilot, "TRACE_ROOT", trace_root)
    with pytest.raises(ValueError, match="variant disagrees with directory"):
        pilot._load_traces({"models": {}})


def test_original_frozen_pilot_selected_rows_satisfy_uniqueness_contract():
    # Read-only structural regression against the Git-preserved diagnostic pilot.
    # This neither reruns nor reselects the historical treatment runs.
    source = Path(__file__).resolve().parents[1] / "experiments/results/pilot_v1_canonical_runs.csv"
    with source.open(encoding="utf-8", newline="") as handle:
        canonical = list(csv.DictReader(handle))
    matrix = pilot._index_pilot_rows(canonical)
    assert len(matrix) == len(canonical) == 15
    assert {task for _, task in matrix} == {f"pilot-{i:02d}" for i in range(1, 6)}
