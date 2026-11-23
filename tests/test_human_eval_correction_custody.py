"""Synthetic-only correction custody and no-cherry-picking regressions."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_correction_custody as custody


def _fixture(tmp_path, monkeypatch):
    root = tmp_path / "submissions"
    root.mkdir()
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    monkeypatch.setattr(
        custody.freeze_verifier, "verify_frozen_snapshot",
        lambda **kwargs: {"status": "blinded_human_ratings_verified"})
    def make(filename, score):
        path = root / filename
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=freeze.RATING_FIELDS)
            writer.writeheader()
            writer.writerow({
                "annotator_id": "Rater-A", "blind_id": "H001",
                **{field: str(score) for field in freeze.SCORE_FIELDS},
                "notes": "synthetic-only",
            })
        return hashlib.sha256(path.read_bytes()).hexdigest()
    first = make("r001_v001.csv", 2)
    final = make("r001_v002.csv", 3)
    data = {"schema_version": 1, "study_id": "budget-main-v1",
            "phase": "before_unblinding",
            "chains": [{"annotator_id": "Rater-A",
                        "reason": "clerical_transcription",
                        "versions": [
                            {"file": "r001_v001.csv", "sha256": first},
                            {"file": "r001_v002.csv", "sha256": final},
                        ]}]}
    ledger = tmp_path / "ledger.json"
    def store():
        ledger.write_text(json.dumps(data), encoding="utf-8")
        (frozen / "freeze_manifest.json").write_text(
            json.dumps({"study_id": "budget-main-v1",
                        "rating_inputs": [{"sha256": data["chains"][0]["versions"][-1]["sha256"]}]}),
            encoding="utf-8")
    store()
    return root, frozen, ledger, data, store


def test_success_is_only_blinded_custody(tmp_path, monkeypatch):
    root, frozen, ledger, data, store = _fixture(tmp_path, monkeypatch)
    result = custody.audit_corrections(
        ledger=ledger, submissions_root=root, freeze_root=frozen)
    assert result["n_retained_versions"] == 2
    assert result["historical_timing_independently_authenticated"] is False
    assert "rating" not in result


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(phase="after_unblinding"),
    lambda d: d["chains"][0].update(reason="favorable_score"),
    lambda d: d["chains"][0]["versions"].pop(),
    lambda d: d["chains"][0]["versions"][0].update(file="../outside.csv"),
    lambda d: d["chains"][0]["versions"][0].update(sha256="0" * 64),
    lambda d: d["chains"][0].update(annotator_id="Another-Rater"),
    lambda d: d["chains"].append(dict(d["chains"][0])),
    lambda d: d["chains"][0]["versions"][0].update(
        file="r001_v002.csv", sha256=d["chains"][0]["versions"][1]["sha256"]),
])
def test_rejects_invalid_chains(tmp_path, monkeypatch, mutation):
    root, frozen, ledger, data, store = _fixture(tmp_path, monkeypatch)
    mutation(data)
    store()
    with pytest.raises(ValueError):
        custody.audit_corrections(
            ledger=ledger, submissions_root=root, freeze_root=frozen)


def test_rejects_superseded_submission_in_freeze(tmp_path, monkeypatch):
    root, frozen, ledger, data, store = _fixture(tmp_path, monkeypatch)
    (frozen / "freeze_manifest.json").write_text(
        json.dumps({"study_id": "budget-main-v1", "rating_inputs": [
            {"sha256": data["chains"][0]["versions"][0]["sha256"]},
            {"sha256": data["chains"][0]["versions"][1]["sha256"]},
        ]}), encoding="utf-8")
    with pytest.raises(ValueError, match="superseded"):
        custody.audit_corrections(
            ledger=ledger, submissions_root=root, freeze_root=frozen)


def test_rejects_unfrozen_replacement(tmp_path, monkeypatch):
    root, frozen, ledger, data, store = _fixture(tmp_path, monkeypatch)
    (frozen / "freeze_manifest.json").write_text(
        json.dumps({"study_id": "budget-main-v1", "rating_inputs": [
            {"sha256": "0" * 64}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="absent"):
        custody.audit_corrections(
            ledger=ledger, submissions_root=root, freeze_root=frozen)


def test_rejects_replaced_bytes(tmp_path, monkeypatch):
    root, frozen, ledger, data, store = _fixture(tmp_path, monkeypatch)
    with (root / "r001_v001.csv").open("a", encoding="utf-8") as handle:
        handle.write("extra")
    with pytest.raises(ValueError, match="digest"):
        custody.audit_corrections(
            ledger=ledger, submissions_root=root, freeze_root=frozen)


def test_rejects_duplicate_ledger_keys(tmp_path, monkeypatch):
    root, frozen, ledger, data, store = _fixture(tmp_path, monkeypatch)
    ledger.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        custody.audit_corrections(
            ledger=ledger, submissions_root=root, freeze_root=frozen)


def _replace_blind_rows(root: Path, filename: str, blind_ids: list[str]) -> str:
    """Write synthetic rows only; never use real annotator ratings."""
    path = root / filename
    with path.open("r", newline="", encoding="utf-8") as handle:
        template = next(csv.DictReader(handle))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=freeze.RATING_FIELDS)
        writer.writeheader()
        for blind_id in blind_ids:
            writer.writerow({**template, "blind_id": blind_id})
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("reason,original,final,accepted", [
    ("clerical_transcription", ["H001"], ["H001"], True),
    ("clerical_transcription", ["H001"], ["H002"], False),
    ("file_format_correction", ["H001"], ["H001", "H002"], False),
    ("other_predeclared_validity_correction", ["H001", "H002"], ["H001"], False),
    ("missing_row_completion", ["H001"], ["H001", "H002"], True),
    ("missing_row_completion", ["H001", "H002"], ["H001"], False),
    ("missing_row_completion", ["H001"], ["H002"], False),
])
def test_corrected_versions_preserve_blinded_report_coverage(
    tmp_path, monkeypatch, reason, original, final, accepted
):
    root, frozen, ledger, data, store = _fixture(tmp_path, monkeypatch)
    chain = data["chains"][0]
    chain["reason"] = reason
    chain["versions"][0]["sha256"] = _replace_blind_rows(
        root, "r001_v001.csv", original
    )
    chain["versions"][1]["sha256"] = _replace_blind_rows(
        root, "r001_v002.csv", final
    )
    store()
    if accepted:
        result = custody.audit_corrections(
            ledger=ledger, submissions_root=root, freeze_root=frozen
        )
        assert result["n_accepted_versions_bound_to_verified_freeze"] == 1
    else:
        with pytest.raises(ValueError, match="report"):
            custody.audit_corrections(
                ledger=ledger, submissions_root=root, freeze_root=frozen
            )


@pytest.mark.parametrize("original_ids,pattern", [
    ([""], "blank blinded report ID"),
    (["H001", "H001"], "duplicate blinded report ID"),
])
def test_rejects_ambiguous_superseded_report_identity(
    tmp_path, monkeypatch, original_ids, pattern
):
    root, frozen, ledger, data, store = _fixture(tmp_path, monkeypatch)
    data["chains"][0]["versions"][0]["sha256"] = _replace_blind_rows(
        root, "r001_v001.csv", original_ids
    )
    store()
    with pytest.raises(ValueError, match=pattern):
        custody.audit_corrections(
            ledger=ledger, submissions_root=root, freeze_root=frozen
        )
