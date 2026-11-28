"""Synthetic, outcome-free contracts for the historical 37+3 measurement split."""
from __future__ import annotations

import csv
import hashlib
import io

import pytest

from scripts import audit_historical_evaluator_measurement_partition as audit


def _rows():
    return [
        {
            **{field: "0" for field in audit.FIELDS},
            "variant_id": variant,
            "task_id": task,
            "run_id": f"synthetic-{variant}-{task}",
            "evidence_status": audit.RECOVERED.get((variant, task), ""),
        }
        for variant in audit.VARIANTS for task in audit.TASK_IDS
    ]


def _raw(rows=None, fields=None):
    data = io.StringIO(newline="")
    writer = csv.DictWriter(data, fieldnames=list(fields or audit.FIELDS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(_rows() if rows is None else rows)
    return data.getvalue().encode("utf-8")


def _inspect(raw):
    return audit.inspect_partition(raw, expected_sha256=hashlib.sha256(raw).hexdigest())


def test_frozen_partition_describes_source_declared_nonuniform_measurement():
    receipt = _inspect(_raw())
    assert receipt["cells"] == 40
    assert receipt["source_declared_original_cached_cells"] == 37
    assert receipt["source_declared_evaluator_only_recovered_cells"] == 3
    assert receipt["recovery_cells_by_arm"] == {"D3": 0, "D6": 0, "P6": 0, "P6V": 3}
    assert receipt["recovered_zero_evidence_status_cells"] == ["P6V/main-10"]
    assert receipt["recovered_share_of_p6v_cells"] == "3/10"
    for field in ("original_trace_report_custody_authenticated",
                  "recovered_evaluator_execution_authenticated",
                  "recovered_sentinel_provider_call_authenticated",
                  "bias_direction_or_magnitude_established", "human_validation_performed"):
        assert receipt[field] is False


def test_independent_published_byte_pin_required():
    with pytest.raises(audit.EvaluatorPartitionError, match="pinned bytes"):
        audit.inspect_partition(_raw(), expected_sha256="0" * 64)


@pytest.mark.parametrize("field", ["variant_id", "task_id", "run_id", "evidence_status"])
def test_missing_column_rejected(field):
    cols = [column for column in audit.FIELDS if column != field]
    rows = [{k: v for k, v in row.items() if k != field} for row in _rows()]
    with pytest.raises(audit.EvaluatorPartitionError, match="column contract"):
        _inspect(_raw(rows, fields=cols))


@pytest.mark.parametrize("cell,status", [
    (("P6V", "main-02"), ""),
    (("P6V", "main-08"), "zero_successful_sources"),
    (("P6V", "main-10"), "retrieved_evidence"),
    (("D3", "main-01"), "retrieved_evidence"),
])
def test_false_status_rejected(cell, status):
    rows = _rows()
    next(row for row in rows if (row["variant_id"], row["task_id"]) == cell)["evidence_status"] = status
    with pytest.raises(audit.EvaluatorPartitionError, match="recovery status"):
        _inspect(_raw(rows))


def test_missing_cell_rejected():
    with pytest.raises(audit.EvaluatorPartitionError, match="exactly 40"):
        _inspect(_raw(_rows()[:-1]))


def test_duplicate_cell_rejected():
    rows = _rows()
    rows[-1] = dict(rows[0], run_id="new-run")
    with pytest.raises(audit.EvaluatorPartitionError, match="identity"):
        _inspect(_raw(rows))


def test_duplicate_run_id_rejected():
    rows = _rows()
    rows[-1]["run_id"] = rows[0]["run_id"]
    with pytest.raises(audit.EvaluatorPartitionError, match="identity"):
        _inspect(_raw(rows))


def test_different_task_identity_rejected():
    rows = _rows()
    rows[-1]["task_id"] = "main-11"
    with pytest.raises(audit.EvaluatorPartitionError, match="identity"):
        _inspect(_raw(rows))


def test_extra_column_rejected():
    rows = _rows()
    for row in rows:
        row["unexpected"] = "x"
    with pytest.raises(audit.EvaluatorPartitionError, match="column contract"):
        _inspect(_raw(rows, fields=(*audit.FIELDS, "unexpected")))


def test_invalid_utf8_rejected():
    with pytest.raises(audit.EvaluatorPartitionError, match="encoding"):
        _inspect(_raw() + b"\xff")


def test_missing_record_field_rejected():
    raw = _raw().decode("utf-8")
    lines = raw.splitlines()
    lines[1] = ",".join(lines[1].split(",")[:-1])
    with pytest.raises(audit.EvaluatorPartitionError, match="missing or extra"):
        _inspect(("\n".join(lines) + "\n").encode())
