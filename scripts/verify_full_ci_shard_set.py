"""Independently replay all sixteen retained offline CI shard evidence bundles.

This verifies complete *local* coverage of the source-tree module inventory at
one externally specified GitHub run identity. It does not attest GitHub's
runner, actual test execution, network isolation, or research artifacts.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
import stat
from pathlib import Path

from scripts import select_full_ci_shard as selector
from scripts import verify_ci_early_gate_evidence as early
from scripts import verify_ci_source_checkout as source_checker
from scripts import verify_ci_test_evidence as producer
from scripts import verify_retained_ci_test_evidence as replay

MAX_AGGREGATE_RECEIPT_BYTES = 256 * 1024

EVIDENCE_FILES = frozenset({
    "vera-offline-tests.log",
    "vera-offline-test-receipt.json",
    "vera-offline-test-modules.txt",
})



@contextmanager
def _pinned_directory_chain(path: Path):
    """Reject indirect aliases and observed directory replacement during replay.

    No-follow descriptor-relative walks pin each directory component while
    downloaded evidence is inspected. This is present-day path consistency,
    not GitHub attestation or an absolute defense against concurrent races.
    """
    path = Path(path)
    if ".." in path.parts:
        raise ValueError("CI evidence path must not traverse parent components")
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("CI evidence directory custody requires no-follow opens")
    absolute = Path(os.path.abspath(path))
    flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
             | getattr(os, "O_CLOEXEC", 0))
    opened: list[tuple[int | None, str | None, int]] = []
    try:
        anchor_fd = os.open(absolute.anchor, flags)
        opened.append((None, None, anchor_fd))
        for component in absolute.parts[1:]:
            parent_fd = opened[-1][2]
            fd = os.open(component, flags, dir_fd=parent_fd)
            opened.append((parent_fd, component, fd))
        try:
            yield
        finally:
            # A failed evidence read can be caused by a swapped ancestor.
            # Verify pinned custody even when the consumer is unwinding a
            # different error, rather than masking the observed replacement.
            for parent_fd, component, fd in opened[1:]:
                pinned = os.fstat(fd)
                visible = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(visible.st_mode)
                    or (pinned.st_dev, pinned.st_ino, pinned.st_mode)
                    != (visible.st_dev, visible.st_ino, visible.st_mode)
                ):
                    raise ValueError("CI evidence directory changed during replay")
    except OSError as exc:
        raise ValueError("CI evidence directory is missing, aliased, or changed") from exc
    finally:
        for _, _, fd in reversed(opened):
            os.close(fd)


def _require_exact_entries(directory: Path, expected: set[str] | frozenset[str], *, message: str) -> None:
    """Fail on the first surplus downloaded entry, without unbounded listing.

    Retained artifact directories are untrusted local input. Materializing a
    set from every name before comparing it to the expected fixed inventory
    permits a huge directory to consume unbounded memory. The seventeenth shard or
    fourth file is already proof of invalid evidence.
    """
    observed: set[str] = set()
    with os.scandir(directory) as entries:
        for entry in entries:
            if len(observed) >= len(expected):
                raise ValueError(message)
            observed.add(entry.name)
    if observed != expected:
        raise ValueError(message)


def verify_early_diagnostic_set(
    evidence_root: Path, *, checkout_sha: str, run_id: str,
    run_attempt: str, event: str,
) -> dict:
    """Replay *all* retained pre-install diagnostics at the same run identity.

    Independent per-job early replay is not enough to establish that the
    archived diagnostic set is complete. This operates only on retained bytes,
    never invokes unittest, pytest, treatments, evaluators or model providers.
    """
    evidence_root = Path(evidence_root)
    expected_dirs = {f"shard-{index}" for index in range(selector.SHARDS)}
    expected_files = frozenset({
        "vera-stdlib-evaluation.log", "vera-stdlib-evaluation-receipt.json",
    })
    sources = {
        name: producer.read_bounded_evidence(
            producer.ROOT / name, maximum=early.MAX_SOURCE_BYTES,
            label=f"early diagnostic source {name}",
        )
        for name in early.SOURCES
    }
    per_shard = []
    with ExitStack() as pins:
        pins.enter_context(_pinned_directory_chain(evidence_root))
        _require_exact_entries(
            evidence_root, expected_dirs,
            message="missing or unexpected early diagnostic shard directory",
        )
        for index in range(selector.SHARDS):
            folder = evidence_root / f"shard-{index}"
            pins.enter_context(_pinned_directory_chain(folder))
            _require_exact_entries(
                folder, expected_files,
                message=f"shard {index} early diagnostic files missing or unexpected",
            )
            log = producer.read_bounded_evidence(
                folder / "vera-stdlib-evaluation.log",
                maximum=early.MAX_LOG_BYTES,
                label=f"shard {index} early diagnostic log",
            )
            receipt = producer.read_bounded_evidence(
                folder / "vera-stdlib-evaluation-receipt.json",
                maximum=early.MAX_RECEIPT_BYTES,
                label=f"shard {index} early diagnostic receipt",
            )
            expected = early.build_receipt(
                log, sha=checkout_sha, run_id=run_id,
                attempt=run_attempt, event=event,
                repository="anupamking01/Ai-Researcher-Agent",
                sources=sources,
            )
            # Require the exact canonical producer bytes, not an independently
            # edited equivalent JSON object or a spoofed success declaration.
            if receipt != early._canonical(expected):
                raise ValueError(
                    f"shard {index} early diagnostic receipt disagrees with "
                    "the retained log, source, or run identity"
                )
            per_shard.append({
                "shard": index,
                "passed_tests": expected["passed_tests"],
                "log_sha256": hashlib.sha256(log).hexdigest(),
                "receipt_sha256": hashlib.sha256(receipt).hexdigest(),
            })
    return {
        "status": "complete_sixteen_early_diagnostics_locally_consistent_not_attested",
        "shards_verified": len(per_shard),
        "per_shard": per_shard,
        "runner_or_original_research_source_attested": False,
    }


def verify_shard_set(
    evidence_root: Path, *, checkout_sha: str, run_id: str,
    run_attempt: str, event: str, dependency_bytes: dict[str, bytes],
    early_evidence_root: Path | None = None,
) -> dict:
    """Replay only while the complete evidence-directory namespace stays pinned."""
    with ExitStack() as pins:
        pins.enter_context(_pinned_directory_chain(evidence_root))
        result = _verify_pinned_shard_set(
            evidence_root, checkout_sha=checkout_sha, run_id=run_id,
            run_attempt=run_attempt, event=event,
            dependency_bytes=dependency_bytes, pins=pins,
        )
        if early_evidence_root is None:
            result["preinstall_diagnostics"] = "not_replayed"
        else:
            result["preinstall_diagnostics"] = verify_early_diagnostic_set(
                early_evidence_root, checkout_sha=checkout_sha,
                run_id=run_id, run_attempt=run_attempt, event=event,
            )
        return result


def _verify_pinned_shard_set(
    evidence_root: Path, *, checkout_sha: str, run_id: str,
    run_attempt: str, event: str, dependency_bytes: dict[str, bytes],
    pins: ExitStack,
) -> dict:
    """Verify every shard with independent identity, then its global coverage."""
    evidence_root = Path(evidence_root)
    if evidence_root.is_symlink() or not evidence_root.is_dir():
        raise ValueError("evidence root must be a real directory")
    expected_dirs = {f"shard-{index}" for index in range(selector.SHARDS)}
    _require_exact_entries(
        evidence_root, expected_dirs,
        message="missing or unexpected CI shard evidence directory",
    )

    all_modules: list[str] = []
    per_shard = []
    counts: dict[str, int] = {}
    for index in range(selector.SHARDS):
        folder = evidence_root / f"shard-{index}"
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError(f"shard {index} evidence directory is not real")
        pins.enter_context(_pinned_directory_chain(folder))
        _require_exact_entries(
            folder, EVIDENCE_FILES,
            message=f"shard {index} evidence files are incomplete or unexpected",
        )
        log = producer.read_bounded_evidence(
            folder / "vera-offline-tests.log",
            maximum=producer.MAX_LOG_BYTES, label=f"shard {index} log",
        )
        receipt_bytes = producer.read_bounded_evidence(
            folder / "vera-offline-test-receipt.json",
            maximum=replay.MAX_RECEIPT_BYTES, label=f"shard {index} receipt",
        )
        selected_bytes = producer.read_bounded_evidence(
            folder / "vera-offline-test-modules.txt",
            maximum=producer.MAX_SELECTED_MODULES_BYTES,
            label=f"shard {index} module inventory",
        )
        receipt = replay.verify_retained_evidence(
            log, receipt_bytes, checkout_sha=checkout_sha, run_id=run_id,
            run_attempt=run_attempt, event=event,
            dependency_bytes=dependency_bytes, selected_modules=selected_bytes,
            shard=index,
        )
        modules = selected_bytes.decode("utf-8").splitlines()
        if len(modules) != receipt["full_ci_selected_module_count"]:
            raise ValueError(f"shard {index} module count disagrees with receipt")
        all_modules.extend(modules)
        for name, value in receipt["test_counts"].items():
            counts[name] = counts.get(name, 0) + value
        per_shard.append({
            "shard": index,
            "n_modules": len(modules),
            "n_passed": receipt["test_counts"]["passed"],
            "log_sha256": hashlib.sha256(log).hexdigest(),
            "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "selected_modules_sha256": hashlib.sha256(selected_bytes).hexdigest(),
        })

    discovered = selector.discover_modules(producer.ROOT)
    selector.verify_partition(discovered)
    if len(all_modules) != len(set(all_modules)) or sorted(all_modules) != list(discovered):
        raise ValueError("sixteen retained shards do not cover each source test module exactly once")
    return {
        "status": "complete_sixteen_shard_local_replay_consistent_not_independently_attested",
        "checkout_sha": checkout_sha,
        "workflow_event": event,
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "shards_verified": len(per_shard),
        "source_test_modules_covered": len(discovered),
        "aggregate_test_counts": dict(sorted(counts.items())),
        "per_shard": per_shard,
        "experimental_treatments_or_evaluators_run": False,
        "human_validation_performed": False,
    }


def canonical_aggregate_receipt(result: dict) -> bytes:
    """Serialize the exact bytes emitted by the aggregate workflow job."""
    return (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")


def verify_retained_aggregate_receipt(result: dict, path: Path) -> None:
    """Require the provider-retained aggregate to equal independent full replay."""
    if not isinstance(result.get("preinstall_diagnostics"), dict):
        raise ValueError("retained aggregate comparison requires all early diagnostics")
    retained = producer.read_bounded_evidence(
        path, maximum=MAX_AGGREGATE_RECEIPT_BYTES,
        label="retained aggregate replay receipt",
    )
    if retained != canonical_aggregate_receipt(result):
        raise ValueError("retained aggregate receipt disagrees with independent replay")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--early-evidence-root", type=Path)
    parser.add_argument("--retained-aggregate-receipt", type=Path,
                        help="compare the downloaded aggregate JSON to the full independent replay")
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument(
        "--event", required=True,
        choices=("push", "pull_request", "workflow_dispatch"),
    )
    args = parser.parse_args()
    if args.retained_aggregate_receipt is not None and args.early_evidence_root is None:
        parser.error("--retained-aggregate-receipt requires --early-evidence-root")
    try:
        # Require exact checkout bytes, not just a matching branch name/HEAD.
        source_checker.verify_source_checkout(
            producer.ROOT, expected_sha=args.checkout_sha
        )
        result = verify_shard_set(
            args.evidence_root, checkout_sha=args.checkout_sha,
            run_id=args.run_id, run_attempt=args.run_attempt, event=args.event,
            dependency_bytes={
                name: (producer.ROOT / name).read_bytes()
                for name in ("requirements.txt", "requirements-ci.lock")
            },
            early_evidence_root=args.early_evidence_root,
        )
        if args.retained_aggregate_receipt is not None:
            verify_retained_aggregate_receipt(result, args.retained_aggregate_receipt)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(1, f"VERA FULL CI SHARD SET: FAIL: {exc}\n")
    # Keep the historical aggregate bytes stable in both modes.
    print(canonical_aggregate_receipt(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
