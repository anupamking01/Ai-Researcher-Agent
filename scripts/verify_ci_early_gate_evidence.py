"""Produce and independently replay a *local-consistency* receipt for early CI.

This standard-library-only check runs before pip installation. It verifies
one complete, successful physical unittest transcript and binds its bytes to
the explicitly supplied GitHub run/commit and tracked source files. It does
not attest the runner, GitHub identity, firewall, or experiment provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAX_LOG_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 16 * 1024
SOURCES = (
    "logic/evaluation.py",
    "tests/test_evaluation_stdlib_gate.py",
    "scripts/verify_ci_early_gate_evidence.py",
)
CASE = re.compile(
    r"^(test_[A-Za-z0-9_]+) "
    r"\(test_evaluation_stdlib_gate\.DependencyFreeEvaluationGate\.\1\) "
    r"\.\.\. ok$"
)
SUMMARY = re.compile(r"^Ran ([1-9][0-9]*) tests? in [0-9]+(?:\.[0-9]+)?s$")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key in retained early CI receipt")
        result[key] = value
    return result


def _strict_equals(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(b, dict):
        return a.keys() == b.keys() and all(
            _strict_equals(a[k], v) for k, v in b.items()
        )
    if isinstance(b, list):
        return len(a) == len(b) and all(_strict_equals(x, y) for x, y in zip(a, b))
    return a == b


def build_receipt(log: bytes, *, sha: str, run_id: str, attempt: str,
                  event: str, repository: str, sources: dict[str, bytes]) -> dict:
    """Reject partial/failing/spliced unittest output, without claiming attestation."""
    if type(log) is not bytes or not 0 < len(log) <= MAX_LOG_BYTES:
        raise ValueError("early test log is missing or exceeds byte limit")
    if type(sha) is not str or not SHA.fullmatch(sha):
        raise ValueError("invalid checkout SHA")
    if repository != "anupamking01/Ai-Researcher-Agent":
        raise ValueError("unexpected repository")
    if (type(run_id) is not str or not run_id.isascii() or not run_id.isdecimal()
            or int(run_id) < 1 or type(attempt) is not str
            or not attempt.isascii() or not attempt.isdecimal()
            or int(attempt) < 1):
        raise ValueError("invalid workflow run identity")
    if event not in {"push", "pull_request", "workflow_dispatch"}:
        raise ValueError("invalid workflow event")
    if set(sources) != set(SOURCES) or any(type(v) is not bytes for v in sources.values()):
        raise ValueError("incomplete early test source fingerprints")
    try:
        transcript = log.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("early test log is not UTF-8") from exc
    if (not transcript.endswith("\n") or "\x00" in transcript
            or any(c in transcript for c in ("\x85", "\u2028", "\u2029", "\v", "\f"))
            or "\r" in transcript.replace("\r\n", "")):
        raise ValueError("early test log has invalid physical records")
    lines = [line.removesuffix("\r") for line in transcript.split("\n")]
    header = f"VERA EARLY DIAGNOSTIC: sha={sha} run={run_id} attempt={attempt} event={event}"
    if lines[0] != header or lines.count(header) != 1:
        raise ValueError("early test log identity header mismatch")
    names = [m.group(1) for line in lines if (m := CASE.fullmatch(line))]
    if len(names) < 7 or len(names) != len(set(names)):
        raise ValueError("incomplete or repeated early diagnostic test cases")
    matches = [(i, m) for i, line in enumerate(lines)
               if (m := SUMMARY.fullmatch(line))]
    if len(matches) != 1 or int(matches[0][1].group(1)) != len(names):
        raise ValueError("unittest completion count does not match passing cases")
    summary_index = matches[0][0]
    nonblank = [i for i, line in enumerate(lines) if line]
    if (summary_index < 2 or lines[summary_index - 1] != "-" * 70
            or nonblank[-1] != lines.index("OK")
            or summary_index >= nonblank[-1]
            or any(lines[i] for i in range(summary_index + 1, nonblank[-1])
                   if lines[i].strip())):
        raise ValueError("early test log lacks final successful unittest result")
    # For this fixed suite, disallow unrelated content masquerading as a test.
    allowed = {header, "-" * 70, "OK", ""}
    for line in lines:
        if line not in allowed and not CASE.fullmatch(line) and not SUMMARY.fullmatch(line):
            raise ValueError("unexpected content in early diagnostic transcript")
    return {
        "schema_version": 1,
        "status": "early_unittest_log_locally_consistent_not_independently_attested",
        "repository": repository,
        "checkout_sha": sha,
        "workflow_run_id": run_id,
        "workflow_run_attempt": attempt,
        "workflow_event": event,
        "passed_tests": len(names),
        "test_names": sorted(names),
        "log_bytes": len(log),
        "log_sha256": hashlib.sha256(log).hexdigest(),
        "source_sha256": {
            name: hashlib.sha256(sources[name]).hexdigest() for name in SOURCES
        },
        "full_pytest_success_established": False,
        "historical_source_custody_established": False,
        "human_validation_performed": False,
    }


def _canonical(receipt: dict) -> bytes:
    return (json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True)
            + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("create", "verify"), required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    try:
        if args.log.stat().st_size > MAX_LOG_BYTES:
            raise ValueError("early test log exceeds byte limit")
        expected = build_receipt(
            args.log.read_bytes(), sha=args.checkout_sha, run_id=args.run_id,
            attempt=args.run_attempt, event=args.event, repository=args.repository,
            sources={name: (ROOT / name).read_bytes() for name in SOURCES},
        )
        canonical = _canonical(expected)
        if args.mode == "create":
            with args.receipt.open("xb") as output:
                output.write(canonical)
        else:
            if args.receipt.stat().st_size > MAX_RECEIPT_BYTES:
                raise ValueError("retained early test receipt exceeds byte limit")
            original = args.receipt.read_bytes()
            observed = json.loads(
                original.decode("utf-8"), object_pairs_hook=_unique_pairs,
                parse_float=lambda _: (_ for _ in ()).throw(ValueError("float in receipt")),
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant in receipt")),
            )
            if (type(observed) is not dict or original != _canonical(observed)
                    or not _strict_equals(observed, expected)):
                raise ValueError("retained early test receipt disagrees with log/source/run")
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, RecursionError) as exc:
        parser.exit(1, f"VERA EARLY CI RECEIPT: FAIL: {exc}\n")
    print(f"VERA EARLY CI RECEIPT: {args.mode.upper()} LOCALLY CONSISTENT (not attested)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
