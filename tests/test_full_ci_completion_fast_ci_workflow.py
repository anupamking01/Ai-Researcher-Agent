"""Keep offline CI completion triage independently testable and source-bound.

A passing fast lane tests metadata classification and synthetic shard replay. It cannot certify
a cancelled sixteen-shard run, historical treatment custody, or human ratings.
"""
import os
from pathlib import Path
import subprocess

import pytest
import yaml

from scripts.audit_full_ci_job_completion import (
    REQUIRED_REPLAY_STEPS,
    REQUIRED_SHARD_STEPS,
)

ROOT = Path(__file__).resolve().parents[1]
FAST = ".github/workflows/full-ci-job-completion-fast-ci.yml"
FULL = ".github/workflows/tests.yml"
TESTS = (
    "tests/test_full_ci_job_completion_triage.py",
    "tests/test_full_ci_completion_fast_ci_workflow.py",
    "tests/test_full_ci_shard_selection.py",
    "tests/test_full_ci_shard_set_verification.py",
    "tests/test_full_ci_shard_set_ci_workflow.py",
    "tests/test_offline_ci_network_firewall.py",
)
AUDITOR = "scripts/audit_full_ci_job_completion.py"
REPLAY_DEPENDENCIES = (
    "scripts/select_full_ci_shard.py",
    "scripts/verify_full_ci_shard_set.py",
    "scripts/verify_ci_early_gate_evidence.py",
    "logic/evaluation.py",
    "tests/test_evaluation_stdlib_gate.py",
    "tests/conftest.py",
    "docs/FULL_OFFLINE_CI_SHARD_SET_REPLAY.md",
    "research-evidence/offline-ci-45526533438-attempt-1/**",
    "research-evidence/offline-ci-aggregate-45526533438-attempt-1.zip",
    ".github/workflows/live-pilot.yml",
    ".github/workflows/live-app-smoke.yml",
)


