"""Synthetic tests for the complete, unextracted Actions preservation package."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import warnings
import zipfile

import pytest

from scripts import verify_preserved_canonical_package as package
from scripts import verify_preserved_canonical_bundle as preserved
from scripts import verify_retained_canonical_download as source

CAPTURED = datetime(2026, 10, 29, 1, 34, tzinfo=timezone.utc)


def _parts(tmp_path, monkeypatch):
    inner = tmp_path / "retained-canonical.zip"
    inner.write_bytes(b"synthetic-only archive, never real treatment evidence")
    digest = hashlib.sha256(inner.read_bytes()).hexdigest()
    monkeypatch.setattr(source, "OBSERVED_ZIP_BYTES", inner.stat().st_size)
    monkeypatch.setattr(source, "OBSERVED_ZIP_SHA256", digest)

    metadata = {
        "id": source.ARTIFACT_ID,
        "name": source.ARTIFACT_NAME,
        "expired": False,
        "expires_at": "2026-12-23T23:03:46Z",
        "size_in_bytes": source.OBSERVED_ZIP_BYTES,
        "digest": "sha256:" + digest,
        "archive_download_url": (
            f"https://api.github.com/repos/{source.REPO}/actions/artifacts/"
            f"{source.ARTIFACT_ID}/zip"
        ),
        "workflow_run": {
            "id": source.RUN_ID,
            "head_sha": source.RUN_HEAD,
            "head_branch": "research-paper-eval-2027",
            "repository_id": source.REPO_ID,
            "head_repository_id": source.REPO_ID,
        },
    }
    metadata_file = tmp_path / package.METADATA
    metadata_file.write_text(json.dumps(metadata), encoding="utf-8")

    def fake_concordance(path, *, root):
        assert Path(path).read_bytes() == inner.read_bytes()
        return {
            "archive_sha256_observed_now": digest,
            "historical_evidence_authenticated": False,
            "original_treatment_traces_authenticated": False,
            "human_evaluation_ready": False,
            "independently_supplied_archive_pin_matched": False,
        }
    monkeypatch.setattr(source.concordance, "verify_archive_against_checkout", fake_concordance)

    initial = source.verify_download(metadata_file, inner, checked_at=CAPTURED)
    initial_file = tmp_path / package.ORIGINAL_RECEIPT
    initial_file.write_text(json.dumps(initial), encoding="utf-8")
    offline = preserved.verify_preserved_bundle(
        metadata_file, inner, initial_file, checked_at=CAPTURED,
    )
    return {
        package.METADATA: metadata_file.read_bytes(),
        package.INNER_ZIP: inner.read_bytes(),
        package.ORIGINAL_RECEIPT: initial_file.read_bytes(),
        package.OFFLINE_RECEIPT: json.dumps(offline).encode("utf-8"),
    }


def _zip(tmp_path, parts, name="preserved.zip"):
    path = tmp_path / name
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for key, value in parts.items():
                archive.writestr(key, value)
    return path


def test_full_outer_package_reverified_and_all_four_members_bound(tmp_path, monkeypatch):
    path = _zip(tmp_path, _parts(tmp_path, monkeypatch))
    receipt = package.verify_package(path)
    assert receipt["package_member_count"] == 4
    assert receipt["saved_offline_receipt_recomputed"] is True
    assert receipt["original_source_receipt_recomputed"] is True
    assert receipt["original_source_availability_checked_now"] is False
    assert receipt["original_treatment_traces_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert receipt["experimental_treatments_rerun"] is False


def test_older_three_file_preservation_package_still_verifies(tmp_path, monkeypatch):
    parts = _parts(tmp_path, monkeypatch)
    del parts[package.OFFLINE_RECEIPT]
    receipt = package.verify_package(_zip(tmp_path, parts))
    assert receipt["package_member_count"] == 3
    assert receipt["saved_offline_receipt_included"] is False
    assert receipt["saved_offline_receipt_recomputed"] is False


@pytest.mark.parametrize("edit", ["missing", "extra", "unexpected_directory", "path_escape"])
def test_incomplete_or_unsafe_package_fails_closed(tmp_path, monkeypatch, edit):
    parts = _parts(tmp_path, monkeypatch)
    if edit == "missing":
        del parts[package.METADATA]
    elif edit == "extra":
        parts["unknown-research-result.csv"] = b"synthetic"
    elif edit == "unexpected_directory":
        parts["other/"] = b""
    else:
        parts["../outside.txt"] = b"synthetic"
    with pytest.raises(ValueError):
        package.verify_package(_zip(tmp_path, parts))


def test_duplicate_name_cannot_hide_substituted_receipt(tmp_path, monkeypatch):
    parts = _parts(tmp_path, monkeypatch)
    path = _zip(tmp_path, parts)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr(package.ORIGINAL_RECEIPT, b"{}")
    with pytest.raises(ValueError, match="duplicate"):
        package.verify_package(path)


def test_saved_offline_receipt_must_match_exact_recomputed_content(tmp_path, monkeypatch):
    parts = _parts(tmp_path, monkeypatch)
    stored = json.loads(parts[package.OFFLINE_RECEIPT])
    stored["human_evaluation_ready"] = True
    parts[package.OFFLINE_RECEIPT] = json.dumps(stored).encode()
    with pytest.raises(ValueError, match="saved offline replay receipt differs"):
        package.verify_package(_zip(tmp_path, parts))


def test_saved_offline_receipt_rejects_noncanonical_utc_time(tmp_path, monkeypatch):
    parts = _parts(tmp_path, monkeypatch)
    stored = json.loads(parts[package.OFFLINE_RECEIPT])
    stored["reverified_at_utc"] = "2026-10-29T01:34:00Z"
    parts[package.OFFLINE_RECEIPT] = json.dumps(stored).encode()
    with pytest.raises(ValueError, match="explicit UTC"):
        package.verify_package(_zip(tmp_path, parts))


def test_mutated_original_receipt_fails_nested_replay(tmp_path, monkeypatch):
    parts = _parts(tmp_path, monkeypatch)
    saved = json.loads(parts[package.ORIGINAL_RECEIPT])
    saved["source_artifact_id"] = 7
    parts[package.ORIGINAL_RECEIPT] = json.dumps(saved).encode()
    with pytest.raises(ValueError, match="preserved verification receipt differs"):
        package.verify_package(_zip(tmp_path, parts))


def test_caller_supplied_package_hash_checked_not_claimed_as_historical(tmp_path, monkeypatch):
    path = _zip(tmp_path, _parts(tmp_path, monkeypatch))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = package.verify_package(path, expected_package_sha256=digest)
    assert receipt["caller_supplied_package_sha256_matched"] is True
    assert receipt["independent_historical_custody_authenticated"] is False
    with pytest.raises(ValueError, match="caller-supplied ZIP SHA-256"):
        package.verify_package(path, expected_package_sha256="0" * 64)


def test_oversized_outer_zip_rejected_before_parsing(tmp_path, monkeypatch):
    path = tmp_path / "too-large.zip"
    path.write_bytes(b"x" * (package.MAX_PACKAGE_BYTES + 1))
    with pytest.raises(ValueError, match="exceeds byte limit"):
        package.verify_package(path)


def test_symlink_package_rejected(tmp_path, monkeypatch):
    path = _zip(tmp_path, _parts(tmp_path, monkeypatch))
    link = tmp_path / "linked.zip"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="regular file"):
        package.verify_package(link)


def test_workflow_verifies_actual_retained_package_without_rerunning_treatments():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/preserved-canonical-package-audit.yml"
    ).read_text(encoding="utf-8")
    assert "actions: read" in workflow and "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "run_budget_main_study" not in workflow
    assert "run_pilot" not in workflow
    assert "12865837714/zip" in workflow
    assert "ea4930f9b897de86785ab12ccf0cab9d3781feb5e1d735f7aafa232c405b65f1" in workflow
    assert "f333623380526fa05dcb14110e7ec1fb72d2d0e2" in workflow
    assert "scripts.verify_preserved_canonical_package" in workflow
    assert workflow.index("Bind six frozen scientific files") < workflow.index(
        "Replay complete preserved package before publishing receipt"
    )
    assert "if-no-files-found: error" in workflow
