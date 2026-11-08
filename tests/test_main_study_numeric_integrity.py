"""Synthetic numeric-input integrity regressions; no analyzer or treatment reruns."""

import copy
import os

import pytest

from scripts import audit_main_study_numeric_inputs as audit


def _rows():
    main = [{
        "variant_id": "D3", "task_id": "synthetic-only",
        "completed": "true", "source_budget": "3",
        "successful_sources": "1", "failed_sources": "2", "search_calls": "1",
        "model_calls": "2", "total_tokens": "100",
        "treatment_cost_usd": "0.01", "latency_seconds": "3.5",
        "report_words": "120", "posthoc_claims_checked": "4",
        "posthoc_strict_support_rate": "0.5",
        "posthoc_evaluator_cost_usd": "0.004",
    }]
    support = [{
        "variant_id": "D3", "task_id": "synthetic-only",
        "claims_checked": "4", "supported": "2", "partially_supported": "1",
        "unsupported": "1", "contradicted": "0",
        "strict_support_rate": "0.5", "total_tokens": "80",
        "estimated_cost_usd": "0.004",
    }]
    return main, support


def _check(*, main_change=None, support_change=None):
    main, support = copy.deepcopy(_rows())
    if main_change:
        main[0].update(main_change)
    if support_change:
        support[0].update(support_change)
    return audit.audit_rows(
        main, support,
        variants=("D3",), tasks=("synthetic-only",), budgets={"D3": 3},
    )


def test_valid_synthetic_data():
    assert _check()["n_cells"] == 1


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "-0.1", "not-a-number"])
def test_invalid_treatment_measurement_rejected(bad):
    with pytest.raises(audit.NumericInputError, match="numeric|nonfinite|negative"):
        _check(main_change={"treatment_cost_usd": bad})


@pytest.mark.parametrize("bad", ["3.5", "-1", "nan", "inf", "oops"])
def test_nonintegral_or_invalid_claim_counts_rejected(bad):
    with pytest.raises(audit.NumericInputError, match="count|numeric|nonfinite|negative|fractional"):
        _check(support_change={"supported": bad})


def test_overcap_claims_rejected():
    with pytest.raises(audit.NumericInputError, match="outside frozen"):
        _check(support_change={"claims_checked": "13"})


@pytest.mark.parametrize("bad", ["0.25", "1.01", "nan", "-0.1"])
def test_exported_rate_mismatch_rejected(bad):
    with pytest.raises(audit.NumericInputError, match="strict_support_rate"):
        _check(support_change={"strict_support_rate": bad})


def test_treatment_mirrored_claims_mismatch_rejected():
    with pytest.raises(audit.NumericInputError, match="mirrored claims_checked"):
        _check(main_change={"posthoc_claims_checked": "5"})


def test_treatment_mirrored_rate_mismatch_rejected():
    with pytest.raises(audit.NumericInputError, match="posthoc_strict_support_rate"):
        _check(main_change={"posthoc_strict_support_rate": "0.75"})


def test_treatment_mirrored_evaluator_cost_mismatch_rejected():
    with pytest.raises(audit.NumericInputError, match="evaluator-cost"):
        _check(main_change={"posthoc_evaluator_cost_usd": "0.99"})


def test_duplicate_cell_rejected():
    main, support = _rows()
    with pytest.raises(audit.NumericInputError, match="duplicate"):
        audit.audit_rows(
            main + main, support,
            variants=("D3",), tasks=("synthetic-only",), budgets={"D3": 3},
        )


def test_accept_integral_decimal_and_binary_rounding_noise():
    result = _check(support_change={
        "claims_checked": "4.0",
        "supported": "2.0",
        "strict_support_rate": "0.5000000000001",
    })
    assert result["n_cells"] == 1


def test_frozen_csv_inputs_have_internally_consistent_numeric_fields():
    result = audit.audit_files()
    assert result["n_cells"] == 40
    assert result["n_tasks"] == 10
    assert result["status"].endswith("not_original_source_authenticity")
    assert len(result["input_sha256"]) == 2


