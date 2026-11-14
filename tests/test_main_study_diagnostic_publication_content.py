"""Adversarial stage-to-published diagnostic result integrity checks.

Only synthetic local files are used; no treatment or evaluation is executed.
"""
import os

import pytest

from scripts import analyze_main_study_with_preflight as diagnostic


@pytest.fixture
def staged(tmp_path):
    source = tmp_path / "staging"
    source.mkdir()
    (source / diagnostic.DIAGNOSTIC_JSON).write_text('{"n_tasks": 10}', encoding="utf-8")
    (source / diagnostic.DIAGNOSTIC_MD).write_text("# synthetic inference\n", encoding="utf-8")
    return source, tmp_path / "published"


def test_unchanged_diagnostics_publish_exact_source_bytes(staged):
    source, destination = staged
    diagnostic._publish_diagnostic_pair(source, destination)
    for name in (diagnostic.DIAGNOSTIC_JSON, diagnostic.DIAGNOSTIC_MD):
        assert (destination / name).read_bytes() == (source / name).read_bytes()


def test_mutation_of_first_staged_output_during_second_link_fails_closed(staged, monkeypatch):
    source, destination = staged
    original = diagnostic.os.link

    def mutate_after_link(src, dst, **kwargs):
        result = original(src, dst, **kwargs)
        if src == diagnostic.DIAGNOSTIC_JSON:
            # The destination is already hard-linked to this mutable inode.
            (source / src).write_text('{"n_tasks": 99}', encoding="utf-8")
        return result

    monkeypatch.setattr(diagnostic.os, "link", mutate_after_link)
    with pytest.raises(ValueError, match="content or identity changed"):
        diagnostic._publish_diagnostic_pair(source, destination)
    assert not destination.exists()


def test_identical_byte_inode_replacement_of_second_staged_output_fails_closed(
    staged, monkeypatch
):
    source, destination = staged
    original = diagnostic.os.link

    def replace_second_after_first_link(src, dst, **kwargs):
        result = original(src, dst, **kwargs)
        if src == diagnostic.DIAGNOSTIC_JSON:
            second = source / diagnostic.DIAGNOSTIC_MD
            replacement = source / "replacement.md"
            replacement.write_bytes(second.read_bytes())
            os.replace(replacement, second)
        return result

    monkeypatch.setattr(diagnostic.os, "link", replace_second_after_first_link)
    with pytest.raises(ValueError, match="staged-file identity changed"):
        diagnostic._publish_diagnostic_pair(source, destination)
    assert not destination.exists()


def test_mutation_after_both_links_before_final_verification_fails_closed(staged, monkeypatch):
    source, destination = staged
    original = diagnostic.os.fsync
    calls = 0

    def mutate_after_sync(fd):
        nonlocal calls
        result = original(fd)
        calls += 1
        if calls == 1:
            (destination / diagnostic.DIAGNOSTIC_MD).write_text(
                "# modified after linking\n", encoding="utf-8"
            )
        return result

    monkeypatch.setattr(diagnostic.os, "fsync", mutate_after_sync)
    with pytest.raises(ValueError, match="content or identity changed"):
        diagnostic._publish_diagnostic_pair(source, destination)
    assert not destination.exists()


def test_oversized_stage_file_is_rejected_before_destination_creation(staged, monkeypatch):
    source, destination = staged
    monkeypatch.setattr(diagnostic, "DIAGNOSTIC_MAX_FILE_BYTES", 8)
    with pytest.raises(ValueError, match="size limit"):
        diagnostic._publish_diagnostic_pair(source, destination)
    assert not destination.exists()


def test_staged_symlink_rejected_without_following_external_file(staged):
    source, destination = staged
    original = source / diagnostic.DIAGNOSTIC_MD
    outside = source.parent / "external-synthetic"
    outside.write_text("must remain untouched", encoding="utf-8")
    original.unlink()
    original.symlink_to(outside)
    with pytest.raises(ValueError, match="cannot be opened safely"):
        diagnostic._publish_diagnostic_pair(source, destination)
    assert outside.read_text(encoding="utf-8") == "must remain untouched"
    assert not destination.exists()
