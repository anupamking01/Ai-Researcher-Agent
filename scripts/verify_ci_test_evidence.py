"""Create a source-bound, diagnostic receipt for one successful offline CI run.

The GitHub job must run the firewalled pytest wrapper with bash pipefail and
tee the exact output. This verifier audits that completed local output; it
cannot independently attest the runner or the correctness of tests.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import stat

from scripts import select_full_ci_shard as shard_selector

MAX_LOG_BYTES = 16 * 1024 * 1024
MAX_SELECTED_MODULES_BYTES = 64 * 1024
FIREWALL_MARKER = (
    "Offline pytest egress isolation active "
    "(IPv4 + IPv6; loopback allowed; policy inspected)."
)
# Pytest -q emits a bare summary; -vv emits the same summary bracketed
# by '=' runs. Require *both* bars if either is present, and preserve the
# unique, physically last success-line requirement in build_receipt().
SUMMARY = re.compile(
    r"(?:(?P<ruler>={3,}) )?"
    r"(?P<counts>[1-9][0-9]* passed(?:, [0-9]+ "
    r"(?:skipped|xfailed|xpassed|warnings?|deselected))*) "
    r"in (?P<elapsed>[0-9]+(?:\.[0-9]+)?)s"
    r"(?: \([0-9:.]+\))?"
    r"(?(ruler) ={3,})"
)
# Verbose full-suite logs expose both collected test cases and per-case
# completion records. Validate all three independent representations (collection,
# progress, footer) rather than trusting only an otherwise green footer.
VERBOSE_COLLECTION = re.compile(
    r"collecting \.\.\. collected (?P<count>[1-9][0-9]*) items"
)
# Parse the short terminal suffix from the right: pytest parameter IDs may
# contain hundreds of KiB of whitespace (see CI shard 4, 17 Nov 2026).
# A lazy node-ID regex followed by \\s+ was quadratic on those valid IDs.
VERBOSE_PROGRESS_SUFFIX = re.compile(r"\[\s*[0-9]+%\]")
VERBOSE_TERMINAL_STATUSES = frozenset(
    ("PASSED", "SKIPPED", "XFAIL", "XPASS", "FAILED", "ERROR")
)

REQUIRED_ENV = (
    "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT", "GITHUB_EVENT_NAME",
)
ROOT = Path(__file__).resolve().parents[1]


def read_bounded_evidence(path: Path, *, maximum: int, label: str) -> bytes:
    """Capture single-link CI evidence through held, no-follow ancestor FDs.

    A stable leaf descriptor is insufficient when an intermediate pathname
    redirects to another evidence tree or is replaced during capture. Recheck
    the entire ancestor chain before accepting the exact retained bytes.
    This verifies local pathname continuity, not independent runner custody.
    """
    if type(maximum) is not int or maximum < 1:
        raise ValueError("invalid evidence capture limit")
    path = Path(path)
    if ".." in path.parts:
        raise ValueError(f"{label} path may not contain parent traversal")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError(f"{label} cannot enforce no-follow ancestor capture")
    absolute = path.absolute()
    dir_flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                 | getattr(os, "O_CLOEXEC", 0))
    file_flags = (os.O_RDONLY | os.O_NOFOLLOW
                  | getattr(os, "O_CLOEXEC", 0)
                  | getattr(os, "O_NONBLOCK", 0))

    def generation(st):
        return (st.st_dev, st.st_ino, st.st_mode, st.st_size,
                st.st_mtime_ns, st.st_ctime_ns)

    def file_identity(st):
        return (*generation(st), st.st_nlink)

    try:
        with ExitStack() as stack:
            parent_fd = os.open(absolute.anchor, dir_flags)
            stack.callback(os.close, parent_fd)
            ancestors = []
            for component in absolute.parts[1:-1]:
                child_fd = os.open(component, dir_flags, dir_fd=parent_fd)
                stack.callback(os.close, child_fd)
                if generation(os.fstat(child_fd)) != generation(os.stat(
                    component, dir_fd=parent_fd, follow_symlinks=False
                )):
                    raise ValueError(f"{label} parent directory changed before capture")
                ancestors.append((parent_fd, component, child_fd))
                parent_fd = child_fd

            path_before = os.stat(
                absolute.name, dir_fd=parent_fd, follow_symlinks=False
            )
            fd = os.open(absolute.name, file_flags, dir_fd=parent_fd)
            stack.callback(os.close, fd)
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode)
                    or not stat.S_ISREG(path_before.st_mode)):
                raise ValueError(f"{label} must be a regular file")
            if before.st_nlink != 1:
                raise ValueError(f"{label} must have exactly one filesystem link")
            if file_identity(path_before) != file_identity(before):
                raise ValueError(f"{label} pathname changed before capture")
            if before.st_size > maximum:
                raise ValueError(f"{label} exceeds size limit")

            # Retain the descriptor while reading bounded bytes; do not follow
            # a new pathname if either the file or an ancestor is replaced.
            with os.fdopen(fd, "rb", closefd=False) as stream:
                captured = stream.read(maximum + 1)
            after = os.fstat(fd)
            try:
                path_after = os.stat(
                    absolute.name, dir_fd=parent_fd, follow_symlinks=False
                )
            except OSError as exc:
                raise ValueError(f"{label} changed during capture") from exc
            if (file_identity(before) != file_identity(after)
                    or file_identity(after) != file_identity(path_after)
                    or len(captured) != before.st_size):
                raise ValueError(f"{label} changed during capture")
            if len(captured) > maximum:
                raise ValueError(f"{label} exceeds size limit")

            for holder_fd, component, child_fd in ancestors:
                try:
                    linked = os.stat(
                        component, dir_fd=holder_fd, follow_symlinks=False
                    )
                except OSError as exc:
                    raise ValueError(
                        f"{label} parent directory changed during capture"
                    ) from exc
                if generation(os.fstat(child_fd)) != generation(linked):
                    raise ValueError(f"{label} parent directory changed during capture")
            return captured
    except OSError as exc:
        raise ValueError(f"{label} cannot be opened as a regular file") from exc


def _verify_full_ci_selection(
    log_text: str, *, selected_modules: bytes, shard: int, checkout_sha: str,
) -> dict:
    """Bind the saved shard inventory to this exact checkout and test transcript.

    This is a local source/log consistency check, not independent proof that
    every pytest test function executed or that the GitHub runner was honest.
    """
    if type(shard) is not int or not 0 <= shard < shard_selector.SHARDS:
        raise ValueError("invalid full CI shard identity")
    if (type(selected_modules) is not bytes or
            not 0 < len(selected_modules) <= MAX_SELECTED_MODULES_BYTES):
        raise ValueError("full CI selected-module inventory missing or oversized")
    discovered = shard_selector.discover_modules(ROOT)
    shard_selector.verify_partition(discovered)
    expected = shard_selector.select_shard(discovered, shard=shard)
    expected_bytes = ("".join(f"{name}\n" for name in expected)).encode("utf-8")
    if selected_modules != expected_bytes:
        raise ValueError("full CI selected-module inventory differs from checkout")
    header = (
        f"VERA full-suite shard {shard}/{shard_selector.SHARDS}; "
        f"selected {len(expected)} modules; checkout {checkout_sha}"
    )
    # build_receipt already validates physical LF/CRLF framing. Match shard
    # anchors on normalized record text, but hash the original log bytes.
    lines = [line.removesuffix("\r") for line in log_text.split("\n")]
    anchors = [i for i, line in enumerate(lines) if line == header]
    if len(anchors) != 1 or lines[anchors[0]:anchors[0] + 1 + len(expected)] != [
        header, *expected,
    ]:
        raise ValueError("full CI selected-module inventory is not in the test log")
    return {
        "full_ci_shard": shard,
        "full_ci_total_modules": len(discovered),
        "full_ci_selected_module_count": len(expected),
        "full_ci_selected_modules_sha256": hashlib.sha256(selected_modules).hexdigest(),
    }


def _parse_verbose_completion(line: str) -> tuple[str, str] | None:
    """Parse a pytest completion in linear time without truncating its node ID.

    A historical parameterized node ID included more than 500 KiB of spaces.
    Splitting after the rightmost progress bracket avoids quadratic regex
    backtracking while preserving valid parameter IDs containing whitespace.
    """
    bracket = line.rfind("[")
    if bracket < 0 or VERBOSE_PROGRESS_SUFFIX.fullmatch(line[bracket:]) is None:
        return None
    parts = line[:bracket].rstrip().rsplit(None, 1)
    if len(parts) != 2 or parts[1] not in VERBOSE_TERMINAL_STATUSES:
        return None
    return parts[0], parts[1]


def _verify_verbose_full_ci_progress(
    test_output_lines: list[str], *, expected: dict[str, int],
    allowed_modules: frozenset[str] | None = None,
) -> None:
    """Check collected items against source-bound, unique pytest node IDs.

    This validates the captured pytest transcript's internal consistency.
    It does not independently authenticate the runner or discover omitted
    tests that never appeared in pytest collection.
    """
    collections = [
        (index, match)
        for index, line in enumerate(test_output_lines)
        if (match := VERBOSE_COLLECTION.fullmatch(line))
    ]
    if len(collections) != 1:
        raise ValueError("full CI verbose pytest collection record missing or ambiguous")
    collected_position, collection = collections[0]
    observed: dict[str, int] = {}
    seen_nodes: set[str] = set()
    for index, line in enumerate(test_output_lines):
        completion = _parse_verbose_completion(line)
        if completion is None:
            continue
        if index <= collected_position:
            raise ValueError("full CI test completion precedes collection")
        nodeid, status = completion
        module, separator, case = nodeid.partition("::")
        if (not separator or not case or not module.startswith("tests/")
                or not module.endswith(".py")
                or (allowed_modules is not None and module not in allowed_modules)):
            raise ValueError("full CI pytest completion node is outside selected modules")
        if nodeid in seen_nodes:
            raise ValueError("full CI pytest duplicate completion node ID")
        seen_nodes.add(nodeid)
        observed[status] = observed.get(status, 0) + 1
    if sum(observed.values()) != int(collection["count"]):
        raise ValueError(
            "full CI verbose pytest collected and completed test counts disagree"
        )
    summary_outcomes = {
        "PASSED": expected.get("passed", 0),
        "SKIPPED": expected.get("skipped", 0),
        "XFAIL": expected.get("xfailed", 0),
        "XPASS": expected.get("xpassed", 0),
    }
    if observed != {
        status: count for status, count in summary_outcomes.items() if count
    }:
        raise ValueError(
            "full CI pytest per-test completion outcomes differ from terminal summary"
        )


def build_receipt(log: bytes, *, context: dict[str, str],
                  checkout_sha: str, dependency_bytes: dict[str, bytes],
                  selected_modules: bytes | None = None,
                  shard: int | None = None) -> dict:
    """Do not publish a PASS for absent, ambiguous, or failing pytest output."""
    if type(log) is not bytes or not 0 < len(log) <= MAX_LOG_BYTES:
        raise ValueError("offline test log is missing or exceeds size limit")
    try:
        decoded = log.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("offline test log is not UTF-8") from exc
    # Preserve *physical* LF/CRLF records. str.splitlines() would also accept
    # Unicode separators and bare CR as forged pytest/runner log boundaries.
    if not decoded.endswith("\n") or "\x00" in decoded:
        raise ValueError("offline test log has no complete terminal record")
    if any(sep in decoded for sep in ("\x85", "\u2028", "\u2029", "\x0b", "\x0c")):
        raise ValueError("offline test log has unsupported record separators")
    if "\r" in decoded.replace("\r\n", ""):
        raise ValueError("offline test log has bare carriage returns")
    lines = [line.removesuffix("\r") for line in decoded.split("\n")]
    markers = [i for i, line in enumerate(lines) if line == FIREWALL_MARKER]
    if len(markers) != 1:
        raise ValueError("missing or repeated physical offline firewall marker")
    matches = [(i, match) for i, line in enumerate(lines)
               if (match := SUMMARY.fullmatch(line))]
    if len(matches) != 1:
        raise ValueError("offline pytest success summary missing or ambiguous")
    summary_index, match = matches[0]
    if summary_index <= markers[0]:
        raise ValueError("offline pytest success precedes firewall activation")
    if summary_index != max(i for i, line in enumerate(lines) if line):
        raise ValueError("offline pytest success is not the final nonempty log record")
    parsed = {}
    for token in match["counts"].split(", "):
        count, label = token.split(" ", 1)
        # Pytest prints "1 warning" but "2 warnings"; record one stable key.
        if label == "warning":
            label = "warnings"
        if label in parsed:
            raise ValueError("duplicate offline test outcome category")
        parsed[label] = int(count)
    if any(label not in {"passed", "skipped", "xfailed", "xpassed",
                         "warnings", "deselected"} for label in parsed):
        raise ValueError("unsupported offline test result category")
    # A zero-exit pytest run can still hide narrowed test collection or an
    # unexpectedly passing known-failure case. Neither is complete validation
    # of the source-bound CI test scope, even with a green pytest summary.
    if parsed.get("deselected", 0):
        raise ValueError("deselected tests cannot produce a complete CI test receipt")
    if parsed.get("xpassed", 0):
        raise ValueError("unexpectedly passing tests cannot produce a CI test receipt")
    if not re.fullmatch(r"[0-9a-f]{40}", checkout_sha):
        raise ValueError("invalid checked-out commit identity")
    if any(not context.get(key) for key in REQUIRED_ENV):
        raise ValueError("missing GitHub Actions run identity")
    if context["GITHUB_SHA"] != checkout_sha:
        raise ValueError("workflow commit does not match checked-out source")
    if context["GITHUB_REPOSITORY"] != "anupamking01/Ai-Researcher-Agent":
        raise ValueError("unexpected repository for VERA research receipt")
    if (context["GITHUB_EVENT_NAME"] not in {"push", "pull_request", "workflow_dispatch"}
            or any(not context[key].isdigit() or int(context[key]) < 1
                   for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))):
        raise ValueError("invalid GitHub Actions event or run identity")
    if (selected_modules is None) != (shard is None):
        raise ValueError("full CI shard identity and module inventory must be supplied together")
    # First verify the selected-module inventory against this checkout.
    # Then reject count-preserving substitutions from other modules or
    # duplicated node IDs. Specialist receipts keep their prior contract.
    full_ci = (
        _verify_full_ci_selection(
            decoded, selected_modules=selected_modules,
            shard=shard, checkout_sha=checkout_sha,
        ) if selected_modules is not None else {}
    )
    if selected_modules is not None:
        _verify_verbose_full_ci_progress(
            lines[markers[0] + 1:summary_index], expected=parsed,
            allowed_modules=frozenset(selected_modules.decode("utf-8").splitlines()),
        )
    expected_dependencies = {"requirements.txt", "requirements-ci.lock"}
    if set(dependency_bytes) != expected_dependencies:
        raise ValueError("offline test dependencies must be fully fingerprinted")
    return {
        "schema_version": 1,
        "status": "source_bound_offline_ci_log_consistent_not_independently_attested",
        "repository": context["GITHUB_REPOSITORY"],
        "checkout_sha": checkout_sha,
        "workflow_event": context["GITHUB_EVENT_NAME"],
        "workflow_run_id": context["GITHUB_RUN_ID"],
        "workflow_run_attempt": context["GITHUB_RUN_ATTEMPT"],
        "python_version": sys.version.split()[0],
        "test_counts": parsed,
        "pytest_elapsed_seconds": match["elapsed"],
        "log_bytes": len(log),
        "log_sha256": hashlib.sha256(log).hexdigest(),
        "dependency_sha256": {
            name: hashlib.sha256(dependency_bytes[name]).hexdigest()
            for name in sorted(expected_dependencies)
        },
        "firewall_activation_marker_observed": True,
        "actual_egress_independently_attested": False,
        "experimental_treatments_or_evaluators_run": False,
        "human_validation_performed": False,
        **full_ci,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--selected-modules", type=Path)
    parser.add_argument("--shard", type=int)
    args = parser.parse_args()
    try:
        log_bytes = read_bounded_evidence(
            args.log, maximum=MAX_LOG_BYTES, label="offline test log"
        )
        selected_bytes = (
            read_bounded_evidence(
                args.selected_modules, maximum=MAX_SELECTED_MODULES_BYTES,
                label="full CI selected-module inventory",
            ) if args.selected_modules is not None else None
        )
        checkout_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        receipt = build_receipt(
            log_bytes, context=dict(os.environ),
            checkout_sha=checkout_sha,
            dependency_bytes={
                name: (ROOT / name).read_bytes()
                for name in ("requirements.txt", "requirements-ci.lock")
            },
            selected_modules=selected_bytes,
            shard=args.shard,
        )
        # No read from treatment/evaluator artifacts, no network calls.
        args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"VERA OFFLINE TEST EVIDENCE: FAIL: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
