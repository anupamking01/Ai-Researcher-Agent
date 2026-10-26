"""Direct main-study inference must not bypass the frozen CSV scientific preflight.

All fixtures are synthetic; the preserved automated main study is not re-executed.
"""
import csv
import json

import pytest

from scripts import analyze_main_study
from scripts import analyze_main_study_with_preflight as validated
from scripts.validate_main_study_inputs import EXPECTED_CELLS, FROZEN_SOURCE_BUDGETS


def _canonical_fixture():
    treatments = []
    evaluations = []
    for variant, task in sorted(EXPECTED_CELLS):
        treatments.append({
            "variant_id": variant,
            "task_id": task,
            "completed": "True",
            "source_budget": str(FROZEN_SOURCE_BUDGETS[variant]),
            "successful_sources": "3",
            "failed_sources": "0",
            "search_calls": "1",
            "total_tokens": "1200",
            "model_calls": "2",
            "report_words": "500",
            "treatment_cost_usd": "0.04",
            "latency_seconds": "12.5",
            "posthoc_claims_checked": "4",
            "posthoc_strict_support_rate": "0.5",
            "posthoc_evaluator_cost_usd": "0.0125",
            "cost_status": "estimated_from_frozen_uncached_rates",
            "pricing_file": "experiments/openai_pricing_2026-09-08.json",
            "pricing_file_size_bytes": "1090",
            "pricing_file_sha256": "35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace",
            "pricing_unit": "per_1m_text_tokens",
        })
        evaluations.append({
            "variant_id": variant,
            "task_id": task,
            "run_id": f"synthetic-run-{variant}-{task}",
            "claims_checked": "4",
            "supported": "2",
            "partially_supported": "1",
            "unsupported": "1",
            "contradicted": "0",
            "strict_support_rate": "0.5",
            "evidence_status": "",
            "total_tokens": "200",
            "estimated_cost_usd": "0.0125",
        })
    return treatments, evaluations


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def direct_inputs(tmp_path, monkeypatch):
    main_rows, support_rows = _canonical_fixture()
    main_path = tmp_path / "main.csv"
    support_path = tmp_path / "support.csv"
    monkeypatch.setattr(analyze_main_study, "MAIN_CSV", main_path)
    monkeypatch.setattr(analyze_main_study, "SUPPORT_CSV", support_path)
    monkeypatch.setattr(analyze_main_study, "OUT_JSON", tmp_path / "inference.json")
    monkeypatch.setattr(analyze_main_study, "OUT_MD", tmp_path / "inference.md")

    def write():
        _write_csv(main_path, main_rows)
        _write_csv(support_path, support_rows)

    write()
    return main_rows, support_rows, write, main_path, support_path


def test_direct_analyzer_accepts_same_valid_frozen_matrix(direct_inputs):
    _, _, _, _, _ = direct_inputs
    dataset, task_ids = validated.build_dataset()
    assert len(dataset) == 40
    assert task_ids == [f"main-{i:02d}" for i in range(1, 11)]


def test_direct_analyzer_can_render_valid_synthetic_matrix(direct_inputs, monkeypatch):
    monkeypatch.setattr(analyze_main_study, "BOOTSTRAP_DRAWS", 8)
    destination = analyze_main_study.OUT_JSON.parent / "isolated-diagnostic"
    assert validated.main(output_dir=destination) == 0
    output = json.loads((destination / validated.DIAGNOSTIC_JSON).read_text(encoding="utf-8"))
    assert output["n_tasks"] == 10
    assert set(output["variant_summary"]) == {"D3", "D6", "P6", "P6V"}
    assert (destination / validated.DIAGNOSTIC_MD).is_file()
    assert not analyze_main_study.OUT_JSON.exists()
    assert not analyze_main_study.OUT_MD.exists()


@pytest.mark.parametrize(
    "side,field,invalid,message",
    [
        ("main", "source_budget", "9", "frozen source_budget mismatch"),
        ("main", "cost_status", "provider_billed", "treatment cost_status diverges"),
        ("support", "supported", "2.6", "non-integer"),
        ("main", "treatment_cost_usd", "nan", "non-finite"),
        ("main", "pricing_file_sha256", "f" * 64, "frozen pricing_file_sha256 mismatch"),
        ("support", "evidence_status", "zero_successful_sources", "evidence_status contradicts"),
        ("main", "posthoc_evaluator_cost_usd", "0.01", "post-hoc evaluator cost differs"),
    ],
)
def test_direct_analyzer_fails_closed_on_frozen_contract_drift(
    direct_inputs, side, field, invalid, message
):
    main, support, write, _, _ = direct_inputs
    (main if side == "main" else support)[0][field] = invalid
    write()
    with pytest.raises(ValueError, match=message):
        validated.build_dataset()


