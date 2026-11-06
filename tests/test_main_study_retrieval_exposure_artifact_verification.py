"""Synthetic and frozen-source regressions for independent exposure receipt replay.

No experiment, evaluator, model, or human-annotation execution occurs.
"""
from __future__ import annotations

import copy
import json
import os

import pytest

from scripts import analyze_main_study_retrieval_exposure as producer
from scripts import audit_frozen_analysis_csv_inputs as audit
from scripts import verify_main_study_retrieval_exposure_artifact as verifier

MAIN = "a" * 64
SUPPORT = "b" * 64
AGGREGATE = "c" * 64


def _rows() -> list[dict[str, str]]:
    rows = []
    for variant in ("D3", "D6", "P6", "P6V"):
        for index in range(1, 11):
            budget = 3 if variant == "D3" else 6
            successful = (index % 2) + (1 if variant == "D3" else 2)
            failed = 1 if variant in ("D3", "D6") else 2
            rows.append({
                "variant_id": variant,
                "task_id": f"synthetic-{index:02d}",
                "completed": "True",
                "source_budget": str(budget),
                "successful_sources": str(successful),
                "failed_sources": str(failed),
                "search_calls": "1" if variant in ("D3", "D6") else "4",
                "model_calls": str(index + 4),
                "total_tokens": str(1000 + index * 17),
            })
    return rows


def _receipt(rows=None):
    summary = producer.summarize_retrieval_exposure(rows or _rows())
    summary["verified_published_treatment_csv_sha256"] = MAIN
    summary["published_evaluator_csv_sha256_reference"] = SUPPORT
    summary["published_input_aggregate_sha256_reference"] = AGGREGATE
    summary["published_summary_preflight_passed"] = True
    return summary


def _verify(rows, summary):
    return verifier.verify_bytes(
        rows,
        json.dumps(summary, allow_nan=False, sort_keys=True).encode("utf-8"),
        main_sha256=MAIN, support_sha256=SUPPORT,
        aggregate_sha256=AGGREGATE,
    )


def test_independent_receipt_recomputation_checks_all_40_cells_and_30_pairs():
    rows = _rows()
    original = copy.deepcopy(rows)
    result = _verify(rows, _receipt(rows))
    assert result["status"] == "verified_post_hoc_exploratory_retrieval_exposure_only"
    assert result["cells_checked"] == 40
    assert result["paired_contrast_rows_checked"] == 30
    assert result["original_execution_authenticated"] is False
    assert result["human_validation_performed"] is False
    assert result["confirmatory_inference_changed"] is False
    assert rows == original


@pytest.mark.parametrize("path,value", [
    (("variant_summaries", "D3", "totals", "successful_sources"), 888),
    (("variant_summaries", "D6", "means_per_report", "total_tokens"), 0.0),
    (("variant_summaries", "P6", "reports_with_capacity_not_accounted_for"), 10),
    (("variant_summaries", "P6V", "all_task_exposures", 0, "failed_sources"), 0),
    (("frozen_contrast_exposure_comparisons", "D6_minus_D3_retrieval_depth",
      "all_task_exposure_differences", 0, "successful_source_delta"), 99),
    (("frozen_contrast_exposure_comparisons", "P6_minus_D6_planning",
      "mean_successful_source_delta"), 111.0),
    (("frozen_contrast_exposure_comparisons", "P6V_minus_P6_verification",
      "equal_successful_sources"), 77),
    (("verified_published_treatment_csv_sha256",), SUPPORT),
    (("published_evaluator_csv_sha256_reference",), MAIN),
    (("published_input_aggregate_sha256_reference",), MAIN),
    (("original_execution_authenticated",), True),
    (("human_validation_performed",), True),
    (("published_summary_preflight_passed",), False),
    (("statistical_tests_added",), True),
    (("status",), "confirmatory"),
    (("interpretation",), "no limitations"),
])
def test_forged_or_incomplete_exploratory_receipts_fail_closed(path, value):
    rows = _rows()
    modified = _receipt(rows)
    target = modified
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(ValueError, match="artifact"):
        _verify(rows, modified)