def _load(path):
    return yaml.load((ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(steps, name):
    matches = [step for step in steps if step["name"] == name]
    assert len(matches) == 1, f"expected one CI step named {name!r}"
    return matches[0]


def test_completion_auditor_fast_lane_is_pinned_offline_and_source_triggered():
    flow = _load(FAST)
    assert flow["permissions"] == {"contents": "read"}
    assert "workflow_dispatch" in flow["on"]
    for event in ("push", "pull_request"):
        paths = set(flow["on"][event]["paths"])
        assert {FAST, FULL, AUDITOR, *TESTS, *REPLAY_DEPENDENCIES,
                "scripts/run_offline_pytest_firewalled.sh",
                "scripts/verify_ci_source_checkout.py",
                "scripts/verify_ci_test_evidence.py",
                "scripts/verify_retained_ci_test_evidence.py",
                "requirements.txt", "requirements-ci.lock"} <= paths
    assert flow["on"]["push"]["branches"] == ["research-*"]
    assert set(flow["jobs"]) == {"completion-auditor-regressions"}
    job = flow["jobs"]["completion-auditor-regressions"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert int(job["timeout-minutes"]) <= 12
    steps = job["steps"]
    assert _step(steps, "Checkout source without credentials")["with"]["persist-credentials"] == "false"
    assert _step(steps, "Pin Python interpreter")["with"]["python-version"] == "3.11.17"
    install = _step(steps, "Install pinned, offline test dependencies only")["run"]
    for token in ("--no-deps", "--only-binary=:all:", "--constraint requirements-ci.lock",
                  "--constraint requirements.txt"):
        assert token in install
    compile_command = _step(steps, "Compile auditor and targeted tests")["run"]
    for module in (*TESTS, AUDITOR, "scripts/select_full_ci_shard.py",
                   "scripts/verify_full_ci_shard_set.py",
                   "scripts/verify_ci_early_gate_evidence.py"):
        assert module in compile_command.split()
    run = _step(steps, "Run firewalled completion-auditor regressions")
    assert run["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert run["env"]["VERA_CI_PRIVATE_NETNS"] == "1"
    assert run["run"].strip().splitlines() == [
        "set -euo pipefail",
        "bash scripts/run_offline_pytest_firewalled.sh "
        + " ".join(TESTS)
        + ' | tee "$RUNNER_TEMP/vera-ci-completion-tests.log"',
    ]


def test_completion_fast_lane_binds_and_replays_exact_commit_evidence():
    steps = _load(FAST)["jobs"]["completion-auditor-regressions"]["steps"]
    names = [step["name"] for step in steps]
    assert len(names) == len(set(names))
    required = (
        "Verify runtime and exact checkout before dependencies",
        "Install pinned, offline test dependencies only",
        "Verify exact checkout before targeted tests",
        "Run firewalled completion-auditor regressions",
        "Verify runtime and checkout after targeted tests",
        "Bind exact-commit completion-auditor receipt",
        "Replay completion-auditor receipt before retention",
        "Retain source-bound completion-auditor evidence (90 days)",
    )
    assert [names.index(s) for s in required] == sorted(names.index(s) for s in required)
    bind = _step(steps, "Bind exact-commit completion-auditor receipt")["run"]
    replay = _step(steps, "Replay completion-auditor receipt before retention")["run"]
    assert "python -m scripts.verify_ci_test_evidence" in bind
    assert "python -m scripts.verify_retained_ci_test_evidence" in replay
    for flag in ('--checkout-sha "$GITHUB_SHA"', '--run-id "$GITHUB_RUN_ID"',
                 '--run-attempt "$GITHUB_RUN_ATTEMPT"', '--event "$GITHUB_EVENT_NAME"'):
        assert flag in replay
    assert 'vera-ci-completion-tests.log' in bind and 'vera-ci-completion-tests.log' in replay
    upload = _step(steps, "Retain source-bound completion-auditor evidence (90 days)")["with"]
    assert "vera-ci-completion-test-receipt.json" in upload["path"]
    assert upload["if-no-files-found"] == "error"
    assert upload["retention-days"] == "90"


def test_completion_auditor_essential_step_labels_match_actual_full_ci_contract():
    """Prevent a green metadata auditor when full CI silently renames a gate."""
    jobs = _load(FULL)["jobs"]
    assert jobs["unit-tests"]["strategy"]["fail-fast"] == "false"
    assert jobs["replay-complete-shard-set"]["needs"] == "unit-tests"
    unit_steps = jobs["unit-tests"]["steps"]
    replay_steps = jobs["replay-complete-shard-set"]["steps"]
    for steps, required in ((unit_steps, REQUIRED_SHARD_STEPS),
                            (replay_steps, REQUIRED_REPLAY_STEPS)):
        names = [step["name"] for step in steps]
        assert len(names) == len(set(names))
        # The metadata auditor must track EVERY unconditional workflow step,
        # not merely the tests/receipt/upload gates. A new skipped dependency
        # or runtime prerequisite cannot silently become invisible to audit.
        if steps is unit_steps:
            names = [name for name in names if name !=
                     "Retain unverified diagnostics on CI failure or cancellation (90 days)"]
        assert tuple(names) == required
        # Couple the metadata auditor to actual test / receipt / replay order.
        positions = [names.index(label) for label in required]
        assert positions == sorted(positions)
    offline = _step(unit_steps, "Run offline unit tests")
    assert "scripts/run_offline_pytest_firewalled.sh" in offline["run"]
    assert offline["env"]["VERA_CI_PRIVATE_NETNS"] == "1"
    assert "scripts.verify_retained_ci_test_evidence" in _step(
        unit_steps, "Replay exact-commit offline test evidence before upload"
    )["run"]
    assert "scripts.verify_full_ci_shard_set" in _step(
        replay_steps, "Independently replay all sixteen downloaded shard receipts"
    )["run"]
    for steps, label in (
        (unit_steps, "Retain source-bound offline test evidence (90 days)"),
        (replay_steps, "Retain verified sixteen-shard replay (90 days)"),
    ):
        upload = _step(steps, label)
        assert upload["uses"].startswith("actions/upload-artifact@")
        assert upload["with"]["if-no-files-found"] == "error"


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0,
                    reason="private namespace launcher requires nonroot Linux caller")
@pytest.mark.parametrize(("mode", "expected"), [("1", 73), ("invalid", 1)])
def test_private_namespace_bootstrap_never_falls_back_to_host_firewall(tmp_path, mode, expected):
    """Fake sudo failure must not reach host iptables or pytest."""
    fake = tmp_path / "bin"
    fake.mkdir()
    log = tmp_path / "sudo.log"
    scripts = {
        "sudo": '#!/bin/sh\nprintf "%s\\n" "$@" > "$VERA_FAKE_NETNS_LOG"\nexit 73\n',
        "iptables": "#!/bin/sh\nexit 91\n",
        "ip6tables": "#!/bin/sh\nexit 92\n",
        "python": "#!/bin/sh\nexit 93\n",
    }
    for name, body in scripts.items():
        path = fake / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONOPTIMIZE", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        env.pop(name, None)
    env.update(PATH=str(fake) + os.pathsep + env["PATH"],
               VERA_CI_PRIVATE_NETNS=mode, VERA_FAKE_NETNS_LOG=str(log))
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/run_offline_pytest_firewalled.sh"), "tests/synthetic.py"],
        cwd=ROOT, env=env, text=True, capture_output=True, timeout=10, check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert "Offline pytest egress isolation active" not in result.stdout
    if mode == "1":
        args = log.read_text(encoding="utf-8").splitlines()
        assert args[:7] == ["-n", "-E", "/usr/bin/unshare", "--net", "--fork", "--kill-child", "/bin/bash"]
        assert args[-1] == "tests/synthetic.py"
    else:
        assert not log.exists()
