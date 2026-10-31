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
    assert invocations[0]["run"].strip() == "bash scripts/run_offline_pytest_firewalled.sh"


def _fake_iptables(family: str) -> str:
    return (
        "#!/usr/bin/env bash\n"
        + 'printf "' + family + ' %s\\n" "$*" >> "$VERA_FAKE_FIREWALL_LOG"\n'
        + 'if [[ "$VERA_FAIL_V6_LINK" == "1" && "'
        + family + '" == "v6" && "$*" == *" -I OUTPUT "* ]]; then exit 42; fi\n'
        + "exit 0\n"
    )


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only firewall wrapper")
@pytest.mark.parametrize(
    ("v6_failure", "pytest_exit", "expected_exit"),
    [(False, 0, 0), (False, 7, 7), (True, 0, 42)],
)
def test_firewall_order_failure_rollback_and_exit_code(
    tmp_path: Path, v6_failure: bool, pytest_exit: int, expected_exit: int
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
    else:
        v4_check = index("v4 -w -C OUTPUT -j ")
        v6_check = index("v6 -w -C OUTPUT -j ")
        pytest_index = index("pytest -m pytest -q")
        v6_remove = index("v6 -w -D OUTPUT -j ")
        assert v4_link < v6_link < v4_check < v6_check < pytest_index < v6_remove
        assert pytest_index < v4_remove
        assert any(row.startswith("v4 -w -F VERA_OFFLINE_") for row in commands)
        assert any(row.startswith("v6 -w -X VERA_OFFLINE_") for row in commands)
