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


def test_alternate_index_cannot_hide_staged_only_edit(checkout, monkeypatch):
    root, sha = checkout
    clean_index = root / ".git" / "alternate-clean-index"
    clean_index.write_bytes((root / ".git" / "index").read_bytes())
    source = root / "source.py"
    original = source.read_bytes()
    source.write_bytes(b"print('staged only')\n")
    _git(root, "add", "source.py")
    source.write_bytes(original)
    assert _git(root, "status", "--porcelain") == "MM source.py"
    with pytest.raises(ValueError, match="staged changes"):
        verify_source_checkout(root, expected_sha=sha)

    # Git still reports the pinned HEAD and sees the original working bytes,
    # but status examines a clean alternate index, not the real staged edit.
    monkeypatch.setenv("GIT_INDEX_FILE", str(clean_index))
    assert _git(root, "rev-parse", "HEAD") == sha
    assert _git(root, "status", "--porcelain") == ""
    with pytest.raises(ValueError, match="ambient Git storage overrides.*GIT_INDEX_FILE"):
        verify_source_checkout(root, expected_sha=sha)
    monkeypatch.delenv("GIT_INDEX_FILE")
    assert _git(root, "status", "--porcelain") == "MM source.py"
    _git(root, "reset", "--hard", sha)
    assert verify_source_checkout(root, expected_sha=sha) == 1


@pytest.mark.parametrize("variable", [
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
])
@pytest.mark.parametrize("value", ["", "/unused-alternate-git-storage"])
def test_ambient_git_storage_selector_fails_before_inspection(
    checkout, monkeypatch, variable, value
):
    root, sha = checkout
    monkeypatch.setenv(variable, value)
    def unexpected_git(*args, **kwargs):
        pytest.fail("Git inspection must not run with redirected storage")
    monkeypatch.setattr("scripts.verify_ci_source_checkout._git", unexpected_git)
    with pytest.raises(ValueError, match=f"ambient Git storage overrides.*{variable}"):
        verify_source_checkout(root, expected_sha=sha)


def test_assume_unchanged_cannot_hide_modified_source(checkout):
    root, sha = checkout
    _git(root, "update-index", "--assume-unchanged", "source.py")
    (root / "source.py").write_bytes(b"print('hidden')\n")
    assert _git(root, "status", "--porcelain") == ""
    with pytest.raises(ValueError, match="source bytes differ"):
        verify_source_checkout(root, expected_sha=sha)


@pytest.mark.parametrize("object_kind", ["commit", "tree"])
def test_git_replacement_objects_cannot_redirect_pinned_tree(checkout, object_kind):
    root, sha = checkout
    (root / "source.py").write_bytes(b"print('replacement')\n")
    _git(root, "commit", "-qam", "replacement fixture")
    alternative = _git(root, "rev-parse", "HEAD")
    if object_kind == "tree":
        original_object = _git(root, "rev-parse", f"{sha}^{{tree}}")
        replacement_object = _git(root, "rev-parse", f"{alternative}^{{tree}}")
    else:
        original_object, replacement_object = sha, alternative
    _git(root, "replace", original_object, replacement_object)
    _git(root, "checkout", "-q", "--detach", sha)
    # Default Git inspection sees a clean, substituted tree at the old SHA.
    assert _git(root, "rev-parse", "HEAD") == sha
    assert _git(root, "status", "--porcelain") == ""
    assert (root / "source.py").read_bytes() == b"print('replacement')\n"
    assert _git(root, "ls-tree", sha) != _git(
        root, "--no-replace-objects", "ls-tree", sha
    )
    with pytest.raises(ValueError, match="source bytes differ"):
        verify_source_checkout(root, expected_sha=sha)
    # Restore the literal tree without removing the replacement ref.
    _git(root, "--no-replace-objects", "reset", "--hard", sha)
    assert verify_source_checkout(root, expected_sha=sha) == 1


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


@pytest.mark.parametrize("target_kind", ["external_absolute", "external_relative", "ignored", "tracked"])
def test_tracked_symlink_cannot_extend_verified_source_domain(checkout, target_kind):
    root, _ = checkout
    if target_kind == "tracked":
        target = root / "source.py"
        link_target = "source.py"
    elif target_kind == "ignored":
        target = root / "ignored.py"
        (root / ".gitignore").write_text("ignored.py\n")
        _git(root, "add", ".gitignore")
        link_target = "ignored.py"
    else:
        target = root.parent / f"{root.name}-external.py"
        link_target = str(target) if target_kind == "external_absolute" else f"../{target.name}"
    if target_kind != "tracked":
        target.write_bytes(b"print('initial')\n")
    pointer = root / "pointer.py"
    pointer.symlink_to(link_target)
    _git(root, "add", "pointer.py")
    _git(root, "commit", "-qm", "add tracked symlink")
    sha = _git(root, "rev-parse", "HEAD")
    assert _git(root, "status", "--porcelain") == ""
    if target_kind != "tracked":
        # The committed link text is unchanged, but code reached by reading it is not.
        target.write_bytes(b"print('substituted')\n")
        assert pointer.read_bytes() == b"print('substituted')\n"
        assert _git(root, "status", "--porcelain") == ""
    with pytest.raises(ValueError, match="tracked symlinks are unsupported"):
        verify_source_checkout(root, expected_sha=sha)
    # Ordinary exact regular-file checkouts remain accepted.
    _git(root, "rm", "pointer.py")
    _git(root, "commit", "-qm", "remove tracked symlink")
    assert verify_source_checkout(root, expected_sha=_git(root, "rev-parse", "HEAD")) == (
        2 if target_kind == "ignored" else 1
    )
