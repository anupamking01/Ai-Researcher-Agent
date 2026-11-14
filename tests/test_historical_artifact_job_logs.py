"""Synthetic, offline regressions for contemporaneous GitHub artifact-log lineage."""
from __future__ import annotations

import pytest

from scripts import audit_historical_artifact_job_logs as audit


def _line(timestamp: str, message: str) -> str:
    return f"{timestamp} {message}"


def _logs() -> tuple[str, str]:
    original = audit.ORIGINAL
    recovered = audit.RECOVERED
    a, b = original["artifact_name"], recovered["artifact_name"]
    h, j = original["zip_sha256"], recovered["zip_sha256"]
    original_log = "\n".join([
        _line("2026-09-11T17:22:39.0297511Z", "##[group]Run actions/upload-artifact@v4"),
        _line("2026-09-11T17:22:40.4375561Z", f"SHA256 digest of uploaded artifact zip is {h}"),
        _line("2026-09-11T17:22:40.6897562Z", f"Artifact {a}.zip successfully finalized. Artifact ID {original['artifact_id']}"),
        _line("2026-09-11T17:22:40.6898529Z", f"Artifact {a} has been successfully uploaded! Final size is {original['size_bytes']} bytes. Artifact ID is {original['artifact_id']}"),
        _line("2026-09-11T17:22:40.6903482Z", f"Artifact download URL: https://github.com/{audit.REPOSITORY}/actions/runs/{original['run_id']}/artifacts/{original['artifact_id']}"),
        _line("2026-09-11T17:22:40.7100120Z", "Post job cleanup."),
    ])
    recovery_log = "\n".join([
        _line("2026-09-13T21:21:03.9240000Z", "##[group]Run actions/download-artifact@v4"),
        _line("2026-09-13T21:21:04.3171190Z", f"- {a} (ID: {original['artifact_id']}, Size: {original['size_bytes']}, Expected Digest: sha256:{h})"),
        _line("2026-09-13T21:21:04.3207087Z", f"Downloading artifact '{original['artifact_id']}' from '{audit.REPOSITORY}'"),
        _line("2026-09-13T21:21:05.3735717Z", f"SHA256 digest of downloaded artifact is {h}"),
        _line("2026-09-13T21:21:05.3736586Z", "Artifact download completed successfully."),
        _line("2026-09-13T21:21:05.3736925Z", "Total of 1 artifact(s) downloaded"),
        _line("2026-09-13T21:21:05.3879883Z", "##[group]Run python - <<'PY'"),
        _line("2026-09-13T21:21:35.2241667Z", "##[group]Run actions/upload-artifact@v4"),
        _line("2026-09-13T21:21:36.9137499Z", f"SHA256 digest of uploaded artifact zip is {j}"),
        _line("2026-09-13T21:21:37.1789583Z", f"Artifact {b}.zip successfully finalized. Artifact ID {recovered['artifact_id']}"),
        _line("2026-09-13T21:21:37.1791553Z", f"Artifact {b} has been successfully uploaded! Final size is {recovered['size_bytes']} bytes. Artifact ID is {recovered['artifact_id']}"),
        _line("2026-09-13T21:21:37.1797920Z", f"Artifact download URL: https://github.com/{audit.REPOSITORY}/actions/runs/{recovered['run_id']}/artifacts/{recovered['artifact_id']}"),
        _line("2026-09-13T21:21:37.1983251Z", "Post job cleanup."),
    ])
    return original_log, recovery_log


