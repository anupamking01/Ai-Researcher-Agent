"""Offline regressions for captured historical job-log source identity.

No workflow logs are downloaded and no experiment is executed.
"""
import os

import pytest

from scripts import audit_historical_artifact_job_logs as audit


def test_bounded_single_link_log_is_read_without_rewriting(tmp_path):
    path = tmp_path / "historical.log"
    content = "\ufeff2026-09-11T17:22:40.0000000Z synthetic metadata\n"
    path.write_text(content, encoding="utf-8")
    assert audit._read_log(path) == content
    assert path.read_text(encoding="utf-8") == content


def test_existing_hardlink_alias_cannot_supply_historical_job_log(tmp_path):
    path = tmp_path / "historical.log"
    path.write_text("2026-09-11T17:22:40.0000000Z synthetic\n")
    os.link(path, tmp_path / "alternate.log")
    with pytest.raises(audit.HistoricalLogError, match="single-link"):
        audit._read_log(path)


def test_new_hardlink_alias_during_capture_invalidates_source(tmp_path, monkeypatch):
    path = tmp_path / "historical.log"
    alias = tmp_path / "late-alias.log"
    path.write_text("2026-09-11T17:22:40.0000000Z synthetic\n")
    original_fdopen = os.fdopen

    class LinkedReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def fileno(self):
            return self.handle.fileno()

        def read(self, limit):
            data = self.handle.read(limit)
            os.link(path, alias)
            return data

    monkeypatch.setattr(audit.os, "fdopen", lambda *a, **kw: LinkedReader(
        original_fdopen(*a, **kw)
    ))
    with pytest.raises(audit.HistoricalLogError, match="changed"):
        audit._read_log(path)
    assert alias.exists()


def test_short_descriptor_read_with_unchanged_metadata_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "historical.log"
    path.write_text("2026-09-11T17:22:40.0000000Z synthetic\n")
    original_fdopen = os.fdopen

    class ShortReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def fileno(self):
            return self.handle.fileno()

        def read(self, limit):
            return self.handle.read(limit)[:-1]

    monkeypatch.setattr(audit.os, "fdopen", lambda *a, **kw: ShortReader(
        original_fdopen(*a, **kw)
    ))
    with pytest.raises(audit.HistoricalLogError, match="truncated"):
        audit._read_log(path)
