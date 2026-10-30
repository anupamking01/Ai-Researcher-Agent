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


def test_cli_accepts_bounded_synthetic_job_logs(tmp_path, capsys, monkeypatch):
    a, b = _logs()
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
    with pytest.raises(audit.HistoricalLogError, match="chronology contradicts archive lineage"):
        audit.audit_historical_job_logs(original, recovery)


def test_recovery_archive_cannot_be_logged_as_uploaded_before_source_download():
    original, recovery = _logs()
    recovery = recovery.replace("2026-09-13T21:21:3", "2026-09-13T21:20:3")
    with pytest.raises(audit.HistoricalLogError, match="chronology contradicts archive lineage"):
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