def test_direct_analyzer_rejects_coherently_relabelled_frozen_task(direct_inputs):
    main, support, write, _, _ = direct_inputs
    # All variants use the same 10 replacement IDs; the earlier analyzer
    # accepted this aligned but non-preregistered task set.
    for rows in (main, support):
        for row in rows:
            if row["task_id"] == "main-10":
                row["task_id"] = "main-99"
    write()
    with pytest.raises(ValueError, match="frozen 4x10 main-study matrix"):
        validated.build_dataset()


def test_direct_analyzer_rejects_ambiguous_duplicate_csv_header(direct_inputs):
    _, _, _, main_path, _ = direct_inputs
    data = main_path.read_text(encoding="utf-8")
    main_path.write_text(data.replace("variant_id,task_id", "variant_id,variant_id,task_id", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate CSV header"):
        validated.build_dataset()


def test_direct_analyzer_rejects_bad_input_before_output_publication(direct_inputs):
    main, _, write, _, _ = direct_inputs
    main[0]["source_budget"] = "99"
    write()
    with pytest.raises(ValueError, match="frozen source_budget mismatch"):
        validated.main(output_dir=analyze_main_study.OUT_JSON.parent / "invalid-diagnostic")
    assert not (analyze_main_study.OUT_JSON.parent / "invalid-diagnostic").exists()
    assert not analyze_main_study.OUT_JSON.exists()
    assert not analyze_main_study.OUT_MD.exists()



def test_diagnostic_requires_explicit_output_destination(direct_inputs):
    with pytest.raises(TypeError, match="output_dir"):
        validated.main()
    assert not analyze_main_study.OUT_JSON.exists()
    assert not analyze_main_study.OUT_MD.exists()


def test_diagnostic_rejects_existing_destination_without_overwrite(direct_inputs):
    directory = analyze_main_study.OUT_JSON.parent / "already-exists"
    directory.mkdir()
    sentinel = directory / validated.DIAGNOSTIC_JSON
    sentinel.write_text("retained", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists"):
        validated.main(output_dir=directory)
    assert sentinel.read_text(encoding="utf-8") == "retained"
    assert not (directory / validated.DIAGNOSTIC_MD).exists()


def test_diagnostic_does_not_modify_preexisting_canonical_outputs(direct_inputs, monkeypatch):
    original_json, original_md = analyze_main_study.OUT_JSON, analyze_main_study.OUT_MD
    original_reader = analyze_main_study._read_csv
    original_json.write_text("frozen-json-sentinel", encoding="utf-8")
    original_md.write_text("frozen-md-sentinel", encoding="utf-8")
    monkeypatch.setattr(analyze_main_study, "BOOTSTRAP_DRAWS", 8)
    directory = original_json.parent / "separate-run"
    assert validated.main(output_dir=directory) == 0
    assert original_json.read_text(encoding="utf-8") == "frozen-json-sentinel"
    assert original_md.read_text(encoding="utf-8") == "frozen-md-sentinel"
    assert analyze_main_study.OUT_JSON == original_json
    assert analyze_main_study.OUT_MD == original_md
    assert analyze_main_study._read_csv is original_reader
    assert (directory / validated.DIAGNOSTIC_JSON).exists()
    assert (directory / validated.DIAGNOSTIC_MD).exists()


def test_failed_rendering_publishes_no_diagnostic_files(direct_inputs, monkeypatch):
    directory = analyze_main_study.OUT_JSON.parent / "failed-render"
    original_json, original_md = analyze_main_study.OUT_JSON, analyze_main_study.OUT_MD
    monkeypatch.setattr(analyze_main_study, "BOOTSTRAP_DRAWS", 8)

    def fail_markdown(_):
        raise RuntimeError("synthetic markdown rendering failure")

    monkeypatch.setattr(analyze_main_study, "_markdown", fail_markdown)
    with pytest.raises(RuntimeError, match="synthetic markdown"):
        validated.main(output_dir=directory)
    assert not directory.exists()
    assert analyze_main_study.OUT_JSON == original_json
    assert analyze_main_study.OUT_MD == original_md


def test_diagnostic_requires_existing_parent_directory(direct_inputs):
    directory = analyze_main_study.OUT_JSON.parent / "no-parent" / "diagnostic"
    with pytest.raises(ValueError, match="parent directory"):
        validated.main(output_dir=directory)
    assert not directory.exists()