def test_missing_paired_row_rejected():
    rows = _rows()
    summary = _receipt(rows)
    summary["frozen_contrast_exposure_comparisons"][
        "D6_minus_D3_retrieval_depth"
    ]["all_task_exposure_differences"].pop()
    with pytest.raises(ValueError, match="row count"):
        _verify(rows, summary)


def test_added_or_removed_field_rejected():
    rows = _rows()
    summary = _receipt(rows)
    summary["new_confidence_interval"] = [0.0, 1.0]
    with pytest.raises(ValueError, match="missing/extra"):
        _verify(rows, summary)


def test_numeric_boolean_cannot_impersonate_count():
    rows = _rows()
    summary = _receipt(rows)
    summary["variant_summaries"]["D3"]["n_reports"] = True
    with pytest.raises(ValueError, match="JSON type"):
        _verify(rows, summary)


def test_duplicate_keys_rejected_even_when_values_equal():
    raw = b'{"schema_version":1,"schema_version":1}'
    with pytest.raises(ValueError, match="duplicate"):
        verifier.verify_bytes(_rows(), raw, main_sha256=MAIN,
                              support_sha256=SUPPORT, aggregate_sha256=AGGREGATE)


@pytest.mark.parametrize("raw,match", [
    (b'{"a":NaN}', "numeric constant"),
    (b'{"a":1e999}', "nonfinite"),
    (b'{"a":123456789012345678901}', "integer token"),
    (b'["' + b"t" * (verifier.MAX_ARTIFACT_BYTES + 1) + b'"]', "byte limit"),
    ((b"[" * 40) + b"0" + (b"]" * 40), "nested"),
    (b'{"not_json": ', "UTF-8 JSON"),
])
def test_invalid_or_pathological_json_rejected(raw, match):
    with pytest.raises(ValueError, match=match):
        verifier.verify_bytes(
            _rows(), raw, main_sha256=MAIN, support_sha256=SUPPORT,
            aggregate_sha256=AGGREGATE,
        )


def test_literal_brackets_inside_a_string_are_not_container_depth():
    rows = _rows()
    report = _receipt(rows)
    report["interpretation"] = "[" * 120 + report["interpretation"]
    with pytest.raises(ValueError, match="interpretation"):
        _verify(rows, report)


def test_receipt_file_rejects_symlink_and_hardlink_aliases(tmp_path):
    original = tmp_path / "saved.json"
    original.write_text("{}", encoding="utf-8")
    alias = tmp_path / "shortcut.json"
    alias.symlink_to(original)
    with pytest.raises(OSError):
        verifier._read_artifact(alias)
    hardlink = tmp_path / "hardlink.json"
    os.link(original, hardlink)
    with pytest.raises(ValueError, match="single-link"):
        verifier._read_artifact(original)


def test_receipt_file_rejects_oversize(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b"0" * (verifier.MAX_ARTIFACT_BYTES + 1))
    with pytest.raises(ValueError, match="byte limit"):
        verifier._read_artifact(path)


def test_production_receipt_verifies_against_published_frozen_bytes(tmp_path):
    # Uses immutable Git-retained CSVs, not original model treatment artifacts.
    saved = producer.run_verified()
    output = tmp_path / "retrieval_exposure.json"
    output.write_text(json.dumps(saved, sort_keys=True, indent=2), encoding="utf-8")
    verified = verifier.verify_published(output)
    assert verified["cells_checked"] == 40
    assert verified["paired_contrast_rows_checked"] == 30
    assert verified["verified_published_treatment_csv_sha256"] == (
        audit.FROZEN_MAIN_CSV_SHA256
    )
    assert verified["published_input_aggregate_sha256_reference"] == (
        audit.PUBLISHED_INPUT_AGGREGATE_SHA256
    )
