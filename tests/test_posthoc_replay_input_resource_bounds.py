"""Bound untrusted noncanonical evaluator inputs before parsing/provider use.

All inputs are synthetic offline fixtures. No treatment or evaluator is run.
"""
import pytest

from scripts import evaluate_posthoc_support as evaluator


def test_json_oversize_fails_before_parsing_even_when_valid(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_JSON_BYTES", 32)
    path = tmp_path / "trace.json"
    path.write_text('{"unused_metadata":"' + "x" * 64 + '"}', encoding="utf-8")
    with pytest.raises(SystemExit, match="JSON input exceeds maximum 32 bytes"):
        evaluator._load_json(path)


def test_json_exact_byte_boundary_is_accepted(tmp_path, monkeypatch):
    raw = b'{"metadata":{"count":1}}'
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_JSON_BYTES", len(raw))
    path = tmp_path / "cache.json"
    path.write_bytes(raw)
    assert evaluator._load_json(path) == {"metadata": {"count": 1}}


def test_json_one_byte_past_limit_fails(tmp_path, monkeypatch):
    raw = b'{"metadata":{"count":1}}'
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_JSON_BYTES", len(raw) - 1)
    path = tmp_path / "cache.json"
    path.write_bytes(raw)
    with pytest.raises(SystemExit, match="JSON input exceeds maximum"):
        evaluator._load_json(path)


def test_text_limit_counts_utf8_bytes_not_characters(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_TEXT_FILE_BYTES", 6)
    path = tmp_path / "research_report.md"
    path.write_text("ééé", encoding="utf-8")
    assert evaluator._read_regular_text(path, label="Evaluator report") == "ééé"
    path.write_text("éééé", encoding="utf-8")
    with pytest.raises(SystemExit, match="Evaluator report exceeds maximum 6 bytes"):
        evaluator._read_regular_text(path, label="Evaluator report")


def test_report_reader_rejects_large_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_TEXT_FILE_BYTES", 12)
    run_dir = tmp_path / "outputs" / "example-run"
    run_dir.mkdir(parents=True)
    (run_dir / "research_report.md").write_text("R" * 13, encoding="utf-8")
    with pytest.raises(SystemExit, match="Evaluator report exceeds maximum"):
        evaluator._report_text("example-run", root=tmp_path)


def test_context_rejects_oversized_combination_of_valid_files(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_TEXT_FILE_BYTES", 16)
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_EVIDENCE_BYTES", 9)
    run_dir = tmp_path / "outputs" / "example-run"
    run_dir.mkdir(parents=True)
    (run_dir / "research-query-01.txt").write_text("abcd", encoding="utf-8")
    (run_dir / "research-query-02.txt").write_text("wxyz", encoding="utf-8")
    with pytest.raises(SystemExit, match="exceeds combined 9-byte limit"):
        evaluator._research_context("example-run", root=tmp_path)


def test_context_exact_combined_boundary_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_TEXT_FILE_BYTES", 16)
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_EVIDENCE_BYTES", 10)
    run_dir = tmp_path / "outputs" / "example-run"
    run_dir.mkdir(parents=True)
    (run_dir / "research-query-01.txt").write_text("abcd", encoding="utf-8")
    (run_dir / "research-query-02.txt").write_text("wxyz", encoding="utf-8")
    assert evaluator._research_context("example-run", root=tmp_path) == "abcd\n\nwxyz"


def test_invalid_text_still_rejected_within_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_TEXT_FILE_BYTES", 4)
    path = tmp_path / "source.txt"
    path.write_bytes(b"\xff")
    with pytest.raises(SystemExit, match="must contain valid UTF-8"):
        evaluator._read_regular_text(path, label="Evaluator evidence")