def _synthetic_csv_path(tmp_path, content=b"variant_id,task_id\nD3,main-01\n"):
    output = tmp_path / "outputs"
    output.mkdir()
    path = output / "main_study_runs.csv"
    path.write_bytes(content)
    return path


def test_csv_capture_reads_exact_synthetic_bytes(tmp_path):
    source = _synthetic_csv_path(tmp_path)
    assert audit._csv_bytes(tmp_path, audit.MAIN_PATH) == source.read_bytes()


def test_csv_capture_rejects_file_symlink(tmp_path):
    destination = _synthetic_csv_path(tmp_path)
    other = tmp_path / "other.csv"
    destination.replace(other)
    destination.symlink_to(other)
    with pytest.raises(audit.NumericInputError, match="redirected|changed"):
        audit._csv_bytes(tmp_path, audit.MAIN_PATH)


def test_csv_capture_rejects_symlinked_parent_directory(tmp_path):
    real = tmp_path / "real_outputs"
    real.mkdir()
    (real / "main_study_runs.csv").write_bytes(b"variant_id,task_id\n")
    (tmp_path / "outputs").symlink_to(real, target_is_directory=True)
    with pytest.raises(audit.NumericInputError, match="redirected|changed"):
        audit._csv_bytes(tmp_path, audit.MAIN_PATH)


def test_csv_capture_rejects_hardlinked_file(tmp_path):
    source = _synthetic_csv_path(tmp_path)
    os.link(source, tmp_path / "alias.csv")
    with pytest.raises(audit.NumericInputError, match="single-linked"):
        audit._csv_bytes(tmp_path, audit.MAIN_PATH)


def test_csv_capture_rejects_oversize_sparse_file_without_reading(tmp_path):
    source = _synthetic_csv_path(tmp_path)
    with source.open("wb") as handle:
        handle.truncate(audit.MAX_CSV_BYTES + 1)
    with pytest.raises(audit.NumericInputError, match="exceeds 2 MiB"):
        audit._csv_bytes(tmp_path, audit.MAIN_PATH)


def test_csv_capture_detects_pathname_replacement_during_read(tmp_path, monkeypatch):
    source = _synthetic_csv_path(tmp_path)
    original_pread = os.pread
    swapped = False

    def replace_during_read(fd, count, offset):
        nonlocal swapped
        if not swapped:
            swapped = True
            source.rename(tmp_path / "old.csv")
            source.write_bytes(b"variant_id,task_id\nP6,main-01\n")
        return original_pread(fd, count, offset)

    monkeypatch.setattr(audit.os, "pread", replace_during_read)
    with pytest.raises(audit.NumericInputError, match="changed"):
        audit._csv_bytes(tmp_path, audit.MAIN_PATH)


def test_csv_capture_detects_in_place_edit_during_read(tmp_path, monkeypatch):
    source = _synthetic_csv_path(tmp_path)
    original_pread = os.pread
    mutated = False

    def mutate_during_read(fd, count, offset):
        nonlocal mutated
        chunk = original_pread(fd, count, offset)
        if not mutated:
            mutated = True
            with source.open("r+b") as handle:
                handle.seek(0)
                handle.write(b"X")
        return chunk

    monkeypatch.setattr(audit.os, "pread", mutate_during_read)
    with pytest.raises(audit.NumericInputError, match="changed"):
        audit._csv_bytes(tmp_path, audit.MAIN_PATH)


def test_numeric_receipt_rechecks_captured_csv_after_parsing(tmp_path, monkeypatch):
    main = _synthetic_csv_path(tmp_path)
    (tmp_path / audit.SUPPORT_PATH).write_bytes(
        b"variant_id,task_id\nD3,main-01\n"
    )

    def synthetic_validator(main_rows, support_rows):
        assert main_rows[0]["variant_id"] == "D3"
        main.write_bytes(b"variant_id,task_id\nP6,main-01\n")
        return {"status": "synthetic_only"}

    monkeypatch.setattr(audit, "audit_rows", synthetic_validator)
    with pytest.raises(audit.NumericInputError, match="changed before audit receipt"):
        audit.audit_files(tmp_path)
