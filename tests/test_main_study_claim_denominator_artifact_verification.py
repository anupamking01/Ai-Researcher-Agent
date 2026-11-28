"""Synthetic regression tests and one frozen-CSV replay smoke test."""
from __future__ import annotations

import copy
import json
import os

import pytest

from scripts import analyze_main_study_claim_denominators as producer
from scripts import audit_frozen_analysis_csv_inputs as audit
from scripts import verify_main_study_claim_denominator_artifact as verifier

HASHES = dict(support_sha256="a"*64, main_sha256="b"*64, aggregate_sha256="c"*64)


def _rows():
    rows = []
    for arm in ("D3", "D6", "P6", "P6V"):
        for i in range(1, 11):
            checked = i % 5 + (4 if arm in ("D6", "P6V") else 3)
            supported = checked - i % 3
            rows.append({
                "variant_id": arm,
                "task_id": f"synthetic-{i:02d}",
                "claims_checked": str(checked), "supported": str(supported),
                "partially_supported": "0",
                "unsupported": str(checked - supported),
                "contradicted": "0",
                "strict_support_rate": str(supported / checked),
            })
    return rows


def _report(rows):
    report = producer.summarize_claim_denominators(rows)
    report.update(
        verified_published_evaluator_csv_sha256=HASHES["support_sha256"],
        published_treatment_csv_sha256_reference=HASHES["main_sha256"],
        published_input_aggregate_sha256_reference=HASHES["aggregate_sha256"],
        published_summary_preflight_passed=True,
    )
    return report


def _verify(rows, report):
    return verifier.verify_bytes(
        rows, json.dumps(report, sort_keys=True, allow_nan=False).encode(),
        **HASHES,
    )


def test_independent_replay_accepts_40_cells_and_30_task_pairs():
    rows = _rows()
    original = copy.deepcopy(rows)
    receipt = _verify(rows, _report(rows))
    assert receipt["cells_checked"] == 40
    assert receipt["paired_contrast_rows_checked"] == 30
    assert not receipt["human_validation_performed"]
    assert not receipt["original_execution_authenticated"]
    assert rows == original


@pytest.mark.parametrize("path,value", [
    (("variant_summaries", "D3", "total_claims_checked"), 999),
    (("variant_summaries", "P6", "total_claims_supported"), 999),
    (("variant_summaries", "D6", "claims_checked_histogram_1_to_12", "5"), 20),
    (("variant_summaries", "P6V", "task_claim_counts", 0, "claims_checked"), 12),
    (("variant_summaries", "D3", "equal_report_macro_strict_support"), 0.5),
    (("variant_summaries", "D6", "claim_pooled_micro_strict_support"), 0.5),
    (("variant_summaries", "P6", "micro_minus_macro_strict_support"), 0.5),
    (("frozen_contrast_denominator_comparisons", "D6_minus_D3_retrieval_depth",
      "all_task_claim_count_differences", 0, "right_minus_left_claims_checked"), 42),
    (("frozen_contrast_denominator_comparisons", "P6_minus_D6_planning",
      "mean_difference_claims_checked"), 42.0),
    (("frozen_contrast_denominator_comparisons", "P6V_minus_P6_verification",
      "tasks_with_equal_claims"), 42),
    (("verified_published_evaluator_csv_sha256",), "b"*64),
    (("published_treatment_csv_sha256_reference",), "a"*64),
    (("published_input_aggregate_sha256_reference",), "a"*64),
    (("status",), "confirmatory"),
    (("published_summary_preflight_passed",), False),
    (("p_values_or_confidence_intervals_added",), True),
    (("confirmatory_primary_estimand_changed",), True),
    (("human_validation_performed",), True),
    (("original_execution_authenticated",), True),
    (("interpretation",), "all reports complete"),
])
def test_tampering_including_renamed_provenance_is_rejected(path, value):
    rows = _rows()
    altered = _report(rows)
    target = altered
    for element in path[:-1]:
        target = target[element]
    target[path[-1]] = value
    with pytest.raises(ValueError, match="denominator artifact"):
        _verify(rows, altered)


def test_removed_paired_row_and_extra_inferential_field_fail_closed():
    rows = _rows()
    altered = _report(rows)
    altered["frozen_contrast_denominator_comparisons"][
        "D6_minus_D3_retrieval_depth"
    ]["all_task_claim_count_differences"].pop()
    with pytest.raises(ValueError, match="row count"):
        _verify(rows, altered)
    altered = _report(rows)
    altered["new_p_value"] = 0.01
    with pytest.raises(ValueError, match="fields differ"):
        _verify(rows, altered)


def test_boolean_cannot_replace_integer():
    rows = _rows()
    altered = _report(rows)
    altered["variant_summaries"]["D3"]["n_reports"] = True
    with pytest.raises(ValueError, match="JSON type"):
        _verify(rows, altered)


@pytest.mark.parametrize("raw,problem", [
    (b'{"x":NaN}', "numeric constant"),
    (b'{"x":1e999}', "nonfinite"),
    (b'{"x":123456789012345678901}', "integer token"),
    (b'{"x":1,"x":1}', "duplicate"),
    (b"[" * 40 + b"1" + b"]" * 40, "nested"),
    (b'{"x":', "UTF-8 JSON"),
    (b" " * (verifier.MAX_ARTIFACT_BYTES + 1), "byte limit"),
])
def test_invalid_json_or_resource_abuse_rejected(raw, problem):
    with pytest.raises(ValueError, match=problem):
        verifier.verify_bytes(_rows(), raw, **HASHES)


def test_claim_partition_or_score_inconsistency_rejected():
    rows = _rows()
    saved = _report(rows)
    rows[0]["supported"] = "99"
    with pytest.raises(ValueError, match="partition"):
        _verify(rows, saved)
    rows = _rows()
    saved = _report(rows)
    rows[0]["strict_support_rate"] = "0.99"
    with pytest.raises(ValueError, match="contradicts counts"):
        _verify(rows, saved)


def test_saved_json_descriptor_capture_rejects_aliases(tmp_path):
    original = tmp_path / "report.json"
    original.write_text("{}", encoding="utf-8")
    link = tmp_path / "alias.json"
    link.symlink_to(original)
    with pytest.raises(ValueError):
        audit._capture_csv_bytes(link, label="saved denominator JSON")
    hardlink = tmp_path / "hard.json"
    os.link(original, hardlink)
    with pytest.raises(ValueError, match="exactly one link"):
        audit._capture_csv_bytes(original, label="saved denominator JSON")


def test_production_replay_accepts_original_published_frozen_data(tmp_path):
    published = producer.run_verified()
    saved = tmp_path / "denominators.json"
    saved.write_text(json.dumps(published, indent=2, sort_keys=True), encoding="utf-8")
    receipt = verifier.verify_published(saved)
    assert receipt["cells_checked"] == 40
    assert receipt["paired_contrast_rows_checked"] == 30
    assert receipt["verified_published_evaluator_csv_sha256"] == (
        audit.FROZEN_SUPPORT_CSV_SHA256
    )
    assert receipt["published_input_aggregate_sha256_reference"] == (
        audit.PUBLISHED_INPUT_AGGREGATE_SHA256
    )
