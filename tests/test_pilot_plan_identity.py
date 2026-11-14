"""No live/API work: synthetic pilot plan and postrun identity tests."""

import json

import pytest

from scripts import run_pilot
from scripts import validate_pilot_artifacts as postrun


TASKS = [
    {"id": "pilot-01", "question": "First synthetic diagnostic question?"},
    {"id": "pilot-02", "question": "Second synthetic diagnostic question?"},
]


def test_valid_pilot_plan_and_order_preserved():
    run_pilot._validate_run_plan("pilot-v1", TASKS, ["D6", "P6", "P6V"])
    assert [task["id"] for task in run_pilot._select_tasks(
        TASKS, ["pilot-02", "pilot-01"]
    )] == ["pilot-01", "pilot-02"]


@pytest.mark.parametrize(
    ("tasks", "variants", "message"),
    [
        (TASKS, ["D6", "D6"], "duplicate pilot variant"),
        (TASKS, ["D6", "bogus"], "unsupported pilot variant"),
        (TASKS, [], "nonempty list"),
        (TASKS + [dict(TASKS[0])], ["D6"], "duplicate pilot task id"),
        ([{"id": " pilot-01", "question": "x"}], ["D6"], "invalid id"),
        ([{"id": "pilot-01", "question": "   "}], ["D6"], "no question"),
        ([{"id": "pilot-01"}], ["D6"], "no question"),
        ([None], ["D6"], "must be an object"),
        ([], ["D6"], "nonempty list"),
    ],
)
def test_ambiguous_run_plan_rejected(tasks, variants, message):
    with pytest.raises(ValueError, match=message):
        run_pilot._validate_run_plan("pilot-v1", tasks, variants)


def test_invalid_study_identity_rejected():
    with pytest.raises(ValueError, match="task_set_id"):
        run_pilot._validate_run_plan(" pilot-v1", TASKS, ["D6"])


@pytest.mark.parametrize(
    ("requested", "message"),
    [
        (["pilot-01", "pilot-01"], "duplicate --task-id"),
        (["pilot-09"], "unknown pilot task IDs"),
    ],
)
def test_cli_task_selection_never_silently_collapses(requested, message):
    with pytest.raises(ValueError, match=message):
        run_pilot._select_tasks(TASKS, requested)


def test_original_task_source_satisfies_new_plan_contract():
    path = run_pilot.REPO_ROOT / "experiments/pilot_tasks.json"
    task_set_id, tasks = run_pilot._load_tasks(path)
    assert task_set_id == "pilot-v1-2026-09-08"
    assert len(tasks) == 5
    run_pilot._validate_run_plan(task_set_id, tasks, ["D6", "P6", "P6V"])


def write_minimal_pilot(root):
    manifest = {
        "variants": ["D6"], "task_ids": ["pilot-01"],
        "task_set_id": "pilot-v1", "smart_model": "synthetic-smart",
        "fast_model": "synthetic-fast", "temperature": 1,
    }
    progress = {
        "variants": ["D6"], "task_ids": ["pilot-01"],
        "task_set_id": "pilot-v1", "total_expected_runs": 1,
        "attempted_runs": 1, "completed_runs": 1,
        "failed_runs": 0, "timeout_runs": 0,
    }
    summary = {"n_trace_files": 1, "variant_summary": {
        "D6": {"n_runs": 1, "n_completed": 1},
    }}
    experiment = {
        "variant_id": "D6", "task_id": "pilot-01",
        "task_set_id": "pilot-v1", "source_budget": 6,
    }
    trace = {
        "variant_id": "D6", "task_id": "pilot-01",
        "task_set_id": "pilot-v1", "completed": True,
        "source_budget": 6, "source_count": 6,
        "successful_source_count": 6, "failed_source_count": 0,
        "scheduled_urls": [f"https://example.org/{i}" for i in range(6)],
        "successful_urls": [f"https://example.org/{i}" for i in range(6)],
        "failed_urls": [],
        "planning_mode": "direct", "query_count": 1,
        "search_call_count": 1, "research_context_words": 10,
        "report_words": 10, "model_call_count": 1,
        "total_tokens": 10,
        "usage_accounting_status": "provider_usage_complete",
        "smart_model": "synthetic-smart", "fast_model": "synthetic-fast",
        "temperature": 1, "verification_mode": "none",
        "verification_status": "not_requested",
    }
    for name, record in (
        ("pilot_manifest.json", manifest),
        ("pilot_progress.json", progress),
        ("pilot_summary.json", summary),
    ):
        (root / name).write_text(json.dumps(record), encoding="utf-8")
    folder = root / "experiment_traces" / "D6"
    folder.mkdir(parents=True)
    (folder / "sample.json").write_text(
        json.dumps({"experiment": experiment, "trace": trace}), encoding="utf-8"
    )
    return manifest, progress, experiment, trace


def save_pilot(root, manifest, progress, experiment, trace, folder="D6"):
    for name, record in (
        ("pilot_manifest.json", manifest),
        ("pilot_progress.json", progress),
    ):
        (root / name).write_text(json.dumps(record), encoding="utf-8")
    file = root / "experiment_traces" / "D6" / "sample.json"
    file.unlink()
    target = root / "experiment_traces" / folder / "sample.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"experiment": experiment, "trace": trace}), encoding="utf-8"
    )


def test_valid_synthetic_postrun_plan_passes(tmp_path):
    write_minimal_pilot(tmp_path)
    assert postrun.validate_pilot(tmp_path) == []


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda m, p, e, t: m["variants"].append("D6"), "manifest variants contains duplicates"),
        (lambda m, p, e, t: m["task_ids"].append("pilot-01"), "manifest task_ids contains duplicates"),
        (lambda m, p, e, t: p.update(task_set_id="other"), "progress task_set_id differs"),
        (lambda m, p, e, t: p.update(variants=["P6"]), "progress variants differs"),
        (lambda m, p, e, t: t.update(variant_id="P6"), "trace.variant_id disagrees"),
        (lambda m, p, e, t: t.update(task_id="pilot-99"), "trace.task_id disagrees"),
        (lambda m, p, e, t: t.update(task_set_id="other"), "trace.task_set_id disagrees"),
        (lambda m, p, e, t: e.update(task_set_id="other"), "experiment.task_set_id disagrees"),
    ],
)
def test_tampered_plan_or_trace_rejected(tmp_path, mutate, expected):
    manifest, progress, experiment, trace = write_minimal_pilot(tmp_path)
    mutate(manifest, progress, experiment, trace)
    save_pilot(tmp_path, manifest, progress, experiment, trace)
    assert expected in " | ".join(postrun.validate_pilot(tmp_path))


def test_wrong_treatment_directory_rejected(tmp_path):
    manifest, progress, experiment, trace = write_minimal_pilot(tmp_path)
    save_pilot(tmp_path, manifest, progress, experiment, trace, folder="P6")
    assert "trace directory" in " | ".join(postrun.validate_pilot(tmp_path))
