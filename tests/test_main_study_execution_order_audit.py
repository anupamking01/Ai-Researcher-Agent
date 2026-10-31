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
        "failed_runs": 0, "timeout_runs": 0, "current": None,
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
