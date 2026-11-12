"""Create a source-bound, diagnostic receipt for one successful offline CI run.

The GitHub job must run the firewalled pytest wrapper with bash pipefail and
tee the exact output. This verifier audits that completed local output; it
cannot independently attest the runner or the correctness of tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

MAX_LOG_BYTES = 16 * 1024 * 1024
FIREWALL_MARKER = (
    "Offline pytest egress isolation active "
    "(IPv4 + IPv6; loopback allowed; policy inspected)."
)
SUMMARY = re.compile(
    r"(?P<counts>[1-9][0-9]* passed(?:, [0-9]+ "
    r"(?:skipped|xfailed|xpassed|warnings|deselected))*) "
    r"in (?P<elapsed>[0-9]+(?:\.[0-9]+)?)s"
    r"(?: \([0-9:.]+\))?"
)
REQUIRED_ENV = (
    "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT", "GITHUB_EVENT_NAME",
)
ROOT = Path(__file__).resolve().parents[1]


def build_receipt(log: bytes, *, context: dict[str, str],
                  checkout_sha: str, dependency_bytes: dict[str, bytes]) -> dict:
    """Do not publish a PASS for absent, ambiguous, or failing pytest output."""
    if type(log) is not bytes or not 0 < len(log) <= MAX_LOG_BYTES:
        raise ValueError("offline test log is missing or exceeds size limit")
    try:
        lines = log.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("offline test log is not UTF-8") from exc
    if sum(FIREWALL_MARKER in line for line in lines) != 1:
        raise ValueError("missing or repeated offline firewall activation marker")
    matches = [match for line in lines if (match := SUMMARY.fullmatch(line.strip()))]
    if len(matches) != 1:
        raise ValueError("offline pytest success summary missing or ambiguous")
    match = matches[0]
    parsed = {}
    for token in match["counts"].split(", "):
        count, label = token.split(" ", 1)
        if label in parsed:
            raise ValueError("duplicate offline test outcome category")
        parsed[label] = int(count)
    if any(label not in {"passed", "skipped", "xfailed", "xpassed",
                         "warnings", "deselected"} for label in parsed):
        raise ValueError("unsupported offline test result category")
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
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.log.stat().st_size > MAX_LOG_BYTES:
            raise ValueError("offline test log exceeds size limit")
        checkout_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        receipt = build_receipt(
            args.log.read_bytes(), context=dict(os.environ),
            checkout_sha=checkout_sha,
            dependency_bytes={
                name: (ROOT / name).read_bytes()
                for name in ("requirements.txt", "requirements-ci.lock")
            },
        )
        # No read from treatment/evaluator artifacts, no network calls.
        args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"VERA OFFLINE TEST EVIDENCE: FAIL: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
