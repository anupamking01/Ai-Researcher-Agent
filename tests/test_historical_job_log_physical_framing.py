"""Offline physical-line framing checks for original VERA GitHub Actions logs.

All events are synthetic; these tests do not contact GitHub, run treatments,
or manufacture experimental or human-evaluation evidence.
"""
from __future__ import annotations

import pytest

from scripts import audit_historical_artifact_job_logs as audit


FIRST = "2026-09-11T17:22:39.0297511Z"
SECOND = "2026-09-11T17:22:40.4375561Z"
TWO_EVENTS = f"{FIRST} one event\n{SECOND} another event"


@pytest.mark.parametrize(
    "forged_separator",
    ("\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"),
)
def test_non_lf_separator_cannot_create_another_timestamped_event(forged_separator):
    # The previous splitlines() parser accepted these as two stamped lines,
    # even though the supplied transcript has no physical LF separator.
    forged = TWO_EVENTS.replace("\n", forged_separator)
    assert len(forged.splitlines()) == 2
    with pytest.raises(audit.HistoricalLogError, match="physical line separator"):
        audit._bounded_lines(forged, "synthetic treatment")


@pytest.mark.parametrize("newline", ("\n", "\r\n"))
def test_lf_or_crlf_copy_preserves_stamped_event_identity(newline):
    rendered = TWO_EVENTS.replace("\n", newline) + newline
    assert audit._bounded_lines(rendered, "synthetic treatment") == [
        (FIRST, "one event"), (SECOND, "another event"),
    ]
    assert audit._bounded_lines(rendered[:-len(newline)], "synthetic treatment") == [
        (FIRST, "one event"), (SECOND, "another event"),
    ]


def test_utf8_bom_and_exact_upload_path_block_survive_crlf_copy():
    start = "2026-09-11T17:22:39.0297511Z"
    block = "\r\n".join((
        f"{start} ##[group]Run actions/upload-artifact@v4",
        f"{start} {audit._UPLOAD_PATH_HEAD}",
        *audit._UPLOAD_PATH_CONTINUATION,
        f"{start} upload complete",
    ))
    lines = audit._bounded_lines("\ufeff" + block + "\r\n", "synthetic original")
    assert lines[0] == (start, "##[group]Run actions/upload-artifact@v4")
    assert lines[-1] == (start, "upload complete")
    assert len(lines) == 3  # Stamped header, stamped path head, stamped tail.
