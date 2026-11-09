"""Downloaded qualified-report ZIP verification; synthetic archives only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import zipfile

import pytest

from scripts.assemble_qualified_main_study_report import assemble_qualified_report
from scripts.verify_qualified_reporting_copy import verify_qualified_copy
from scripts import verify_qualified_reporting_zip as verified_zip


@pytest.fixture
def source_pair(tmp_path: Path) -> dict[str, bytes]:
    report = tmp_path / "report.md"
    report.write_text(assemble_qualified_report(), encoding="utf-8")
    receipt = verify_qualified_copy(report_path=report)
    return {
        "qualified_main_study.md": report.read_bytes(),
        "verification_receipt.json": (
            json.dumps(receipt, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8"),
    }


def _write_zip(path: Path, members: list[tuple[str, bytes]]) -> Path:
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, body in members:
            output.writestr(name, body)
    return path


def test_original_two_file_zip_is_verified_without_extraction_or_modification(
    tmp_path, source_pair,
):
    path = _write_zip(tmp_path / "download.zip", list(source_pair.items()))
    original = path.read_bytes()
    result = verified_zip.verify_qualified_zip(zip_path=path)
    assert result["status"] == "downloaded_zip_matches_source_bound_qualified_reporting_pair"
    assert result["downloaded_zip_sha256"] == hashlib.sha256(original).hexdigest()
    assert result["zip_regular_member_count"] == 2
    assert result["independent_archive_custody_established"] is False
    assert result["original_reports_and_traces_independently_authenticated"] is False
    assert result["human_validation_performed"] is False
    assert path.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["download.zip"]


@pytest.mark.parametrize("change", [
    lambda members: members[:1],
    lambda members: members + [("surprise.txt", b"unsupported claim")],
    lambda members: members + [("extra/", b"")],
    lambda members: [("folder/qualified_main_study.md", members[0][1]), members[1]],
    lambda members: [("QUALIFIED_MAIN_STUDY.md", members[0][1]), members[1]],
    lambda members: members + [("../escape.txt", b"bad")],
    lambda members: members + [("qualified_main_study.md", b"duplicate")],
], ids=[
    "missing-receipt", "extra-file", "extra-directory", "nested-report",
    "case-alias", "traversal", "duplicate-member",
])
def test_unexpected_or_ambiguous_zip_inventory_fails(tmp_path, source_pair, change):
    path = _write_zip(tmp_path / "altered.zip", change(list(source_pair.items())))
    with pytest.raises(ValueError):
        verified_zip.verify_qualified_zip(zip_path=path)


@pytest.mark.parametrize("target", [
    "qualified_main_study.md", "verification_receipt.json",
])
def test_source_bound_pair_tampering_inside_well_formed_zip_fails(
    tmp_path, source_pair, target,
):
    source_pair[target] += b"\nUnsupported changed content.\n"
    path = _write_zip(tmp_path / "altered.zip", list(source_pair.items()))
    with pytest.raises(ValueError, match="(receipt differs|does not match source-verified assembly)"):
        verified_zip.verify_qualified_zip(zip_path=path)


def test_symlinked_zip_is_refused(tmp_path, source_pair):
    original = _write_zip(tmp_path / "original.zip", list(source_pair.items()))
    alias = tmp_path / "alias.zip"
    alias.symlink_to(original)
    with pytest.raises((OSError, ValueError)):
        verified_zip.verify_qualified_zip(zip_path=alias)


def test_oversize_zip_is_rejected_before_preflight(tmp_path, monkeypatch):
    path = tmp_path / "too-large.zip"
    path.write_bytes(b"x" * 33)
    monkeypatch.setattr(verified_zip, "MAX_DOWNLOAD_ZIP_BYTES", 32)
    monkeypatch.setattr(
        verified_zip, "audit_recovered_zip",
        lambda _: pytest.fail("oversized ZIP must not reach archive preflight"),
    )
    with pytest.raises(ValueError, match="dedicated archive safety"):
        verified_zip.verify_qualified_zip(zip_path=path)


def test_archive_change_after_preflight_is_detected(tmp_path, source_pair, monkeypatch):
    path = _write_zip(tmp_path / "changing.zip", list(source_pair.items()))
    original = verified_zip.audit_recovered_zip

    def mutate_after_preflight(archive):
        result = original(archive)
        archive.write_bytes(archive.read_bytes() + b"post-preflight-change")
        return result

    monkeypatch.setattr(verified_zip, "audit_recovered_zip", mutate_after_preflight)
    with pytest.raises(ValueError, match="changed after structural preflight"):
        verified_zip.verify_qualified_zip(zip_path=path)


def test_cli_outputs_explicit_non_custody_receipt(tmp_path, source_pair, monkeypatch, capsys):
    path = _write_zip(tmp_path / "download.zip", list(source_pair.items()))
    monkeypatch.setattr("sys.argv", ["qualified-report-zip", "--zip", str(path)])
    assert verified_zip.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["independent_archive_custody_established"] is False
    assert result["human_validation_performed"] is False
