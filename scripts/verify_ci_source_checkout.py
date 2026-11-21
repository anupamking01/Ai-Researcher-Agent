"""Fail-closed, offline check that CI tests the exact checked-out Git tree.

This checks tracked *working-tree bytes*, not just HEAD or the mutable index,
so assume-unchanged/skip-worktree entries cannot disguise changed source bytes.
It also rejects staged edits and nonignored untracked files. Run immediately
before and immediately after offline pytest; this is a local-runner check,
not independent attestation of GitHub or the execution interval.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[1]
COMMIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
CHUNK_BYTES = 1024 * 1024


def _git(root: Path, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *arguments], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        ).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("unable to inspect the local Git checkout") from exc


def _source_blob_digest(path: Path, mode: bytes) -> str:
    """Hash the actual checkout bytes with Git blob framing, not index data."""
    try:
        before = path.lstat()
        # A second name for the same inode can alter CI source bytes from
        # outside the checkout without creating an untracked repository file.
        if before.st_nlink != 1:
            raise ValueError("tracked source must be single-link (no hardlink aliases)")
        if mode == b"120000":
            if not stat.S_ISLNK(before.st_mode):
                raise ValueError("tracked symlink was replaced")
            payload = os.fsencode(os.readlink(path))
            after = path.lstat()
            digest = hashlib.sha1(b"blob %d\0" % len(payload) + payload).hexdigest()
        elif mode in (b"100644", b"100755"):
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("tracked regular file was replaced")
            if bool(before.st_mode & 0o111) != (mode == b"100755"):
                raise ValueError("tracked executable mode differs from Git tree")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            try:
                opened = os.fstat(fd)
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise ValueError("tracked file was replaced during open")
                if opened.st_nlink != 1:
                    raise ValueError("tracked source must be single-link (no hardlink aliases)")
                digest_state = hashlib.sha1()
                digest_state.update(b"blob %d\0" % opened.st_size)
                observed = 0
                while chunk := os.read(fd, CHUNK_BYTES):
                    observed += len(chunk)
                    digest_state.update(chunk)
                if observed != opened.st_size:
                    raise ValueError("tracked file changed length during read")
                after_fd = os.fstat(fd)
            finally:
                os.close(fd)
            if _generation(opened) != _generation(after_fd):
                raise ValueError("tracked file changed during read")
            digest = digest_state.hexdigest()
            after = path.lstat()
        else:
            raise ValueError("unsupported tracked Git entry mode")
        if _generation(before) != _generation(after):
            raise ValueError("tracked pathname changed during verification")
        return digest
    except (OSError, OverflowError) as exc:
        raise ValueError("tracked checkout path cannot be read safely") from exc


def _generation(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def verify_source_checkout(root: Path, *, expected_sha: str) -> int:
    """Require HEAD and every tracked file's current bytes to match Git HEAD.

    Reject nonignored untracked files too. Ignored build/cache output and
    mid-test changes restored before this gate remain outside its guarantee.
    """
    if type(expected_sha) is not str or not COMMIT_SHA.fullmatch(expected_sha):
        raise ValueError("expected checkout SHA must be 40 lowercase hex characters")
    root = root.resolve(strict=True)
    top = Path(os.fsdecode(_git(root, "rev-parse", "--show-toplevel").strip())).resolve()
    if top != root:
        raise ValueError("source verification must run from the Git repository root")
    head = _git(root, "rev-parse", "--verify", "HEAD").strip().decode("ascii")
    if head != expected_sha:
        raise ValueError("checked-out HEAD does not match expected workflow SHA")
    listing = _git(root, "ls-tree", "-r", "-z", expected_sha)
    rows = listing.split(b"\0")
    if rows.pop() != b"" or not rows:
        raise ValueError("missing or malformed Git HEAD source tree")
    for row in rows:
        try:
            metadata, raw_path = row.split(b"\t", 1)
            mode, kind, blob = metadata.split(b" ")
        except ValueError as exc:
            raise ValueError("malformed Git HEAD tree entry") from exc
        if kind != b"blob" or not re.fullmatch(rb"[0-9a-f]{40}", blob):
            raise ValueError("unsupported Git HEAD tree entry")
        name = os.fsdecode(raw_path)
        relative = Path(name)
        if (relative.is_absolute() or not relative.parts
                or any(part in ("..", ".", ".git") for part in relative.parts)):
            raise ValueError("unsafe tracked source path")
        path = root / relative
        for parent in relative.parents:
            if parent == Path("."):
                break
            if not stat.S_ISDIR((root / parent).lstat().st_mode):
                raise ValueError("tracked source parent is not a directory")
        if _source_blob_digest(path, mode) != blob.decode("ascii"):
            raise ValueError("tracked source bytes differ from expected Git commit")
    if _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise ValueError("checkout has staged changes or nonignored untracked files")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--phase", choices=("before-tests", "after-tests"), required=True)
    args = parser.parse_args()
    try:
        count = verify_source_checkout(ROOT, expected_sha=args.checkout_sha)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(1, f"VERA SOURCE CHECKOUT ({args.phase}): FAIL: {exc}\n")
    print(f"VERA SOURCE CHECKOUT ({args.phase}): PASS ({count} exact Git blobs; local runner only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
