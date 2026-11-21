"""Offline synthetic Git repositories verify the exact-source CI gate."""
from pathlib import Path
import subprocess

import pytest
import yaml

from scripts.verify_ci_source_checkout import verify_source_checkout


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def checkout(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "VERA Synthetic Fixture")
    (tmp_path / "source.py").write_bytes(b"print('source')\n")
    _git(tmp_path, "add", "source.py")
    _git(tmp_path, "commit", "-qm", "synthetic fixture")
    return tmp_path, _git(tmp_path, "rev-parse", "HEAD")


def test_clean_exact_sha_and_tracked_bytes_pass(checkout):
    root, sha = checkout
    assert verify_source_checkout(root, expected_sha=sha) == 1


def test_wrong_expected_revision_fails(checkout):
    root, _ = checkout
    with pytest.raises(ValueError, match="HEAD does not match"):
        verify_source_checkout(root, expected_sha="b" * 40)


@pytest.mark.parametrize("bad_sha", ["f" * 39, "G" * 40, "f" * 41])
def test_malformed_revision_is_rejected(checkout, bad_sha):
    with pytest.raises(ValueError, match="40 lowercase hex"):
        verify_source_checkout(checkout[0], expected_sha=bad_sha)


def test_unstaged_source_edit_is_rejected(checkout):
    root, sha = checkout
    (root / "source.py").write_bytes(b"print('other')\n")
    with pytest.raises(ValueError, match="source bytes differ"):
        verify_source_checkout(root, expected_sha=sha)


def test_staged_source_edit_is_rejected(checkout):
    root, sha = checkout
    (root / "source.py").write_bytes(b"print('staged')\n")
    _git(root, "add", "source.py")
    with pytest.raises(ValueError, match="source bytes differ"):
        verify_source_checkout(root, expected_sha=sha)


def test_assume_unchanged_cannot_hide_modified_source(checkout):
    root, sha = checkout
    _git(root, "update-index", "--assume-unchanged", "source.py")
    (root / "source.py").write_bytes(b"print('hidden')\n")
    assert _git(root, "status", "--porcelain") == ""
    with pytest.raises(ValueError, match="source bytes differ"):
        verify_source_checkout(root, expected_sha=sha)


def test_nonignored_untracked_file_is_rejected(checkout):
    root, sha = checkout
    (root / "unexpected.py").write_text("print('untracked')")
    with pytest.raises(ValueError, match="untracked files"):
        verify_source_checkout(root, expected_sha=sha)


def test_executable_bit_change_is_rejected(checkout):
    root, sha = checkout
    (root / "source.py").chmod(0o755)
    with pytest.raises(ValueError, match="executable mode"):
        verify_source_checkout(root, expected_sha=sha)


def test_symlink_substitution_is_rejected(checkout):
    root, sha = checkout
    (root / "source.py").unlink()
    (root / "source.py").symlink_to("other.py")
    with pytest.raises(ValueError, match="regular file was replaced"):
        verify_source_checkout(root, expected_sha=sha)


def test_out_of_checkout_hardlink_to_identical_source_is_rejected(checkout):
    root, sha = checkout
    # No edit to source.py or untracked in-repository path exists: a hash-only
    # gate and git status both accept it, but an external writer has an alias.
    alias = root.parent / f"{root.name}-external-source-alias"
    try:
        alias.hardlink_to(root / "source.py")
        assert _git(root, "status", "--porcelain") == ""
        with pytest.raises(ValueError, match="single-link"):
            verify_source_checkout(root, expected_sha=sha)
    finally:
        alias.unlink(missing_ok=True)


def test_out_of_checkout_hardlink_to_tracked_symlink_is_rejected(checkout):
    root, _ = checkout
    (root / "pointer.py").symlink_to("source.py")
    _git(root, "add", "pointer.py")
    _git(root, "commit", "-qm", "add tracked symlink")
    sha = _git(root, "rev-parse", "HEAD")
    alias = root.parent / f"{root.name}-external-link-alias"
    try:
        # POSIX hardlinks to symlink inodes are possible without changing
        # the symlink target stored in Git or the checkout status.
        import os
        try:
            os.link(root / "pointer.py", alias, follow_symlinks=False)
        except (OSError, NotImplementedError):
            pytest.skip("platform does not support hardlinks to symlink inodes")
        assert alias.is_symlink()
        assert _git(root, "status", "--porcelain") == ""
        with pytest.raises(ValueError, match="single-link"):
            verify_source_checkout(root, expected_sha=sha)
    finally:
        alias.unlink(missing_ok=True)


def test_workflow_gates_both_sides_of_tests_before_evidence_publication():
    workflow = yaml.load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/tests.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["unit-tests"]["steps"]
    names = [step.get("name", "") for step in steps]
    before = names.index("Verify exact source checkout before tests")
    tests = names.index("Run offline unit tests")
    after = names.index("Verify exact source checkout after tests")
    producer = names.index("Bind exact-commit offline test evidence")
    replay = names.index("Replay exact-commit offline test evidence before upload")
    upload = next(i for i, name in enumerate(names) if name.startswith("Retain source-bound offline test"))
    assert before < tests < after < producer < replay < upload
    for index, phase in ((before, "before-tests"), (after, "after-tests")):
        step = steps[index]
        assert "continue-on-error" not in step
        assert step["run"].strip().splitlines() == [
            f'python -m scripts.verify_ci_source_checkout --checkout-sha "$GITHUB_SHA" --phase {phase}'
        ]
