"""Synthetic-only tests for historical chronology auditing; no outcome reruns."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from scripts import audit_main_study_execution_order as order


def _fixture():
    start = datetime(2026, 9, 12, 0, 0, tzinfo=timezone.utc)
    events = []
    for index, (task, variant) in enumerate(order.EXPECTED_ORDER):
        begin = start + timedelta(minutes=3 * index + 1)
        events.append({
            "task_id": task, "variant": variant, "status": "completed",
            "started_at_utc": begin.isoformat(),
            "finished_at_utc": (begin + timedelta(minutes=1)).isoformat(),
        })
    return {
        "schema_version": 1, "study_id": order.STUDY_ID,
        "task_set_id": order.TASK_SET_ID, "total_expected_runs": 40,
        "attempted_runs": 40, "completed_runs": 40,
        "failed_runs": 0, "timeout_runs": 0,
        "estimated_treatment_cost_usd": 0.625, "current": None,
        "started_at_utc": start.isoformat(),
        "finished_at_utc": (start + timedelta(minutes=121)).isoformat(),
        "events": events,
    }


def test_accepts_complete_synthetic_recorded_schedule():
    receipt = order.audit_progress(_fixture(), sha256="a" * 64, byte_size=1234)
    assert receipt["recorded_events_checked"] == 40
    assert receipt["status"].endswith("not_authenticated")
    assert receipt["variant_order_randomized"] is False
    assert receipt["temporal_confounding_resolved"] is False
    assert receipt["independent_archive_custody_authenticated"] is False
    assert receipt["fixed_variant_order_within_each_task"] == list(order.VARIANTS)


def test_reports_exact_descriptive_start_lags_without_outcome_inference():
    receipt = order.audit_progress(_fixture(), sha256="a" * 64, byte_size=10)
    exposure = receipt["recorded_clock_exposure"]
    assert exposure["interpretation"] == "recorded_start_time_separation_only_not_web_drift"
    assert exposure["unit"] == "microseconds"
    assert exposure["study_window_microseconds"] == 121 * 60 * 1_000_000
    assert list(exposure["primary_contrast_start_lags"]) == [
        label for _, _, label in order.PRIMARY_CONTRAST_START_PAIRS
    ]
    for left, right, label in order.PRIMARY_CONTRAST_START_PAIRS:
        lag = exposure["primary_contrast_start_lags"][label]
        assert lag["left_variant"] == left
        assert lag["right_variant"] == right
        assert lag["start_lag_microseconds_by_task"] == {
            task: 3 * 60 * 1_000_000 for task in order.TASK_IDS
        }
        assert lag["minimum_start_lag_microseconds"] == 180_000_000
        assert lag["maximum_start_lag_microseconds"] == 180_000_000
    assert receipt["temporal_confounding_resolved"] is False


def test_reported_lag_reflects_nonuniform_recorded_clock_not_fixed_arm_spacing():
    progress = _fixture()
    # Synthetic clock gap increases between D3 start and D6 start on task 1.
    progress["events"][0]["started_at_utc"] = "2026-09-12T00:00:30+00:00"
    receipt = order.audit_progress(progress, sha256="a" * 64, byte_size=10)
    lags = receipt["recorded_clock_exposure"]["primary_contrast_start_lags"]
    depth = lags["D6_minus_D3_retrieval_depth"]
    assert depth["start_lag_microseconds_by_task"]["main-01"] == 210_000_000
    assert depth["start_lag_microseconds_by_task"]["main-02"] == 180_000_000
    assert depth["minimum_start_lag_microseconds"] == 180_000_000
    assert depth["maximum_start_lag_microseconds"] == 210_000_000
    assert lags["P6_minus_D6_planning"]["maximum_start_lag_microseconds"] == 180_000_000


@pytest.mark.parametrize("mutation, message", [
    ("swapped_arms", "fixed-arm order"),
    ("missing_event", "40 recorded events"),
    ("overlap", "overlap or reverse"),
    ("naive_clock", "explicitly UTC"),
    ("wrong_task_set", "task_set_id"),
    ("failed_run", "completed frozen run"),
    ("unfinalized", "unfinished current"),
    ("reversed_study_finish", "study finish"),
])
def test_fails_closed_on_invalid_progress(mutation, message):
    progress = _fixture()
    if mutation == "swapped_arms":
        progress["events"][0], progress["events"][1] = progress["events"][1], progress["events"][0]
    elif mutation == "missing_event":
        progress["events"].pop()
    elif mutation == "overlap":
        progress["events"][1]["started_at_utc"] = progress["events"][0]["started_at_utc"]
    elif mutation == "naive_clock":
        progress["events"][0]["started_at_utc"] = "2026-09-12T00:01:00"
    elif mutation == "wrong_task_set":
        progress["task_set_id"] = "a different task set"
    elif mutation == "failed_run":
        progress["failed_runs"] = 1
    elif mutation == "unfinalized":
        progress["current"] = {}
    elif mutation == "reversed_study_finish":
        progress["finished_at_utc"] = progress["started_at_utc"]
    with pytest.raises(order.ChronologyError, match=message):
        order.audit_progress(progress, sha256="a" * 64, byte_size=10)


def test_supplied_pin_must_match_and_is_not_authentication():
    receipt = order.audit_progress(_fixture(), sha256="a" * 64, byte_size=10,
                                   expected_sha256="a" * 64)
    assert receipt["supplied_digest_matched"] is True
    assert receipt["independent_archive_custody_authenticated"] is False
    with pytest.raises(order.ChronologyError, match="disagree with supplied pin"):
        order.audit_progress(_fixture(), sha256="a" * 64, byte_size=10,
                             expected_sha256="b" * 64)


def test_bounded_capture_round_trip_and_read_only(tmp_path: Path):
    path = tmp_path / "synthetic-progress.json"
    path.write_text(json.dumps(_fixture()), encoding="utf-8")
    before = path.read_bytes()
    payload, digest, size = order._capture_progress(path)
    receipt = order.audit_progress(payload, sha256=digest, byte_size=size)
    assert receipt["recorded_events_checked"] == 40
    assert path.read_bytes() == before


@pytest.mark.parametrize("kind", ("symlink", "oversized", "duplicate_key", "nonfinite"))
def test_capture_rejects_unsafe_or_ambiguous_source(tmp_path: Path, kind):
    path = tmp_path / "input.json"
    if kind == "symlink":
        target = tmp_path / "real.json"
        target.write_text("{}")
        path.symlink_to(target)
    elif kind == "oversized":
        path.write_bytes(b"x" * (order.MAX_PROGRESS_BYTES + 1))
    elif kind == "duplicate_key":
        path.write_text('{"events":[],"events":[]}', encoding="utf-8")
    else:
        path.write_text('{"events":NaN}', encoding="utf-8")
    with pytest.raises(order.ChronologyError):
        order._capture_progress(path)


@pytest.mark.parametrize("field_value", [-1, -0.01, float("inf"), float("nan"),
                                         True, "0.625", None])
def test_rejects_invalid_recorded_cost_before_clock_analysis(field_value):
    progress = _fixture()
    progress["estimated_treatment_cost_usd"] = field_value
    with pytest.raises(order.ChronologyError, match="estimated_treatment_cost_usd"):
        order.audit_progress(progress, sha256="a" * 64, byte_size=10)


def test_rejects_missing_recorded_cost():
    progress = _fixture()
    del progress["estimated_treatment_cost_usd"]
    with pytest.raises(order.ChronologyError, match="estimated_treatment_cost_usd"):
        order.audit_progress(progress, sha256="a" * 64, byte_size=10)


@pytest.mark.parametrize("raw", [
    b'{"uninspected_metadata":1e400}',
    b'{"uninspected_metadata":' + b"9" * 5000 + b"}",
    b'{"uninspected_metadata":' + b"9" * 150 + b"}",
    b'{"uninspected_metadata":0.' + b"1" * 150 + b"}",
])
def test_capture_rejects_overflow_and_unbounded_numbers_even_if_not_used(tmp_path, raw):
    path = tmp_path / "untrusted.json"
    path.write_bytes(raw)
    with pytest.raises(order.ChronologyError, match="numeric bound|finite range"):
        order._capture_progress(path)

def _synthetic_published_cost_csv() -> bytes:
    """Invented uniform costs are test fixtures, never VERA results."""
    import csv
    import io
    handle = io.StringIO(newline="")
    writer = csv.writer(handle)
    writer.writerow(("variant_id", "task_id", "completed", "treatment_cost_usd", "latency_seconds"))
    for task, variant in order.EXPECTED_ORDER:
        writer.writerow((variant, task, "True", "0.015625", "60.0"))
    return handle.getvalue().encode("utf-8")


def test_synthetic_progress_final_cost_matches_complete_pinned_resource_ledger(tmp_path, monkeypatch):
    import hashlib
    raw = _synthetic_published_cost_csv()
    path = tmp_path / "published.csv"
    path.write_bytes(raw)
    monkeypatch.setattr(order, "PUBLISHED_TREATMENT_CSV_SHA256", hashlib.sha256(raw).hexdigest())
    receipt = order.audit_progress(
        _fixture(), sha256="a" * 64, byte_size=10, published_treatment_csv=path
    )
    audit = receipt["frozen_treatment_cost_concordance"]
    assert audit["checked"] is True
    assert audit["published_treatment_cells_checked"] == 40
    assert audit["published_treatment_cost_sum_usd"] == 0.625
    assert audit["recorded_final_treatment_cost_usd"] == 0.625
    assert audit["historical_archive_custody_authenticated"] is False
    assert audit["provider_billing_authenticated"] is False


def test_synthetic_progress_final_cost_disagreement_blocks_receipt(tmp_path, monkeypatch):
    import hashlib
    raw = _synthetic_published_cost_csv()
    path = tmp_path / "published.csv"
    path.write_bytes(raw)
    monkeypatch.setattr(order, "PUBLISHED_TREATMENT_CSV_SHA256", hashlib.sha256(raw).hexdigest())
    progress = _fixture()
    progress["estimated_treatment_cost_usd"] += 0.01
    with pytest.raises(order.ChronologyError, match="differs from frozen published"):
        order.audit_progress(
            progress, sha256="a" * 64, byte_size=10, published_treatment_csv=path
        )


@pytest.mark.parametrize("mutation", [
    "digest", "duplicate", "missing", "incomplete", "nan", "negative", "extra_field",
    "symlink",
])
def test_published_treatment_csv_rejects_ambiguous_and_changed_sources(
    tmp_path, monkeypatch, mutation
):
    import hashlib
    raw = _synthetic_published_cost_csv()
    path = tmp_path / "published.csv"
    if mutation == "symlink":
        target = tmp_path / "original.csv"
        target.write_bytes(raw)
        path.symlink_to(target)
        monkeypatch.setattr(order, "PUBLISHED_TREATMENT_CSV_SHA256",
                            hashlib.sha256(raw).hexdigest())
    else:
        lines = raw.decode("utf-8").splitlines()
        if mutation == "digest":
            lines[1] = lines[1].replace("0.015625", "0.015626")
        elif mutation == "duplicate":
            lines[2] = lines[1]
        elif mutation == "missing":
            lines.pop()
        elif mutation == "incomplete":
            lines[1] = lines[1].replace("True", "False")
        elif mutation == "nan":
            lines[1] = lines[1].replace("0.015625", "NaN")
        elif mutation == "negative":
            lines[1] = lines[1].replace("0.015625", "-0.01")
        elif mutation == "extra_field":
            lines[1] += ",unexpected"
        candidate = ("\n".join(lines) + "\n").encode("utf-8")
        path.write_bytes(candidate)
        monkeypatch.setattr(order, "PUBLISHED_TREATMENT_CSV_SHA256",
                            hashlib.sha256(raw if mutation == "digest" else candidate).hexdigest())
    with pytest.raises(order.ChronologyError):
        order._load_published_treatment_cost(path)


def test_original_published_resource_csv_matches_immutable_input_pin():
    """Read already published, unchanged measurement input; do not rerun models."""
    cost = order._load_published_treatment_cost(order.PUBLISHED_TREATMENT_CSV)
    assert 0 < cost < 3.0


def test_cli_does_not_report_success_for_synthetic_wrong_total(tmp_path, capsys):
    path = tmp_path / "progress.json"
    path.write_text(json.dumps(_fixture()), encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        order.main(["--progress-json", str(path)])
    assert failure.value.code == 1
    assert "differs from frozen published" in capsys.readouterr().err


def test_progress_writer_schema_receipt_discloses_structural_scope():
    receipt = order.audit_progress(_fixture(), sha256="a" * 64, byte_size=100)
    fields = receipt["original_completed_writer_field_schema"]
    assert fields == {
        "checked": True,
        "progress_fields_checked": 13,
        "completed_event_fields_per_run_checked": 5,
        "unexpected_fields_allowed": False,
        "independently_authenticated": False,
    }


@pytest.mark.parametrize("extra,value", [
    ("canonical_archive_authenticated", True),
    ("human_rater_scores", [5, 5]),
    ("extra_execution_events", []),
])
def test_rejects_nonhistorical_top_level_progress_fields(extra, value):
    progress = _fixture()
    progress[extra] = value
    with pytest.raises(order.ChronologyError, match="progress fields differ"):
        order.audit_progress(progress, sha256="a" * 64, byte_size=100)


@pytest.mark.parametrize("missing", [
    "study_id", "estimated_treatment_cost_usd", "finished_at_utc",
])
def test_rejects_missing_completed_progress_writer_fields(missing):
    progress = _fixture()
    del progress[missing]
    with pytest.raises(order.ChronologyError, match="progress fields differ"):
        order.audit_progress(progress, sha256="a" * 64, byte_size=100)


@pytest.mark.parametrize("extra,value", [
    ("posthoc_strict_support_rate", 1.0),
    ("recovered_source_digest", "a" * 64),
    ("human_annotation", {"correctness": 5}),
])
def test_rejects_invented_completed_event_metadata(extra, value):
    progress = _fixture()
    progress["events"][0][extra] = value
    with pytest.raises(order.ChronologyError, match="event 1 fields differ"):
        order.audit_progress(progress, sha256="a" * 64, byte_size=100)


@pytest.mark.parametrize("missing", [
    "variant", "task_id", "status", "started_at_utc", "finished_at_utc",
])
def test_rejects_incomplete_original_writer_event_fields(missing):
    progress = _fixture()
    del progress["events"][0][missing]
    with pytest.raises(order.ChronologyError, match="event 1 fields differ"):
        order.audit_progress(progress, sha256="a" * 64, byte_size=100)



def _pinned_synthetic_latency_ledger(tmp_path, monkeypatch, *, latency=None):
    """Synthetic published-input fixture; its numbers are not historical data."""
    import hashlib

    raw = _synthetic_published_cost_csv()
    if latency is not None:
        raw = raw.replace(b"60.0", str(latency).encode("ascii"), 1)
    path = tmp_path / "synthetic-pinned-ledger.csv"
    path.write_bytes(raw)
    monkeypatch.setattr(
        order, "PUBLISHED_TREATMENT_CSV_SHA256", hashlib.sha256(raw).hexdigest()
    )
    return path


def test_latency_concordance_success_is_only_a_structural_receipt(tmp_path, monkeypatch):
    path = _pinned_synthetic_latency_ledger(tmp_path, monkeypatch)
    receipt = order.audit_progress(
        _fixture(), sha256="a" * 64, byte_size=1, published_treatment_csv=path
    )
    check = receipt["frozen_treatment_latency_concordance"]
    assert check["checked"] is True
    assert check["published_treatment_cells_checked"] == 40
    assert check["maximum_wall_clock_shortfall_tolerance_seconds"] == 5
    assert check["recorded_utc_intervals_not_materially_shorter_than_frozen_latency"] is True
    assert check["historical_archive_custody_authenticated"] is False
    assert check["trace_latency_clock_authenticated"] is False


def test_latency_concordance_detects_shortened_progress_event(tmp_path, monkeypatch):
    path = _pinned_synthetic_latency_ledger(tmp_path, monkeypatch)
    progress = _fixture()
    original_end = datetime.fromisoformat(progress["events"][0]["finished_at_utc"])
    progress["events"][0]["finished_at_utc"] = (
        original_end - timedelta(seconds=10)
    ).isoformat()
    with pytest.raises(order.ChronologyError, match="shorter than frozen published treatment latency"):
        order.audit_progress(
            progress, sha256="a" * 64, byte_size=1, published_treatment_csv=path
        )


def test_latency_concordance_allows_minor_clock_difference(tmp_path, monkeypatch):
    path = _pinned_synthetic_latency_ledger(tmp_path, monkeypatch)
    progress = _fixture()
    original_end = datetime.fromisoformat(progress["events"][0]["finished_at_utc"])
    progress["events"][0]["finished_at_utc"] = (
        original_end - timedelta(seconds=3)
    ).isoformat()
    receipt = order.audit_progress(
        progress, sha256="a" * 64, byte_size=1, published_treatment_csv=path
    )
    assert receipt["frozen_treatment_latency_concordance"]["checked"] is True


def test_per_cell_latency_mismatch_detected_even_when_total_cost_matches(tmp_path, monkeypatch):
    # First trace latency contradicts the outer UTC interval by >5 seconds.
    path = _pinned_synthetic_latency_ledger(tmp_path, monkeypatch, latency="80.0")
    with pytest.raises(order.ChronologyError, match="shorter than frozen published treatment latency"):
        order.audit_progress(
            _fixture(), sha256="a" * 64, byte_size=1, published_treatment_csv=path
        )


@pytest.mark.parametrize("token", ["NaN", "Infinity", "1e400", "-1", "0", "bad", "9" * 160])
def test_latency_ledger_rejects_malformed_nonpositive_or_unbounded_numbers(
    tmp_path, monkeypatch, token
):
    path = _pinned_synthetic_latency_ledger(tmp_path, monkeypatch, latency=token)
    with pytest.raises(order.ChronologyError):
        order._load_published_treatment_cost(path, include_latencies=True)


def test_original_frozen_latency_ledger_is_pinned_and_complete():
    """Read the published input only; no treatment/evaluator execution."""
    total, by_cell = order._load_published_treatment_cost(
        order.PUBLISHED_TREATMENT_CSV, include_latencies=True
    )
    assert total > 0
    assert set(by_cell) == set(order.EXPECTED_ORDER)
    assert all(value > 0 for value in by_cell.values())