def test_contemporaneous_upload_download_correspondence_is_not_custody():
    original, recovered = _logs()
    receipt = audit.audit_historical_job_logs(original, recovered)
    assert receipt["two_workflow_github_log_digest_concordance"] is True
    assert receipt["original_treatment_upload"]["zip_sha256"] == audit.ORIGINAL["zip_sha256"]
    assert receipt["evaluator_recovery_download"]["zip_sha256"] == audit.ORIGINAL["zip_sha256"]
    assert receipt["evaluator_recovery_upload"]["zip_sha256"] == audit.RECOVERED["zip_sha256"]
    assert receipt["historical_treatment_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert receipt["experimental_treatments_rerun"] is False


@pytest.mark.parametrize("source,original,replacement,error", [
    ("original", audit.ORIGINAL["zip_sha256"], "f" * 64, "historical upload differs"),
    ("recovery", audit.ORIGINAL["zip_sha256"], "f" * 64, "recovery download does not match"),
    ("recovery", audit.RECOVERED["zip_sha256"], "e" * 64, "historical upload differs"),
    ("original", "Final size is 608355", "Final size is 608354", "historical upload differs"),
    ("recovery", "Size: 608355", "Size: 608356", "recovery download does not match"),
    ("original", "artifacts/10275100801", "artifacts/10275100802", "historical upload differs"),
])
def test_changed_log_metadata_fails_closed(source, original, replacement, error):
    a, b = _logs()
    if source == "original":
        a = a.replace(original, replacement)
    else:
        b = b.replace(original, replacement)
    with pytest.raises(audit.HistoricalLogError, match=error):
        audit.audit_historical_job_logs(a, b)


def test_duplicate_upload_digest_event_cannot_be_selected():
    a, b = _logs()
    marker = f"SHA256 digest of uploaded artifact zip is {audit.ORIGINAL['zip_sha256']}"
    line = _line("2026-09-11T17:22:40.4375562Z", marker)
    a = a.replace(marker, marker + "\n" + line)
    with pytest.raises(audit.HistoricalLogError, match="exactly one"):
        audit.audit_historical_job_logs(a, b)


def test_log_text_outside_action_step_cannot_supply_missing_upload():
    a, b = _logs()
    marker = f"SHA256 digest of uploaded artifact zip is {audit.ORIGINAL['zip_sha256']}"
    a = _line("2026-09-11T17:22:38.0000000Z", marker) + "\n" + a.replace(marker, "not a digest")
    with pytest.raises(audit.HistoricalLogError, match="upload ZIP digest"):
        audit.audit_historical_job_logs(a, b)


def test_missing_recovery_completion_fails_closed():
    a, b = _logs()
    b = b.replace("Artifact download completed successfully.", "Artifact download failed.")
    with pytest.raises(audit.HistoricalLogError, match="recovery download completion"):
        audit.audit_historical_job_logs(a, b)


def test_oversize_log_rejected_before_parsing():
    a, b = _logs()
    with pytest.raises(audit.HistoricalLogError, match="bounded UTF-8"):
        audit.audit_historical_job_logs("x" * (audit.MAX_LOG_BYTES + 1), b)



def _with_job_envelope(log: str, *, original: bool) -> str:
    if original:
        start, cleanup, terminal = (
            "2026-09-11T16:15:19.0726994Z",
            "2026-09-11T17:22:40.8790940Z",
            "2026-09-11T17:22:40.8981857Z",
        )
        actions = "actions/checkout@v4, actions/setup-python@v5, actions/upload-artifact@v4"
    else:
        start, cleanup, terminal = (
            "2026-09-13T21:20:36.3138953Z",
            "2026-09-13T21:21:37.5684206Z",
            "2026-09-13T21:21:37.5998672Z",
        )
        actions = (
            "actions/checkout@v4, actions/download-artifact@v4, "
            "actions/setup-python@v5, actions/upload-artifact@v4"
        )
    return "\n".join((
        _line(start, "Current runner version: '2.337.0'"),
        log,
        _line(cleanup, "Cleaning up orphan processes"),
        _line(
            terminal,
            "##[warning]Node.js 20 is deprecated. The following actions target "
            "Node.js 20 but are being forced to run on Node.js 24: "
            + actions
            + ". For more information see: "
            "https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/",
        ),
    ))


@pytest.mark.parametrize("original", [True, False])
def test_pinned_job_log_envelope_accepts_historical_opening_and_terminal_markers(original):
    a, b = _logs()
    log = _with_job_envelope(a if original else b, original=original)
    audit._require_historical_job_envelope(
        log,
        run_id=audit.ORIGINAL["run_id"] if original else audit.RECOVERED["run_id"],
        label="synthetic",
    )


@pytest.mark.parametrize("original", [True, False])
def test_digest_bearing_excerpt_without_job_envelope_is_not_accepted_by_cli_guard(original):
    a, b = _logs()
    log = a if original else b
    # Action-level matching still succeeds on these synthetic excerpts.
    audit.audit_historical_job_logs(a, b)
    with pytest.raises(audit.HistoricalLogError, match="opening marker"):
        audit._require_historical_job_envelope(
            log,
            run_id=audit.ORIGINAL["run_id"] if original else audit.RECOVERED["run_id"],
            label="synthetic",
        )


@pytest.mark.parametrize("original", [True, False])
def test_pinned_job_envelope_rejects_truncated_tail_and_missing_cleanup(original):
    a, b = _logs()
    log = _with_job_envelope(a if original else b, original=original)
    run_id = audit.ORIGINAL["run_id"] if original else audit.RECOVERED["run_id"]
    with pytest.raises(audit.HistoricalLogError, match="terminal job-log warning"):
        audit._require_historical_job_envelope(
            "\n".join(log.splitlines()[:-1]), run_id=run_id, label="synthetic",
        )
    without_cleanup = "\n".join(
        line for line in log.splitlines() if not line.endswith("Cleaning up orphan processes")
    )
    with pytest.raises(audit.HistoricalLogError, match="terminal cleanup"):
        audit._require_historical_job_envelope(
            without_cleanup, run_id=run_id, label="synthetic",
        )


def test_pinned_job_envelope_rejects_concatenated_job_and_early_cleanup():
    a, _ = _logs()
    log = _with_job_envelope(a, original=True)
    with pytest.raises(audit.HistoricalLogError, match="duplicate or relocated"):
        audit._require_historical_job_envelope(
            log + "\n" + log, run_id=audit.ORIGINAL["run_id"], label="synthetic",
        )
    moved = log.replace(
        _line("2026-09-11T17:22:40.8790940Z", "Cleaning up orphan processes"),
        "",
    ).replace(
        _line("2026-09-11T16:15:19.0726994Z", "Current runner version: '2.337.0'"),
        _line("2026-09-11T16:15:19.0726994Z", "Current runner version: '2.337.0'") +
        "\n" + _line("2026-09-11T16:15:19.0726995Z", "Cleaning up orphan processes"),
    )
    with pytest.raises(audit.HistoricalLogError, match="terminal cleanup"):
        audit._require_historical_job_envelope(
            moved, run_id=audit.ORIGINAL["run_id"], label="synthetic",
        )


def test_cli_accepts_bounded_synthetic_job_logs(tmp_path, capsys, monkeypatch):
    a, b = _logs()
    a = _with_job_envelope(a, original=True)
    b = _with_job_envelope(b, original=False)
    original = tmp_path / "original.log"
    recovery = tmp_path / "recovery.log"
    original.write_text(a, encoding="utf-8")
    recovery.write_text(b, encoding="utf-8")
    monkeypatch.setattr("sys.argv", [
        "audit_historical_artifact_job_logs",
        "--original-job-log", str(original),
        "--recovery-job-log", str(recovery),
    ])
    assert audit.main() == 0
    assert "historical_github_job_log_zip_lineage_corresponds_not_authenticated" in capsys.readouterr().out



def test_original_upload_log_line_order_does_not_mask_reversed_clock_times():
    original, recovery = _logs()
    original = original.replace(
        "2026-09-11T17:22:40.4375561Z",
        "2026-09-11T17:22:41.4375561Z",
    )
    with pytest.raises(audit.HistoricalLogError, match="timestamps are out of order"):
        audit.audit_historical_job_logs(original, recovery)


def test_recovery_download_reordered_timestamps_fail_closed():
    original, recovery = _logs()
    recovery = recovery.replace(
        "2026-09-13T21:21:04.3207087Z",
        "2026-09-13T21:21:06.3207087Z",
    )
    with pytest.raises(audit.HistoricalLogError, match="timestamps are out of order"):
        audit.audit_historical_job_logs(original, recovery)


def test_original_archive_cannot_be_logged_as_uploaded_after_recovery_download():
    original, recovery = _logs()
    original = original.replace("2026-09-11T", "2026-09-14T")
    # The stronger original-workflow gate rejects this before cross-run order.
    with pytest.raises(audit.HistoricalLogError, match="outside pinned workflow window"):
        audit.audit_historical_job_logs(original, recovery)


def test_recovery_archive_cannot_be_logged_as_uploaded_before_source_download():
    original, recovery = _logs()
    recovery = recovery.replace("2026-09-13T21:21:3", "2026-09-13T21:20:3")
    with pytest.raises(audit.HistoricalLogError, match="timestamps are out of order|chronology contradicts archive lineage"):
        audit.audit_historical_job_logs(original, recovery)


@pytest.mark.parametrize(("source", "before", "after"), [
    ("original", "2026-09-11T", "2026-09-10T"),
    ("original", "2026-09-11T", "2026-09-12T"),
    ("recovery", "2026-09-13T", "2026-09-12T"),
    ("recovery", "2026-09-13T", "2026-09-14T"),
])
def test_historical_job_log_events_must_be_inside_their_original_workflow_window(
    source, before, after
):
    """Whole-step date shifts retain ordering/digests but cannot be historical."""
    original, recovery = _logs()
    if source == "original":
        assert before in original
        original = original.replace(before, after)
    else:
        assert before in recovery
        recovery = recovery.replace(before, after)
    with pytest.raises(audit.HistoricalLogError, match="outside pinned workflow window"):
        audit.audit_historical_job_logs(original, recovery)


def test_workflow_window_allows_last_reported_second_fraction():
    """GitHub workflow timestamps have second precision, logs subsecond."""
    original, recovery = _logs()
    original = original.replace(
        "2026-09-11T17:22:40.6903482Z",
        "2026-09-11T17:22:43.999999999Z",
    ).replace(
        "2026-09-11T17:22:40.7100120Z",
        "2026-09-11T17:22:43.999999999Z",
    )
    # Both the final URL and its observed closing boundary must fit the
    # last second; an earlier cleanup would be a reversed event clock.
    receipt = audit.audit_historical_job_logs(original, recovery)
    assert receipt["historical_treatment_evidence_authenticated"] is False


@pytest.mark.parametrize(("source", "old_stamp", "new_stamp"), [
    ("original", "2026-09-11T17:22:39.0297511Z", "2026-09-11T17:22:41.0297511Z"),
    ("recovery", "2026-09-13T21:21:03.9240000Z", "2026-09-13T21:21:05.9240000Z"),
])
def test_action_step_marker_cannot_postdate_its_digest_events(
    source, old_stamp, new_stamp
):
    """Pinned event timestamps alone cannot excuse a later step start."""
    original, recovery = _logs()
    if source == "original":
        original = original.replace(old_stamp, new_stamp)
    else:
        recovery = recovery.replace(old_stamp, new_stamp)
    with pytest.raises(audit.HistoricalLogError, match="timestamps are out of order"):
        audit.audit_historical_job_logs(original, recovery)


def test_unrelated_step_progress_line_cannot_reverse_the_action_clock():
    original, recovery = _logs()
    digest = _line(
        "2026-09-11T17:22:40.4375561Z",
        f"SHA256 digest of uploaded artifact zip is {audit.ORIGINAL['zip_sha256']}",
    )
    assert digest in original
    original = original.replace(
        digest,
        digest + "\n" + _line("2026-09-11T17:22:40.1000000Z", "Upload progress"),
    )
    with pytest.raises(audit.HistoricalLogError, match="timestamps are out of order"):
        audit.audit_historical_job_logs(original, recovery)


def test_unrelated_step_progress_line_must_be_inside_historical_run_window():
    original, recovery = _logs()
    cleanup = _line("2026-09-11T17:22:40.7100120Z", "Post job cleanup.")
    assert cleanup in original
    original = original.replace(
        cleanup,
        _line("2026-09-12T00:00:00.0000000Z", "Upload debug note") + "\n"
        + _line("2026-09-12T00:00:01.0000000Z", "Post job cleanup."),
    )
    # Keep the closing boundary after the injected progress message so the
    # out-of-window gate, not the distinct event-reversal gate, is exercised.
    with pytest.raises(audit.HistoricalLogError, match="outside pinned workflow window"):
        audit.audit_historical_job_logs(original, recovery)


def test_impossible_calendar_date_in_expected_event_fails_closed():
    original, recovery = _logs()
    original = original.replace(
        "2026-09-11T17:22:40.4375561Z",
        "2026-02-30T17:22:40.4375561Z",
    )
    with pytest.raises(audit.HistoricalLogError, match="invalid GitHub job-log UTC"):
        audit.audit_historical_job_logs(original, recovery)


def test_equal_timestamp_precision_does_not_invent_event_reversal():
    original, recovery = _logs()
    original = original.replace(
        "2026-09-11T17:22:40.6897562Z",
        "2026-09-11T17:22:40.6898529Z",
    )
    receipt = audit.audit_historical_job_logs(original, recovery)
    assert receipt["two_workflow_github_log_digest_concordance"] is True
    assert receipt["historical_treatment_evidence_authenticated"] is False


def test_submicrosecond_clock_reversal_is_detected():
    original, recovery = _logs()
    original = original.replace(
        "2026-09-11T17:22:40.6897562Z",
        "2026-09-11T17:22:40.6898530Z",
    )
    with pytest.raises(audit.HistoricalLogError, match="timestamps are out of order"):
        audit.audit_historical_job_logs(original, recovery)


@pytest.mark.parametrize(("source", "unframed"), [
    (
        "original",
        f"SHA256 digest of uploaded artifact zip is {audit.ORIGINAL['zip_sha256']}",
    ),
    (
        "original",
        "2026-09-11T18:22:40.4375561+01:00 Upload progress",
    ),
    (
        "recovery",
        "2026-09-13T21:21:05Z Artifact download completed successfully.",
    ),
    (
        "recovery",
        "2026-09-13T21:21:05.3736925Z\\tTotal of 1 artifact(s) downloaded",
    ),
])
def test_unframed_or_noncanonical_log_lines_fail_instead_of_disappearing(
    source, unframed
):
    """A second, unframed claim or malformed clock cannot be silently omitted."""
    original, recovery = _logs()
    if source == "original":
        anchor = "2026-09-11T17:22:40.4375561Z"
        assert anchor in original
        original = original.replace(anchor, unframed + "\n" + anchor, 1)
    else:
        anchor = "2026-09-13T21:21:05.3735717Z"
        assert anchor in recovery
        recovery = recovery.replace(anchor, unframed + "\n" + anchor, 1)
    with pytest.raises(audit.HistoricalLogError, match="unframed or malformed"):
        audit.audit_historical_job_logs(original, recovery)


def test_empty_log_line_separator_remains_accepted():
    """A harmless blank separator is not mistaken for an action event."""
    original, recovery = _logs()
    original = original.replace(
        "2026-09-11T17:22:40.4375561Z",
        "\n2026-09-11T17:22:40.4375561Z", 1
    )
    receipt = audit.audit_historical_job_logs(original, recovery)
    assert receipt["historical_treatment_evidence_authenticated"] is False

@pytest.mark.parametrize(("source", "missing_boundary"), [
    ("original", "2026-09-11T17:22:40.7100120Z Post job cleanup."),
    ("recovery", "2026-09-13T21:21:37.1983251Z Post job cleanup."),
])
def test_historical_upload_requires_an_observed_following_step_or_cleanup(
    source, missing_boundary
):
    """A digest/URL-only tail is not a complete observed action window."""
    original, recovery = _logs()
    if source == "original":
        assert missing_boundary in original
        original = original.replace(missing_boundary, "")
    else:
        assert missing_boundary in recovery
        recovery = recovery.replace(missing_boundary, "")
    with pytest.raises(audit.HistoricalLogError, match="no following workflow boundary"):
        audit.audit_historical_job_logs(original, recovery)


@pytest.mark.parametrize(("source", "before", "after", "error"), [
    (
        "original",
        "2026-09-11T17:22:40.7100120Z Post job cleanup.",
        "2026-09-11T17:22:40.0000000Z Post job cleanup.",
        "timestamps are out of order",
    ),
    (
        "recovery",
        "2026-09-13T21:21:05.3879883Z ##[group]Run python - <<'PY'",
        "2026-09-13T21:21:05.0000000Z ##[group]Run python - <<'PY'",
        "timestamps are out of order",
    ),
    (
        "recovery",
        "2026-09-13T21:21:37.1983251Z Post job cleanup.",
        "2026-09-14T00:00:00.0000000Z Post job cleanup.",
        "outside pinned workflow window",
    ),
])
def test_action_closing_boundary_is_within_the_recorded_chronology(
    source, before, after, error
):
    """Closing boundaries are also evidence-bearing clock observations."""
    original, recovery = _logs()
    if source == "original":
        assert before in original
        original = original.replace(before, after)
    else:
        assert before in recovery
        recovery = recovery.replace(before, after)
    with pytest.raises(audit.HistoricalLogError, match=error):
        audit.audit_historical_job_logs(original, recovery)


def _with_historical_upload_path_block(log: str) -> str:
    """Model the literal multiline upload path returned by GitHub job-log GET."""
    marker = next(
        line for line in log.splitlines()
        if line.endswith(" ##[group]Run actions/upload-artifact@v4")
    )
    stamp = marker.split(" ", 1)[0]
    block = "\n".join((
        _line(stamp, audit._UPLOAD_PATH_HEAD),
        *audit._UPLOAD_PATH_CONTINUATION,
    ))
    return log.replace(marker, marker + "\n" + block, 1)


def test_raw_github_log_bom_and_exact_multiline_upload_path_are_accepted():
    """Historical GET format must work, not just hand-curated log excerpts."""
    original, recovery = _logs()
    original = "\ufeff" + _with_historical_upload_path_block(original)
    recovery = "\ufeff" + _with_historical_upload_path_block(recovery)
    receipt = audit.audit_historical_job_logs(original, recovery)
    assert receipt["two_workflow_github_log_digest_concordance"] is True
    assert receipt["historical_treatment_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False


@pytest.mark.parametrize("source", ["original", "recovery"])
def test_modified_or_reordered_unframed_upload_input_fails_closed(source):
    original, recovery = _logs()
    selected = _with_historical_upload_path_block(
        original if source == "original" else recovery
    )
    selected = selected.replace(
        "\noutputs/posthoc_support_runs.csv",
        "\noutputs/changed_support_runs.csv", 1
    )
    if source == "original":
        original = selected
    else:
        recovery = selected
    with pytest.raises(audit.HistoricalLogError, match="unexpected upload-artifact path continuation"):
        audit.audit_historical_job_logs(original, recovery)


def test_unframed_path_continuation_cannot_be_truncated_or_extended():
    original, recovery = _logs()
    selected = _with_historical_upload_path_block(original)
    missing = selected.replace("\noutputs/*/verification.json", "", 1)
    with pytest.raises(audit.HistoricalLogError, match="unexpected upload-artifact path continuation"):
        audit.audit_historical_job_logs(missing, recovery)
    surplus = selected.replace(
        "\noutputs/*/verification.json",
        "\noutputs/*/verification.json\noutputs/extra-secret.txt", 1
    )
    with pytest.raises(audit.HistoricalLogError, match="unframed or malformed"):
        audit.audit_historical_job_logs(surplus, recovery)


def test_unframed_path_outside_upload_step_and_second_bom_are_rejected():
    original, recovery = _logs()
    with pytest.raises(audit.HistoricalLogError, match="unframed or malformed"):
        audit.audit_historical_job_logs(
            original + "\n" + audit._UPLOAD_PATH_CONTINUATION[0], recovery
        )
    with pytest.raises(audit.HistoricalLogError, match="unframed or malformed"):
        audit.audit_historical_job_logs(
            original.replace("Post job cleanup.", "\ufeffPost job cleanup."),
            recovery
        )


def test_raw_job_log_clock_cannot_reverse_outside_selected_artifact_actions():
    original, recovery = _logs()
    # The artifact action itself remains unchanged and internally ordered.
    forged_prefix = _line("2026-09-11T17:22:41.0000000Z", "Earlier checkout step")
    with pytest.raises(audit.HistoricalLogError, match="timestamps are out of order"):
        audit.audit_historical_job_logs(forged_prefix + "\n" + original, recovery)


def test_raw_job_log_clock_cannot_escape_run_window_outside_selected_actions():
    original, recovery = _logs()
    forged_prefix = _line("2026-09-10T00:00:00.0000000Z", "Earlier checkout step")
    with pytest.raises(audit.HistoricalLogError, match="outside pinned workflow window"):
        audit.audit_historical_job_logs(forged_prefix + "\n" + original, recovery)
