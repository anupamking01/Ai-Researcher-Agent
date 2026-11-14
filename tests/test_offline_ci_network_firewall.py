"""Validate fail-closed host egress protection without editing real firewalls."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "run_offline_pytest_firewalled.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


def test_offline_ci_uses_only_firewalled_pytest_entrypoint():
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["unit-tests"]["steps"]
    invocations = [step for step in steps if "pytest" in str(step.get("run", ""))]
    assert len(invocations) == 1
    # Pipefail preserves the firewalled wrapper's exit status under tee.
    # No second unprotected pytest invocation is permitted in this job.
    run = invocations[0]["run"].strip().splitlines()
    assert run == [
        "set -euo pipefail",
        'bash scripts/run_offline_pytest_firewalled.sh 2>&1 | tee "$RUNNER_TEMP/vera-offline-tests.log"',
    ]



# Manually authorized provider-backed workflows also have an offline pytest
# phase; it must retain the host firewall, without modifying the paid stages.
LIVE_OFFLINE_GATES = (
    ("live-pilot.yml", "pilot", "Compile and run offline tests first",
     "Preflight live search and concurrent browser extraction"),
    ("live-app-smoke.yml", "live-smoke", "Run offline regression suite",
     "Start FastAPI application"),
)
FIREWALLED_PYTEST = "bash scripts/run_offline_pytest_firewalled.sh"


def _live_offline_guard_problems(source, job_name, offline_step, first_live_step):
    try:
        workflow = yaml.load(source, Loader=yaml.BaseLoader)
        steps = workflow["jobs"][job_name]["steps"]
    except (yaml.YAMLError, KeyError, TypeError):
        return ["malformed live workflow offline phase"]
    if not isinstance(steps, list):
        return ["missing live workflow steps"]
    invocations = [
        (index, step) for index, step in enumerate(steps)
        if isinstance(step, dict) and "pytest" in str(step.get("run", ""))
    ]
    if len(invocations) != 1:
        return ["live diagnostic requires exactly one offline pytest entrypoint"]
    index, step = invocations[0]
    script = str(step.get("run", ""))
    problems = []
    if (step.get("name") != offline_step
            or script.strip().splitlines()[-1].strip() != FIREWALLED_PYTEST
            or script.count(FIREWALLED_PYTEST) != 1
            or "python -m pytest" in script):
        problems.append("live diagnostic offline pytest must run under host firewall")
    live_positions = [
        i for i, item in enumerate(steps)
        if isinstance(item, dict) and item.get("name") == first_live_step
    ]
    if len(live_positions) != 1 or index >= live_positions[0]:
        problems.append("offline firewall phase must precede provider-backed execution")
    return problems


@pytest.mark.parametrize(("filename", "job", "offline", "live"), LIVE_OFFLINE_GATES)
def test_live_diagnostic_offline_pytest_is_firewalled(filename, job, offline, live):
    source = (WORKFLOW.parent / filename).read_text(encoding="utf-8")
    assert _live_offline_guard_problems(source, job, offline, live) == []


@pytest.mark.parametrize(("filename", "job", "offline", "live"), LIVE_OFFLINE_GATES)
@pytest.mark.parametrize("replacement", [
    "python -m pytest -q",
    "echo skipped-offline-tests",
    "bash scripts/run_offline_pytest_firewalled.sh && python -m pytest -q",
])
def test_live_diagnostic_rejects_unprotected_or_missing_pytest(
    filename, job, offline, live, replacement
):
    source = (WORKFLOW.parent / filename).read_text(encoding="utf-8")
    altered = source.replace(FIREWALLED_PYTEST, replacement, 1)
    assert altered != source
    assert _live_offline_guard_problems(altered, job, offline, live)


def _fake_iptables(family: str) -> str:
    return (
        "#!/usr/bin/env bash\n"
        + 'printf "' + family + ' %s\\n" "$*" >> "$VERA_FAKE_FIREWALL_LOG"\n'
        + 'if [[ "$1" == "-w" && "$2" == "-N" ]]; then printf "%s" "$3" > "$VERA_FAKE_CHAIN_FILE"; fi\n'
        + 'if [[ "$VERA_FAIL_V6_LINK" == "1" && "' + family + '" == "v6" && "$*" == *" -I OUTPUT "* ]]; then exit 42; fi\n'
        + 'chain=$(cat "$VERA_FAKE_CHAIN_FILE" 2>/dev/null || true)\n'
        + 'if [[ "$*" == "-w -S $chain" && -n "$chain" ]]; then\n'
        + '  if [[ "$VERA_FAKE_POLICY" == "' + family + '_query_failure" ]]; then exit 44; fi\n'
        + '  printf -- "-N %s\\n-A %s -o lo -j RETURN\\n" "$chain" "$chain"\n'
        + '  if [[ "$VERA_FAKE_POLICY" != "' + family + '_missing_reject" ]]; then\n'
        + '    if [[ "$VERA_FAKE_POLICY" == "' + family + '_normalized_reject" ]]; then\n'
        + '      if [[ "' + family + '" == "v4" ]]; then suffix="icmp-port-unreachable"; else suffix="icmp6-port-unreachable"; fi\n'
        + '      printf -- "-A %s -j REJECT --reject-with %s\\n" "$chain" "$suffix"\n'
        + '    else printf -- "-A %s -j REJECT\\n" "$chain"; fi\n'
        + '  fi\n'
        + 'elif [[ "$*" == "-w -S OUTPUT" ]]; then\n'
        + '  printf -- "-P OUTPUT ACCEPT\\n"\n'
        + '  if [[ "$VERA_FAKE_POLICY" == "' + family + '_shadowed_output" ]]; then printf -- "-A OUTPUT -j ACCEPT\\n"; fi\n'
        + '  printf -- "-A OUTPUT -j %s\\n" "$chain"\n'
        + 'fi\n'
        + "exit 0\n"
    )


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only firewall wrapper")
@pytest.mark.parametrize(
    ("v6_failure", "pytest_exit", "policy_failure", "expected_exit"),
    [
        (False, 0, "", 0), (False, 7, "", 7), (True, 0, "", 42),
        (False, 0, "v4_missing_reject", 1),
        (False, 0, "v6_missing_reject", 1),
        (False, 0, "v4_shadowed_output", 1),
        (False, 0, "v6_shadowed_output", 1),
        (False, 0, "v4_query_failure", 1),
        (False, 0, "v6_query_failure", 1),
        (False, 0, "v4_normalized_reject", 0),
        (False, 0, "v6_normalized_reject", 0),
    ],
)
def test_firewall_order_failure_rollback_and_exit_code(
    tmp_path: Path, v6_failure: bool, pytest_exit: int,
    policy_failure: str, expected_exit: int
):
    # Fake sudo, iptables and Python prove ordering without root or network.
    fake = tmp_path / "fake-bin"
    fake.mkdir()
    scripts = {
        "sudo": '#!/bin/sh\n[ "$1" = "-n" ] || exit 80\nshift\nexec "$@"\n',
        "iptables": _fake_iptables("v4"),
        "ip6tables": _fake_iptables("v6"),
        "python": (
            '#!/bin/sh\nprintf "pytest %s\\n" "$*" >> "$VERA_FAKE_FIREWALL_LOG"\n'
            'exit "$VERA_FAKE_PYTEST_EXIT"\n'
        ),
    }
    for filename, body in scripts.items():
        path = fake / filename
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    log = tmp_path / "commands.txt"
    env = os.environ.copy()
    env.update({
        "PATH": str(fake) + os.pathsep + env["PATH"],
        "VERA_FAKE_FIREWALL_LOG": str(log),
        "VERA_FAKE_PYTEST_EXIT": str(pytest_exit),
        "VERA_FAIL_V6_LINK": "1" if v6_failure else "0",
        "VERA_FAKE_POLICY": policy_failure,
        "VERA_FAKE_CHAIN_FILE": str(tmp_path / "chain"),
    })
    result = subprocess.run(
        ["bash", str(WRAPPER)], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == expected_exit, result.stderr
    commands = log.read_text(encoding="utf-8").splitlines()
    def index(prefix: str) -> int:
        return next(i for i, row in enumerate(commands) if row.startswith(prefix))
    v4_link = index("v4 -w -I OUTPUT 1 -j ")
    v6_link = index("v6 -w -I OUTPUT 1 -j ")
    v4_remove = index("v4 -w -D OUTPUT -j ")
    assert v4_link < v4_remove
    if v6_failure:
        assert not any(row.startswith("pytest ") for row in commands)
        assert any(row.startswith("v6 -w -F VERA_OFFLINE_") for row in commands)
        assert any(row.startswith("v6 -w -X VERA_OFFLINE_") for row in commands)
        assert not any(row.startswith("v6 -w -D OUTPUT") for row in commands)
    elif policy_failure and not policy_failure.endswith("_normalized_reject"):
        assert not any(row.startswith("pytest ") for row in commands)
        assert any(" -S " in row for row in commands)
        assert any(row.startswith("v4 -w -F VERA_OFFLINE_") for row in commands)
        assert any(row.startswith("v6 -w -X VERA_OFFLINE_") for row in commands)
    else:
        v4_check = index("v4 -w -C OUTPUT -j ")
        v6_check = index("v6 -w -C OUTPUT -j ")
        v4_policy = index("v4 -w -S VERA_OFFLINE_")
        v6_policy = index("v6 -w -S VERA_OFFLINE_")
        pytest_index = index("pytest -m pytest -q --strict-markers --strict-config")
        assert v4_check < v4_policy < v6_policy < pytest_index
        v6_remove = index("v6 -w -D OUTPUT -j ")
        assert v4_link < v6_link < v4_check < v6_check < pytest_index < v6_remove
        assert pytest_index < v4_remove
        assert any(row.startswith("v4 -w -F VERA_OFFLINE_") for row in commands)
        assert any(row.startswith("v6 -w -X VERA_OFFLINE_") for row in commands)

def test_firewalled_pytest_requires_strict_collection_and_configuration():
    """The shared entrypoint must never certify unknown markers/config as green."""
    command = WRAPPER.read_text(encoding="utf-8").rstrip().splitlines()[-1]
    assert command == 'python -m pytest -q --strict-markers --strict-config "$@"'


@pytest.mark.parametrize(
    ("strict_option", "test_source", "config_source", "diagnostic"),
    [
        (
            "--strict-markers",
            "import pytest\n@pytest.mark.vera_typo_marker\ndef test_probe(): pass\n",
            None,
            "vera_typo_marker",
        ),
        (
            "--strict-config",
            "def test_probe(): pass\n",
            "[pytest]\nvera_typo_option = true\n",
            "Unknown config option",
        ),
    ],
)
def test_strict_pytest_rejects_silent_collection_and_configuration_errors(
    tmp_path, strict_option, test_source, config_source, diagnostic,
):
    """Default pytest passes each synthetic misconfiguration; CI must not."""
    source = tmp_path / "test_probe.py"
    source.write_text(test_source, encoding="utf-8")
    if config_source is not None:
        (tmp_path / "pytest.ini").write_text(config_source, encoding="utf-8")
    command = [
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        str(source),
    ]
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    ordinary = subprocess.run(
        command, cwd=tmp_path, env=env, text=True, capture_output=True,
        timeout=20, check=False,
    )
    assert ordinary.returncode == 0, ordinary.stdout + ordinary.stderr
    strict = subprocess.run(
        [*command[:-1], strict_option, command[-1]],
        cwd=tmp_path, env=env, text=True, capture_output=True,
        timeout=20, check=False,
    )
    assert strict.returncode != 0
    assert diagnostic in strict.stdout + strict.stderr
