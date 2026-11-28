"""Synthetic, offline source-to-CSV reconciliation tests for pilot schema v5."""
import csv
import json
import os

import pytest

from scripts import audit_pilot_cost_summary as price_auditor
from scripts import summarize_pilot as producer
from scripts import validate_pilot_artifacts as validator
from test_pilot_paired_summary_reconciliation import _version4_fixture


def _fixture(tmp_path, monkeypatch):
    summary = _version4_fixture(tmp_path, monkeypatch)
    summary["schema_version"] = 5
    (tmp_path / "pilot_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    monkeypatch.setattr(producer, "TRACE_ROOT", tmp_path / "experiment_traces")
    monkeypatch.setattr(producer, "PRICING_FILE", validator.PILOT_PRICING_FILE)
    monkeypatch.setattr(producer, "OUTPUT_CSV", tmp_path / "pilot_runs.csv")
    rows = producer._load_traces(producer._load_pricing())
    producer._write_csv(rows)
    return summary


def _rows(root):
    with (root / "pilot_runs.csv").open(newline="", encoding="utf-8") as h:
        reader = csv.DictReader(h)
        return reader.fieldnames, list(reader)


def _save_rows(root, fields, rows):
    with (root / "pilot_runs.csv").open("w", newline="", encoding="utf-8") as h:
        writer = csv.DictWriter(h, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _errors(root):
    return " | ".join(validator.validate_pilot(root))


def test_v5_complete_synthetic_csv_passes(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    assert validator.validate_pilot(tmp_path) == []


@pytest.mark.parametrize("field", [
    "variant_id", "task_set_id", "task_id", "run_id", "completed",
    "source_count", "successful_source_count", "failed_source_count",
    "search_call_count", "model_call_count", "prompt_tokens",
    "completion_tokens", "total_tokens", "estimated_cost_usd",
    "cost_accounting_status", "latency_seconds", "report_words",
    "claims_checked", "supported_claim_count",
    "partially_supported_claim_count", "unsupported_claim_count",
    "contradicted_claim_count", "claim_support_rate",
    "usage_accounting_status", "verification_status", "smart_model", "fast_model",
])
def test_v5_rejects_stale_or_falsified_csv_field(tmp_path, monkeypatch, field):
    _fixture(tmp_path, monkeypatch)
    fields, rows = _rows(tmp_path)
    rows[0][field] = "FAKE" if field not in {
        "estimated_cost_usd", "latency_seconds", "claim_support_rate"
    } else "0.987654"
    _save_rows(tmp_path, fields, rows)
    assert "pilot_runs.csv" in _errors(tmp_path)


@pytest.mark.parametrize("mutation", [
    "missing", "duplicate", "extra", "wrong_header", "duplicate_header",
    "missing_column", "extra_column", "wrong_order", "missing_file",
    "symlink", "nan_cost", "malformed_quote",
])
def test_v5_rejects_bad_csv_inventory_and_shape(
    tmp_path, monkeypatch, mutation
):
    _fixture(tmp_path, monkeypatch)
    path = tmp_path / "pilot_runs.csv"
    fields, rows = _rows(tmp_path)
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = dict(rows[0])
    elif mutation == "extra":
        rows.append(dict(rows[0]))
    elif mutation == "wrong_header":
        fields[0] = "treatment"
        rows = [{"treatment": r.pop("variant_id"), **r} for r in rows]
    elif mutation == "duplicate_header":
        fields[1] = fields[0]
    elif mutation == "missing_column":
        fields.pop()
    elif mutation == "extra_column":
        fields.append("unselected")
    elif mutation == "wrong_order":
        fields.reverse()
    elif mutation == "nan_cost":
        rows[0]["estimated_cost_usd"] = "NaN"
    if mutation in ("missing_file", "symlink", "malformed_quote"):
        if mutation == "missing_file":
            path.unlink()
        elif mutation == "symlink":
            path.unlink()
            path.symlink_to(tmp_path / "pilot_summary.json")
        else:
            path.write_text('variant_id,task_id\n"D6,broken', encoding="utf-8")
    else:
        _save_rows(tmp_path, fields, rows)
    assert "pilot_runs.csv" in _errors(tmp_path)


def test_v5_row_reordering_is_not_outcome_selection(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    fields, rows = _rows(tmp_path)
    _save_rows(tmp_path, fields, list(reversed(rows)))
    assert validator.validate_pilot(tmp_path) == []


def test_v4_legacy_did_not_require_csv(tmp_path, monkeypatch):
    _version4_fixture(tmp_path, monkeypatch)
    assert not (tmp_path / "pilot_runs.csv").exists()
    assert validator.validate_pilot(tmp_path) == []


def test_v5_unknown_price_is_exported_as_missing(tmp_path, monkeypatch):
    # The source-to-CSV audit preserves, rather than imputes, missing price.
    from test_pilot_paired_summary_reconciliation import _version3_fixture
    summary = _version3_fixture(tmp_path, monkeypatch, ("P6", "pilot-02"))
    digest = __import__("hashlib").sha256(
        validator.PILOT_PRICING_FILE.read_bytes()
    ).hexdigest()
    monkeypatch.setattr(price_auditor, "FROZEN_PILOT_PRICING_SHA256", digest)
    summary["schema_version"] = 5
    summary["pricing_reference"]["sha256"] = digest
    (tmp_path / "pilot_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    monkeypatch.setattr(producer, "TRACE_ROOT", tmp_path / "experiment_traces")
    monkeypatch.setattr(producer, "PRICING_FILE", validator.PILOT_PRICING_FILE)
    monkeypatch.setattr(producer, "OUTPUT_CSV", tmp_path / "pilot_runs.csv")
    producer._write_csv(producer._load_traces(producer._load_pricing()))
    assert validator.validate_pilot(tmp_path) == []
    fields, rows = _rows(tmp_path)
    row = next(r for r in rows if r["variant_id"] == "P6" and r["task_id"] == "pilot-02")
    assert row["estimated_cost_usd"] == ""
    row["estimated_cost_usd"] = "0"
    _save_rows(tmp_path, fields, rows)
    assert "estimated_cost_usd" in _errors(tmp_path)


def test_v5_rejects_oversized_export_before_csv_parsing(tmp_path, monkeypatch):
    from scripts import audit_pilot_runs_csv as auditor

    _fixture(tmp_path, monkeypatch)
    path = tmp_path / "pilot_runs.csv"
    with path.open("ab") as handle:
        handle.write(b"x" * (auditor.MAX_PILOT_RUNS_CSV_BYTES + 1))
    assert "exceeds bounded capture size" in _errors(tmp_path)


def test_v5_rejects_hardlinked_export(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    path = tmp_path / "pilot_runs.csv"
    os.link(path, tmp_path / "unreviewed-pilot-copy.csv")
    assert "non-aliased regular file" in _errors(tmp_path)


def test_capture_rejects_same_byte_path_replacement(tmp_path, monkeypatch):
    from scripts import audit_pilot_runs_csv as auditor

    path = tmp_path / "pilot_runs.csv"
    replacement = tmp_path / "replacement.csv"
    path.write_bytes(b"header\nrow\n")
    replacement.write_bytes(path.read_bytes())
    original_read = os.read
    replaced = False

    def swap_after_first_read(fd, size):
        nonlocal replaced
        data = original_read(fd, size)
        if data and not replaced:
            os.replace(replacement, path)
            replaced = True
        return data

    monkeypatch.setattr(auditor.os, "read", swap_after_first_read)
    with pytest.raises(ValueError, match="changed during bounded capture"):
        auditor._read_bounded_pilot_csv(path)
    assert replaced


def test_capture_rejects_in_place_growth_during_read(tmp_path, monkeypatch):
    from scripts import audit_pilot_runs_csv as auditor

    path = tmp_path / "pilot_runs.csv"
    path.write_bytes(b"header\nrow\n")
    original_read = os.read
    grew = False

    def grow_after_first_read(fd, size):
        nonlocal grew
        data = original_read(fd, size)
        if data and not grew:
            with path.open("ab") as handle:
                handle.write(b"unreviewed extra data")
            grew = True
        return data

    monkeypatch.setattr(auditor.os, "read", grow_after_first_read)
    with pytest.raises(ValueError, match="changed during bounded capture"):
        auditor._read_bounded_pilot_csv(path)
    assert grew
