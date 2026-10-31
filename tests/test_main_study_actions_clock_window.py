"""Synthetic-only offline checks for historical GitHub Actions clock concordance."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts import audit_main_study_execution_order as order


def synthetic_progress():
    start = datetime(2026, 9, 11, 16, 15, 55, tzinfo=timezone.utc)
    events = []
    for i, (task, variant) in enumerate(order.EXPECTED_ORDER):
        started = start + timedelta(seconds=65 * i)
        events.append({
            "task_id": task, "variant": variant, "status": "completed",
            "started_at_utc": started.isoformat(),
            "finished_at_utc": (started + timedelta(seconds=60)).isoformat(),
        })
    return {
        "schema_version": 1, "study_id": order.STUDY_ID,
        "task_set_id": order.TASK_SET_ID, "total_expected_runs": 40,
        "attempted_runs": 40, "completed_runs": 40, "failed_runs": 0,
        "timeout_runs": 0, "estimated_treatment_cost_usd": 0.625,
        "events": events, "current": None,
        "started_at_utc": start.isoformat(),
        "finished_at_utc": events[-1]["finished_at_utc"],
    }


def audit(candidate):
    return order.audit_progress(candidate, sha256="a" * 64, byte_size=100,
                                require_historical_actions_step_window=True)


def test_synthetic_schedule_within_original_actions_window():
    receipt = audit(synthetic_progress())
    check = receipt["historical_actions_step_window_concordance"]
    assert check["checked"] is True
    assert check["original_actions_run_id"] == 34620917346
    assert check["original_actions_job_id"] == 103334373932
    assert check["original_actions_run_attempt"] == 1
    assert check["recorded_study_within_treatment_step"] is True
    assert check["independently_authenticated"] is False
    assert receipt["temporal_confounding_resolved"] is False


@pytest.mark.parametrize("case", ["too_early", "too_late", "shift_all"])
def test_rejects_internally_consistent_but_impossible_timelines(case):
    p = synthetic_progress()
    if case == "too_early":
        p["started_at_utc"] = "2026-09-11T16:15:46+00:00"
    elif case == "too_late":
        p["finished_at_utc"] = "2026-09-11T17:12:14+00:00"
    else:
        for event in p["events"]:
            for field in ("started_at_utc", "finished_at_utc"):
                event[field] = (datetime.fromisoformat(event[field]) + timedelta(days=1)).isoformat()
        for field in ("started_at_utc", "finished_at_utc"):
            p[field] = (datetime.fromisoformat(p[field]) + timedelta(days=1)).isoformat()
    with pytest.raises(order.ChronologyError, match="outside original GitHub Actions"):
        audit(p)


def test_coarse_step_timestamps_admit_five_second_slack():
    p = synthetic_progress()
    p["started_at_utc"] = "2026-09-11T16:15:47+00:00"
    p["finished_at_utc"] = "2026-09-11T17:12:13+00:00"
    assert audit(p)["historical_actions_step_window_concordance"]["checked"]


def test_module_fixture_can_remain_unanchored_but_receipt_discloses_it():
    p = synthetic_progress()
    p["started_at_utc"] = "2026-09-11T16:00:00+00:00"
    receipt = order.audit_progress(p, sha256="a" * 64, byte_size=100)
    assert receipt["historical_actions_step_window_concordance"] == {"checked": False}


def test_production_cli_cannot_bypass_window_with_synthetic_file(tmp_path, monkeypatch, capsys):
    # Replace only the unrelated frozen-cost source with a synthetic fixture.
    monkeypatch.setattr(
        order, "_load_published_treatment_cost",
        lambda path, *, include_latencies=False: (
            (0.625, {cell: 60.0 for cell in order.EXPECTED_ORDER})
            if include_latencies else 0.625
        ),
    )
    path = tmp_path / "synthetic-progress.json"
    path.write_text(json.dumps(synthetic_progress()), encoding="utf-8")
    assert order.main(["--progress-json", str(path)]) == 0
    assert '"recorded_study_within_treatment_step": true' in capsys.readouterr().out

    p = synthetic_progress()
    p["started_at_utc"] = "2026-09-11T16:15:46+00:00"
    path.write_text(json.dumps(p), encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        order.main(["--progress-json", str(path)])
    assert failure.value.code == 1
    out = capsys.readouterr()
    assert "outside original GitHub Actions" in out.err
    assert "recorded_fixed_order_consistent" not in out.out
