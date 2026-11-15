"""Offline synthetic contract for the downstream eight-shard CI replay gate."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest
import yaml


def _steps():
    workflow = yaml.load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/tests.yml").read_text(
            encoding="utf-8"
        ),
        Loader=yaml.BaseLoader,
    )
    job = workflow["jobs"]["replay-complete-shard-set"]
    return workflow, job, {item["name"]: item for item in job["steps"]}


def test_complete_set_replay_is_gated_on_successful_eight_way_matrix():
    workflow, job, steps = _steps()
    assert workflow["permissions"] == {"contents": "read"}
    assert job["needs"] == "unit-tests"
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == "10"
    assert steps["Checkout exact tested sources for full-set replay"]["with"][
        "persist-credentials"
    ] == "false"
    assert steps["Set up pinned Python for full-set replay"]["with"][
        "python-version"
    ] == "3.11.17"
    assert steps["Download current-attempt shard evidence"]["uses"] == (
        "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
    )
    assert steps["Download current-attempt shard evidence"]["with"] == {
        "pattern": "vera-offline-tests-shard-*-${{ github.run_id }}-${{ github.run_attempt }}",
        "merge-multiple": "false",
        "path": "${{ runner.temp }}/vera-downloaded-shard-artifacts",
    }


def test_aggregate_verifier_uses_external_identity_and_runs_before_retention():
    _, job, steps = _steps()
    names = [step["name"] for step in job["steps"]]
    stage = steps["Stage exact-attempt shard directories"]["run"]
    replay = steps["Independently replay all eight downloaded shard receipts"]["run"]
    assert names.index("Download current-attempt shard evidence") < names.index(
        "Stage exact-attempt shard directories"
    ) < names.index("Independently replay all eight downloaded shard receipts")
    assert names.index("Verify exact checkout after full-set replay") < names.index(
        "Retain verified eight-shard replay (90 days)"
    )
    assert 'for shard in {0..7}; do' in stage
    assert '${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}' in stage
    assert 'test -z "$(find "$base" -mindepth 1 -print -quit)"' in stage
    for expected in (
        "python -m scripts.verify_full_ci_shard_set",
        '--checkout-sha "$GITHUB_SHA"',
        '--run-id "$GITHUB_RUN_ID"',
        '--run-attempt "$GITHUB_RUN_ATTEMPT"',
        '--event "$GITHUB_EVENT_NAME"',
        '--evidence-root "$RUNNER_TEMP/vera-eight-shard-evidence"',
    ):
        assert expected in replay
    assert "pip install" not in replay
    assert "run_budget_main_study" not in replay
    assert "evaluate_posthoc_support" not in replay
    before = steps["Verify Python and checkout before full-set replay"]["run"]
    after = steps["Verify exact checkout after full-set replay"]["run"]
    assert "verify_ci_source_checkout" in before
    assert "verify_ci_source_checkout" in after
    retained = steps["Retain verified eight-shard replay (90 days)"]["with"]
    assert retained["name"] == "vera-full-shard-replay-${{ github.run_id }}-${{ github.run_attempt }}"
    assert retained["if-no-files-found"] == "error"
    assert "vera-full-shard-replay.json" in retained["path"]


@pytest.mark.parametrize("case", ["complete", "missing", "extra", "wrong_attempt"])
def test_shell_staging_fails_closed_on_missing_or_mixed_downloads(tmp_path, case):
    _, _, steps = _steps()
    stage = steps["Stage exact-attempt shard directories"]["run"]
    downloaded = tmp_path / "vera-downloaded-shard-artifacts"
    downloaded.mkdir()
    for shard in range(8):
        if case == "missing" and shard == 6:
            continue
        attempt = "1" if case == "wrong_attempt" and shard == 6 else "2"
        folder = downloaded / f"vera-offline-tests-shard-{shard}-12345-{attempt}"
        folder.mkdir()
        (folder / "dummy").write_text("synthetic-only", encoding="utf-8")
    if case == "extra":
        (downloaded / "unexpected-bundle").mkdir()
    result = subprocess.run(
        ["bash", "-c", stage],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path),
             "GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "2"},
        text=True, capture_output=True, timeout=15, check=False,
    )
    if case == "complete":
        assert result.returncode == 0, result.stderr
        assert sorted(
            entry.name for entry in (tmp_path / "vera-eight-shard-evidence").iterdir()
        ) == [f"shard-{i}" for i in range(8)]
        assert not list(downloaded.iterdir())
    else:
        assert result.returncode != 0


def test_failure_diagnostics_are_distinct_from_verified_success_receipts():
    """Preserve negative CI evidence without certifying an incomplete shard."""
    workflow, replay_job, replay_steps = _steps()
    steps = workflow["jobs"]["unit-tests"]["steps"]
    failing = [
        step for step in steps
        if step.get("name") == "Retain unverified diagnostics on CI failure (90 days)"
    ]
    assert len(failing) == 1
    failed = failing[0]
    assert failed["if"] == "${{ failure() && !cancelled() }}"
    assert failed["uses"] == (
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    )
    assert failed["with"]["name"] == (
        "vera-unverified-failure-shard-${{ matrix.shard }}-"
        "${{ github.run_id }}-${{ github.run_attempt }}"
    )
    assert failed["with"]["retention-days"] == "90"
    # A failed test, source gate or replay might have no files, or only a
    # partial transcript. Missing files must not mask the original failure.
    assert failed["with"]["if-no-files-found"] == "warn"
    paths = failed["with"]["path"].splitlines()
    assert paths == [
        "${{ runner.temp }}/vera-offline-tests.log",
        "${{ runner.temp }}/vera-offline-test-modules.txt",
    ]
    assert not any("receipt" in path for path in paths)
    valid = next(step for step in steps if step.get("name") ==
                 "Retain source-bound offline test evidence (90 days)")
    assert "if" not in valid  # default success-only retention
    assert steps.index(failed) > steps.index(valid)
    assert replay_job["needs"] == "unit-tests"
    assert "if" not in replay_job  # failure skips the aggregate success gate
    download = replay_steps["Download current-attempt shard evidence"]["with"]
    assert download["pattern"].startswith("vera-offline-tests-shard-")
    assert "unverified" not in download["pattern"]


def test_synthetic_failed_pipeline_keeps_output_without_turning_green(tmp_path):
    """The actual CI wrapper uses pipefail with tee; failures remain failures."""
    command = (
        "set -euo pipefail; "
        "bash -c 'echo synthetic-failing-pytest; exit 7' "
        '| tee "$RUNNER_TEMP/vera-offline-tests.log"'
    )
    proc = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path)},
        text=True, capture_output=True, timeout=10, check=False,
    )
    assert proc.returncode == 7
    assert "synthetic-failing-pytest" in (
        tmp_path / "vera-offline-tests.log"
    ).read_text(encoding="utf-8")
    assert not (tmp_path / "vera-offline-test-receipt.json").exists()
