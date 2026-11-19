"""Synthetic-only pre-install evidence-file capture checks; no research runs."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
import stat
import sys

import pytest

from scripts import verify_ci_early_gate_evidence as early


SHA = "a" * 40
RECEIPT = {"status": "synthetic-only", "schema_version": 1}


def _invoke(
    tmp_path: Path, monkeypatch, *, mode: str,
    receipt_path: Path | None = None,
) -> int:
    # Isolate the file-capture contract; test-source/transcript semantics are
    # independently covered by the dependency-free unittest suite.
    monkeypatch.setattr(early, "ROOT", tmp_path)
    monkeypatch.setattr(early, "build_receipt", lambda *_args, **_kw: RECEIPT)
    for name in early.SOURCES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic source")
    monkeypatch.setattr(sys, "argv", [
        "verify_ci_early_gate_evidence", "--mode", mode,
        "--log", str(tmp_path / "early.log"),
        "--receipt", str(receipt_path if receipt_path is not None else tmp_path / "receipt.json"),
        "--checkout-sha", SHA, "--run-id", "123", "--run-attempt", "1",
        "--event", "push", "--repository", "anupamking01/Ai-Researcher-Agent",
    ])
    return early.main()


def test_stable_regular_files_support_early_create_and_replay(tmp_path, monkeypatch):
    (tmp_path / "early.log").write_bytes(b"synthetic transcript\n")
    assert _invoke(tmp_path, monkeypatch, mode="create") == 0
    assert (tmp_path / "receipt.json").read_bytes() == early._canonical(RECEIPT)
    assert stat.S_IMODE((tmp_path / "receipt.json").stat().st_mode) == 0o600
    assert _invoke(tmp_path, monkeypatch, mode="verify") == 0


@pytest.mark.parametrize("mode", ["create", "verify"])
@pytest.mark.parametrize("alias", ["symlink", "hardlink"])
def test_early_cli_rejects_aliased_transcript_and_receipt(
    tmp_path, monkeypatch, capsys, mode, alias,
):
    (tmp_path / "early.log").write_bytes(b"synthetic transcript\n")
    (tmp_path / "receipt.json").write_bytes(early._canonical(RECEIPT))
    attacked = tmp_path / ("early.log" if mode == "create" else "receipt.json")
    outside = tmp_path / "outside"
    outside.write_bytes(attacked.read_bytes())
    attacked.unlink()
    if alias == "symlink":
        attacked.symlink_to(outside)
    else:
        os.link(outside, attacked)
    if mode == "create":
        (tmp_path / "receipt.json").unlink()
    with pytest.raises(SystemExit) as error:
        _invoke(tmp_path, monkeypatch, mode=mode)
    assert error.value.code == 1
    expected = "regular file" if alias == "symlink" else "exactly one filesystem link"
    assert expected in capsys.readouterr().err


def test_early_source_fingerprints_cover_imported_capture_dependencies():
    assert "scripts/verify_ci_test_evidence.py" in early.SOURCES
    assert "scripts/select_full_ci_shard.py" in early.SOURCES
    assert early.read_bounded_evidence.__module__ == "scripts.verify_ci_test_evidence"
    assert early.MAX_SOURCE_BYTES > 0


def test_early_create_rejects_symlinked_receipt_parent(tmp_path, monkeypatch, capsys):
    """A leaf-exclusive open must not publish under a redirected ancestor."""
    (tmp_path / "early.log").write_bytes(b"synthetic transcript\n")
    physical = tmp_path / "physical"
    physical.mkdir()
    (tmp_path / "redirect").symlink_to(physical, target_is_directory=True)
    with pytest.raises(SystemExit) as error:
        _invoke(
            tmp_path, monkeypatch, mode="create",
            receipt_path=tmp_path / "redirect" / "receipt.json",
        )
    assert error.value.code == 1
    assert "VERA EARLY CI RECEIPT: FAIL" in capsys.readouterr().err
    assert not (physical / "receipt.json").exists()


def test_early_create_rejects_receipt_parent_traversal(tmp_path, monkeypatch, capsys):
    """The output pathname must be canonical before any receipt is written."""
    (tmp_path / "early.log").write_bytes(b"synthetic transcript\n")
    (tmp_path / "subdir").mkdir()
    with pytest.raises(SystemExit) as error:
        _invoke(
            tmp_path, monkeypatch, mode="create",
            receipt_path=tmp_path / "subdir" / ".." / "receipt.json",
        )
    assert error.value.code == 1
    assert "VERA EARLY CI RECEIPT: FAIL" in capsys.readouterr().err
    assert not (tmp_path / "receipt.json").exists()


def test_early_create_refuses_existing_receipt_without_overwrite(tmp_path, monkeypatch, capsys):
    """Earlier pre-install evidence must not be replaced on re-execution."""
    (tmp_path / "early.log").write_bytes(b"synthetic transcript\n")
    existing = tmp_path / "receipt.json"
    existing.write_bytes(b"earlier retained evidence")
    with pytest.raises(SystemExit) as error:
        _invoke(tmp_path, monkeypatch, mode="create")
    assert error.value.code == 1
    assert "VERA EARLY CI RECEIPT: FAIL" in capsys.readouterr().err
    assert existing.read_bytes() == b"earlier retained evidence"

def test_async_unittest_cannot_pass_early_receipt_even_with_warnings_suppressed(tmp_path):
    """A coroutine in unittest.TestCase can report OK without running assert False."""
    source = (
        "import unittest\n"
        "class DependencyFreeEvaluationGate(unittest.TestCase):\n"
        + "".join(
            f"    def test_sync_{index}(self): assert True\n"
            for index in range(7)
        )
        + "    async def test_unawaited(self): assert False\n"
    )
    path = tmp_path / "test_evaluation_stdlib_gate.py"
    path.write_text(source, encoding="utf-8")
    observed = subprocess.run(
        [
            sys.executable, "-W", "ignore", "-m", "unittest", "discover",
            "-s", str(tmp_path), "-p", path.name, "-v",
        ],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert observed.returncode == 0, observed.stderr
    assert "test_unawaited (" in observed.stderr
    assert "Ran 8 tests" in observed.stderr
    assert observed.stderr.rstrip().endswith("OK")
    # The previous inventory accepted this source and could certify a
    # forged-looking all-OK transcript for a test whose body never executed.
    with pytest.raises(ValueError, match="async early diagnostic test methods"):
        early._declared_early_test_names(path.read_bytes())


def test_early_inventory_preserves_synchronous_tests_with_async_helpers():
    """Only coroutine *test methods* are forbidden, not unrelated helpers."""
    source = (
        "import unittest\n"
        "class DependencyFreeEvaluationGate(unittest.TestCase):\n"
        + "".join(
            f"    def test_sync_{index}(self): assert True\n"
            for index in range(7)
        )
        + "    async def helper_not_a_test(self): return None\n"
    ).encode("utf-8")
    assert early._declared_early_test_names(source) == [
        f"test_sync_{index}" for index in range(7)
    ]

@pytest.mark.parametrize("replacement", [
    "    test_shadowed = lambda self: None\n",
    "    test_shadowed: object = lambda self: None\n",
    "    test_shadowed, helper = (lambda self: None), 1\n",
])
def test_class_body_rebinding_cannot_certify_unexecuted_unittest_assertion(
    tmp_path, replacement,
):
    """unittest can pass an overwritten failing test under the original name."""
    source = (
        "import unittest\n"
        "class DependencyFreeEvaluationGate(unittest.TestCase):\n"
        + "".join(
            f"    def test_sync_{index}(self): assert True\n"
            for index in range(6)
        )
        + "    def test_shadowed(self): assert False\n"
        + replacement
    )
    path = tmp_path / "test_evaluation_stdlib_gate.py"
    path.write_text(source, encoding="utf-8")
    observed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(tmp_path),
         "-p", path.name, "-v"],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert observed.returncode == 0, observed.stderr
    assert "test_shadowed (" in observed.stderr
    assert "Ran 7 tests" in observed.stderr
    assert observed.stderr.rstrip().endswith("OK")
    with pytest.raises(ValueError, match="rebound by class-body assignment"):
        early._declared_early_test_names(path.read_bytes())


def test_unrelated_class_assignment_and_annotation_only_do_not_hide_tests():
    source = (
        "import unittest\n"
        "class DependencyFreeEvaluationGate(unittest.TestCase):\n"
        + "".join(
            f"    def test_sync_{index}(self): assert True\n"
            for index in range(7)
        )
        + "    helper_alias = lambda self: None\n"
        + "    test_sync_0: object\n"
    ).encode("utf-8")
    assert early._declared_early_test_names(source) == [
        f"test_sync_{index}" for index in range(7)
    ]
