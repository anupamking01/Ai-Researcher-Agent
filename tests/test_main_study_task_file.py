import asyncio
import builtins
import hashlib
import importlib
import json
import os
import py_compile
import re
import subprocess
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts import run_budget_main_study


def _git(*args, cwd):
    return subprocess.check_output(
        ["git", *args],
        cwd=cwd,
        text=True,
    ).strip()


def _initialize_git_repository(path):
    _git("init", "-q", cwd=path)
    _git("config", "user.email", "research-test@example.invalid", cwd=path)
    _git("config", "user.name", "Research Test", cwd=path)
    source = path / "source.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    _git("add", "source.py", cwd=path)
    _git("commit", "-q", "-m", "test fixture", cwd=path)
    return source


def _valid_payload() -> dict:
    return {
        "task_set_id": "main-budget-v1-test",
        "tasks": [
            {
                "id": "main-01",
                "category": "technical_comparison",
                "question": "What does the synthetic evidence show?",
            }
        ],
    }


def _write_payload(path, payload) -> bytes:
    raw = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def test_git_source_state_records_exact_clean_commit_and_tree(tmp_path, monkeypatch):
    _initialize_git_repository(tmp_path)
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    assert run_budget_main_study._git_source_state() == {
        "commit": _git("rev-parse", "HEAD", cwd=tmp_path),
        "tree": _git("rev-parse", "HEAD^{tree}", cwd=tmp_path),
    }


def test_git_source_state_rejects_dirty_worktree(tmp_path, monkeypatch):
    source = _initialize_git_repository(tmp_path)
    source.write_text("VALUE = 2\n", encoding="utf-8")
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="Git working tree is not clean"):
        run_budget_main_study._git_source_state()


@pytest.mark.parametrize("index_flag", ["--assume-unchanged", "--skip-worktree"])
def test_git_source_state_rejects_hidden_tracked_changes(
    tmp_path, monkeypatch, index_flag
):
    source = _initialize_git_repository(tmp_path)
    _git("update-index", index_flag, "source.py", cwd=tmp_path)
    source.write_text("VALUE = 2\n", encoding="utf-8")
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="Git index hides tracked source state"):
        run_budget_main_study._git_source_state()


def test_git_source_state_rejects_nonignored_untracked_files(tmp_path, monkeypatch):
    _initialize_git_repository(tmp_path)
    (tmp_path / "untracked.py").write_text("VALUE = 2\n", encoding="utf-8")
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="Git working tree is not clean"):
        run_budget_main_study._git_source_state()


def test_git_source_state_rejects_unversioned_source_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="Cannot record Git source state"):
        run_budget_main_study._git_source_state()


def test_git_source_state_rejects_ancestor_repository(tmp_path, monkeypatch):
    _initialize_git_repository(tmp_path)
    nested_root = tmp_path / "copied-project"
    nested_root.mkdir()
    (nested_root / "runner.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git("add", "copied-project/runner.py", cwd=tmp_path)
    _git("commit", "-q", "-m", "add copied project", cwd=tmp_path)
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", nested_root)

    with pytest.raises(SystemExit, match="Git repository root does not match"):
        run_budget_main_study._git_source_state()


def test_git_source_state_ignores_repository_override_environment(
    tmp_path, monkeypatch
):
    real_root = tmp_path / "real-project"
    real_root.mkdir()
    source = _initialize_git_repository(real_root)

    spoof_root = tmp_path / "spoof-project"
    spoof_root.mkdir()
    spoof_source = _initialize_git_repository(spoof_root)
    spoof_source.write_text("VALUE = 2\n", encoding="utf-8")
    _git("add", "source.py", cwd=spoof_root)
    _git("commit", "-q", "-m", "spoof changed source", cwd=spoof_root)

    source.write_text("VALUE = 2\n", encoding="utf-8")
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", real_root)
    monkeypatch.setenv("GIT_DIR", str(spoof_root / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(real_root))

    with pytest.raises(SystemExit, match="Git working tree is not clean"):
        run_budget_main_study._git_source_state()


def test_git_source_state_rejects_tracked_symlink(tmp_path, monkeypatch):
    _initialize_git_repository(tmp_path)
    external_source = tmp_path.parent / "external-treatment.py"
    external_source.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "linked-treatment.py").symlink_to(external_source)
    _git("add", "linked-treatment.py", cwd=tmp_path)
    _git("commit", "-q", "-m", "track treatment symlink", cwd=tmp_path)
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="tracked source entry is not a regular blob"):
        run_budget_main_study._git_source_state()


def test_git_source_state_rejects_clean_filter_byte_divergence(
    tmp_path, monkeypatch
):
    source = _initialize_git_repository(tmp_path)
    _git(
        "config",
        "filter.freeze.clean",
        "sed 's/VALUE = .*/VALUE = 1/'",
        cwd=tmp_path,
    )
    _git("config", "filter.freeze.smudge", "cat", cwd=tmp_path)
    (tmp_path / ".gitattributes").write_text(
        "source.py filter=freeze\n",
        encoding="utf-8",
    )
    _git("add", ".gitattributes", "source.py", cwd=tmp_path)
    _git("commit", "-q", "-m", "configure source filter", cwd=tmp_path)
    source.write_text("VALUE = 2\n", encoding="utf-8")
    assert _git("status", "--porcelain=v1", cwd=tmp_path) == ""
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)

    with pytest.raises(SystemExit, match="tracked source bytes do not match HEAD"):
        run_budget_main_study._git_source_state()


def test_repository_bytecode_isolation_ignores_unchecked_hash_cache(
    tmp_path, monkeypatch
):
    source = _initialize_git_repository(tmp_path)
    (tmp_path / ".gitignore").write_text(
        "**/__pycache__/\n",
        encoding="utf-8",
    )
    _git("add", ".gitignore", cwd=tmp_path)
    _git("commit", "-q", "-m", "ignore bytecode", cwd=tmp_path)

    source.write_text("VALUE = 2\n", encoding="utf-8")
    py_compile.compile(
        str(source),
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    source.write_text("VALUE = 1\n", encoding="utf-8")
    assert _git("status", "--porcelain=v1", cwd=tmp_path) == ""
    imported_value = subprocess.check_output(
        [sys.executable, "-c", "import source; print(source.VALUE)"],
        cwd=tmp_path,
        text=True,
    ).strip()
    assert imported_value == "2"
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    assert run_budget_main_study._git_source_state()["commit"] == _git(
        "rev-parse", "HEAD", cwd=tmp_path
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    with run_budget_main_study._repository_bytecode_isolation():
        sys.modules.pop("source", None)
        importlib.invalidate_caches()
        source_module = importlib.import_module("source")
        assert source_module.VALUE == 1
    sys.modules.pop("source", None)


def test_repository_imports_precede_external_pythonpath(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    repository.mkdir()
    _initialize_git_repository(repository)
    repository_package = repository / "treatment_shadow"
    repository_package.mkdir()
    (repository_package / "__init__.py").write_text("", encoding="utf-8")
    (repository_package / "runtime.py").write_text(
        "ORIGIN = 'repository'\n",
        encoding="utf-8",
    )
    _git("add", "treatment_shadow", cwd=repository)
    _git("commit", "-q", "-m", "add treatment package", cwd=repository)

    external = tmp_path / "external-shadow"
    external_package = external / "treatment_shadow"
    external_package.mkdir(parents=True)
    (external_package / "__init__.py").write_text("", encoding="utf-8")
    (external_package / "runtime.py").write_text(
        "ORIGIN = 'external'\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", repository)
    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join((str(external), str(repository))),
    )
    monkeypatch.setattr(
        sys,
        "path",
        [str(external), str(repository), *sys.path],
    )
    sys.modules.pop("treatment_shadow", None)
    sys.modules.pop("treatment_shadow.runtime", None)
    original_search_path = list(sys.path)
    original_pythonpath = os.environ["PYTHONPATH"]
    try:
        with run_budget_main_study._repository_bytecode_isolation():
            run_budget_main_study._prioritize_repository_imports()
            treatment_module = importlib.import_module("treatment_shadow.runtime")
            assert treatment_module.ORIGIN == "repository"
            run_budget_main_study._verify_repository_module_origin(
                treatment_module,
                "treatment_shadow/runtime.py",
            )
            assert Path(sys.path[0]).resolve() == repository.resolve()
            assert external.resolve() not in {
                Path(entry or os.getcwd()).resolve() for entry in sys.path
            }
        assert sys.path == original_search_path
        assert os.environ["PYTHONPATH"] == original_pythonpath
    finally:
        sys.modules.pop("treatment_shadow.runtime", None)
        sys.modules.pop("treatment_shadow", None)


def test_execution_environment_records_normalized_sorted_distributions(
    tmp_path, monkeypatch
):
    python_version_file = tmp_path / ".python-version"
    python_version_file.write_text("3.11.99\n", encoding="utf-8")
    requirements_file = tmp_path / "requirements.txt"
    requirements_file.write_text(
        "Zeta_Package==2.0\nalpha.package==1.0\n",
        encoding="utf-8",
    )
    ci_requirements_file = tmp_path / "requirements-ci.lock"
    ci_requirements_file.write_text("ci-package==3.0\n", encoding="utf-8")
    monkeypatch.setattr(
        run_budget_main_study, "PYTHON_VERSION_FILE", python_version_file
    )
    monkeypatch.setattr(
        run_budget_main_study, "REQUIREMENTS_FILE", requirements_file
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_read_requirements_lock",
        requirements_file.read_bytes,
    )
    monkeypatch.setattr(
        run_budget_main_study, "CI_REQUIREMENTS_FILE", ci_requirements_file
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_read_ci_requirements_lock",
        ci_requirements_file.read_bytes,
    )
    distributions = [
        types.SimpleNamespace(metadata={"Name": "Zeta_Package"}, version="2.0"),
        types.SimpleNamespace(metadata={"Name": "alpha.package"}, version="1.0"),
        types.SimpleNamespace(metadata={"Name": "Alpha-Package"}, version="1.0"),
        types.SimpleNamespace(metadata={"Name": "ci-package"}, version="3.0"),
    ]
    monkeypatch.setattr(
        run_budget_main_study,
        "importlib",
        types.SimpleNamespace(
            metadata=types.SimpleNamespace(distributions=lambda: distributions)
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "platform",
        types.SimpleNamespace(
            python_implementation=lambda: "SyntheticPython",
            python_version=lambda: "3.11.99",
            platform=lambda: "synthetic-runner",
        ),
        raising=False,
    )

    assert run_budget_main_study._execution_environment() == {
        "python_implementation": "SyntheticPython",
        "python_version_pin": "3.11.99",
        "python_version": "3.11.99",
        "platform": "synthetic-runner",
        "installed_distributions": [
            {"name": "alpha-package", "version": "1.0"},
            {"name": "alpha-package", "version": "1.0"},
            {"name": "ci-package", "version": "3.0"},
            {"name": "zeta-package", "version": "2.0"},
        ],
        "requirements_file": str(requirements_file.resolve()),
        "requirements_file_sha256": hashlib.sha256(
            requirements_file.read_bytes()
        ).hexdigest(),
        "ci_requirements_file": str(ci_requirements_file.resolve()),
        "ci_requirements_file_sha256": hashlib.sha256(
            ci_requirements_file.read_bytes()
        ).hexdigest(),
        "required_distributions": [
            {"name": "alpha-package", "version": "1.0"},
            {"name": "ci-package", "version": "3.0"},
            {"name": "zeta-package", "version": "2.0"},
        ],
    }


def test_execution_environment_binds_ci_lock_and_validates_its_pins(
    tmp_path, monkeypatch
):
    python_version_file = tmp_path / ".python-version"
    python_version_file.write_text("3.11.99\n", encoding="utf-8")
    requirements_file = tmp_path / "requirements.txt"
    requirements_file.write_text("alpha-package==1.0\n", encoding="utf-8")
    ci_requirements_file = tmp_path / "requirements-ci.lock"
    ci_requirements_file.write_text("beta-package==2.0\n", encoding="utf-8")
    monkeypatch.setattr(
        run_budget_main_study, "PYTHON_VERSION_FILE", python_version_file
    )
    monkeypatch.setattr(
        run_budget_main_study, "REQUIREMENTS_FILE", requirements_file
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "CI_REQUIREMENTS_FILE",
        ci_requirements_file,
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_read_requirements_lock",
        requirements_file.read_bytes,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_read_ci_requirements_lock",
        ci_requirements_file.read_bytes,
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "importlib",
        types.SimpleNamespace(
            metadata=types.SimpleNamespace(
                distributions=lambda: [
                    types.SimpleNamespace(
                        metadata={"Name": "alpha-package"}, version="1.0"
                    ),
                    types.SimpleNamespace(
                        metadata={"Name": "beta-package"}, version="2.0"
                    ),
                ]
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "platform",
        types.SimpleNamespace(
            python_implementation=lambda: "SyntheticPython",
            python_version=lambda: "3.11.99",
            platform=lambda: "synthetic-runner",
        ),
        raising=False,
    )

    environment = run_budget_main_study._execution_environment()

    assert environment["ci_requirements_file"] == str(
        ci_requirements_file.resolve()
    )
    assert environment["ci_requirements_file_sha256"] == hashlib.sha256(
        ci_requirements_file.read_bytes()
    ).hexdigest()
    assert environment["required_distributions"] == [
        {"name": "alpha-package", "version": "1.0"},
        {"name": "beta-package", "version": "2.0"},
    ]


def test_execution_environment_rejects_ci_lock_version_drift(tmp_path, monkeypatch):
    python_version_file = tmp_path / ".python-version"
    python_version_file.write_text("3.11.99\n", encoding="utf-8")
    requirements_file = tmp_path / "requirements.txt"
    requirements_file.write_text("alpha-package==1.0\n", encoding="utf-8")
    ci_requirements_file = tmp_path / "requirements-ci.lock"
    ci_requirements_file.write_text("beta-package==2.0\n", encoding="utf-8")
    monkeypatch.setattr(
        run_budget_main_study, "PYTHON_VERSION_FILE", python_version_file
    )
    monkeypatch.setattr(
        run_budget_main_study, "REQUIREMENTS_FILE", requirements_file
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "CI_REQUIREMENTS_FILE",
        ci_requirements_file,
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_read_requirements_lock",
        requirements_file.read_bytes,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_read_ci_requirements_lock",
        ci_requirements_file.read_bytes,
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "importlib",
        types.SimpleNamespace(
            metadata=types.SimpleNamespace(
                distributions=lambda: [
                    types.SimpleNamespace(
                        metadata={"Name": "alpha-package"}, version="1.0"
                    ),
                    types.SimpleNamespace(
                        metadata={"Name": "beta-package"}, version="2.1"
                    ),
                ]
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "platform",
        types.SimpleNamespace(
            python_implementation=lambda: "SyntheticPython",
            python_version=lambda: "3.11.99",
            platform=lambda: "synthetic-runner",
        ),
        raising=False,
    )

    with pytest.raises(
        SystemExit,
        match="requires beta-package==2.0, found 2.1",
    ):
        run_budget_main_study._execution_environment()


def test_execution_environment_rejects_duplicate_pin_across_locks(
    tmp_path, monkeypatch
):
    python_version_file = tmp_path / ".python-version"
    python_version_file.write_text("3.11.99\n", encoding="utf-8")
    requirements_file = tmp_path / "requirements.txt"
    requirements_file.write_text("Example_Package==1.0\n", encoding="utf-8")
    ci_requirements_file = tmp_path / "requirements-ci.lock"
    ci_requirements_file.write_text("example-package==1.0\n", encoding="utf-8")
    monkeypatch.setattr(
        run_budget_main_study, "PYTHON_VERSION_FILE", python_version_file
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_read_requirements_lock",
        requirements_file.read_bytes,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_read_ci_requirements_lock",
        ci_requirements_file.read_bytes,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "platform",
        types.SimpleNamespace(python_version=lambda: "3.11.99"),
        raising=False,
    )

    with pytest.raises(
        SystemExit,
        match="dependency locks contain duplicate normalized distribution pin: "
        "example-package",
    ):
        run_budget_main_study._execution_environment()


def test_execution_environment_accepts_patch_within_major_minor_pin(
    tmp_path, monkeypatch
):
    python_version_file = tmp_path / ".python-version"
    python_version_file.write_text("3.11\n", encoding="utf-8")
    requirements_file = tmp_path / "requirements.txt"
    requirements_file.write_text("example-package==1.0\n", encoding="utf-8")
    ci_requirements_file = tmp_path / "requirements-ci.lock"
    ci_requirements_file.write_text("ci-package==3.0\n", encoding="utf-8")
    monkeypatch.setattr(
        run_budget_main_study, "PYTHON_VERSION_FILE", python_version_file
    )
    monkeypatch.setattr(
        run_budget_main_study, "REQUIREMENTS_FILE", requirements_file
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_read_requirements_lock",
        requirements_file.read_bytes,
    )
    monkeypatch.setattr(
        run_budget_main_study, "CI_REQUIREMENTS_FILE", ci_requirements_file
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_read_ci_requirements_lock",
        ci_requirements_file.read_bytes,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "importlib",
        types.SimpleNamespace(
            metadata=types.SimpleNamespace(
                distributions=lambda: [
                    types.SimpleNamespace(
                        metadata={"Name": "example-package"}, version="1.0"
                    ),
                    types.SimpleNamespace(
                        metadata={"Name": "ci-package"}, version="3.0"
                    ),
                ]
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "platform",
        types.SimpleNamespace(
            python_implementation=lambda: "CPython",
            python_version=lambda: "3.11.99",
            platform=lambda: "synthetic-runner",
        ),
        raising=False,
    )

    environment = run_budget_main_study._execution_environment()

    assert environment["python_version_pin"] == "3.11"
    assert environment["python_version"] == "3.11.99"


@pytest.mark.parametrize(
    ("requirements", "distributions", "message"),
    [
        (
            "example-package==1.2.3\n",
            [
                types.SimpleNamespace(
                    metadata={"Name": "example-package"}, version="1.2.4"
                )
            ],
            "requires example-package==1.2.3, found 1.2.4",
        ),
        (
            "example-package==1.2.3\n",
            [],
            "missing required distribution example-package==1.2.3",
        ),
        (
            "example-package>=1.2.3\n",
            [],
            "must contain only exact name==version pins",
        ),
        (
            "Example_Package==1.2.3\nexample-package==1.2.3\n",
            [
                types.SimpleNamespace(
                    metadata={"Name": "example-package"}, version="1.2.3"
                )
            ],
            "duplicate normalized distribution pin: example-package",
        ),
        (
            "example-package==1.2.3,!=2.0\n",
            [
                types.SimpleNamespace(
                    metadata={"Name": "example-package"}, version="1.2.3,!=2.0"
                )
            ],
            "must contain only exact name==version pins",
        ),
    ],
)
def test_execution_environment_rejects_unsatisfied_or_ambiguous_requirements(
    tmp_path, monkeypatch, requirements, distributions, message
):
    python_version_file = tmp_path / ".python-version"
    python_version_file.write_text("3.11\n", encoding="utf-8")
    requirements_file = tmp_path / "requirements.txt"
    requirements_file.write_text(requirements, encoding="utf-8")
    monkeypatch.setattr(
        run_budget_main_study, "PYTHON_VERSION_FILE", python_version_file
    )
    monkeypatch.setattr(
        run_budget_main_study, "REQUIREMENTS_FILE", requirements_file
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_read_requirements_lock",
        requirements_file.read_bytes,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "importlib",
        types.SimpleNamespace(
            metadata=types.SimpleNamespace(distributions=lambda: distributions)
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "platform",
        types.SimpleNamespace(
            python_implementation=lambda: "CPython",
            python_version=lambda: "3.11.99",
            platform=lambda: "synthetic-runner",
        ),
        raising=False,
    )

    with pytest.raises(SystemExit, match=re.escape(message)):
        run_budget_main_study._execution_environment()


def test_requirements_lock_rejects_tracked_symlink(tmp_path, monkeypatch):
    _initialize_git_repository(tmp_path)
    external_requirements = tmp_path.parent / "external-requirements.txt"
    external_requirements.write_text("example-package==1.0\n", encoding="utf-8")
    requirements_file = tmp_path / "requirements.txt"
    requirements_file.symlink_to(external_requirements)
    _git("add", "requirements.txt", cwd=tmp_path)
    _git("commit", "-q", "-m", "track requirements symlink", cwd=tmp_path)
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        run_budget_main_study, "REQUIREMENTS_FILE", requirements_file
    )

    with pytest.raises(SystemExit, match="tracked regular file at HEAD"):
        run_budget_main_study._read_requirements_lock()


def test_ci_requirements_lock_rejects_tracked_symlink(tmp_path, monkeypatch):
    _initialize_git_repository(tmp_path)
    external_requirements = tmp_path.parent / "external-ci-requirements.txt"
    external_requirements.write_text("example-package==1.0\n", encoding="utf-8")
    requirements_file = tmp_path / "requirements-ci.lock"
    requirements_file.symlink_to(external_requirements)
    _git("add", "requirements-ci.lock", cwd=tmp_path)
    _git("commit", "-q", "-m", "track CI requirements symlink", cwd=tmp_path)
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        run_budget_main_study, "CI_REQUIREMENTS_FILE", requirements_file
    )

    with pytest.raises(SystemExit, match="tracked regular file at HEAD"):
        run_budget_main_study._read_ci_requirements_lock()


def test_requirements_lock_rejects_ignored_replacement(tmp_path, monkeypatch):
    _initialize_git_repository(tmp_path)
    (tmp_path / ".gitignore").write_text("requirements.txt\n", encoding="utf-8")
    _git("add", ".gitignore", cwd=tmp_path)
    _git("commit", "-q", "-m", "ignore requirements", cwd=tmp_path)
    requirements_file = tmp_path / "requirements.txt"
    requirements_file.write_text("example-package==1.0\n", encoding="utf-8")
    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        run_budget_main_study, "REQUIREMENTS_FILE", requirements_file
    )

    with pytest.raises(SystemExit, match="tracked regular file at HEAD"):
        run_budget_main_study._read_requirements_lock()


@pytest.mark.parametrize(
    ("pin", "active_python"),
    [("3.11", "3.12.1"), ("3.11.17", "3.11.18")],
)
def test_execution_environment_rejects_python_outside_repository_pin(
    tmp_path, monkeypatch, pin, active_python
):
    python_version_file = tmp_path / ".python-version"
    python_version_file.write_text(f"{pin}\n", encoding="utf-8")
    monkeypatch.setattr(
        run_budget_main_study,
        "PYTHON_VERSION_FILE",
        python_version_file,
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "importlib",
        types.SimpleNamespace(
            metadata=types.SimpleNamespace(distributions=lambda: [])
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "platform",
        types.SimpleNamespace(
            python_implementation=lambda: "CPython",
            python_version=lambda: active_python,
            platform=lambda: "synthetic-runner",
        ),
        raising=False,
    )

    with pytest.raises(SystemExit, match=f"does not match repository pin {pin}"):
        run_budget_main_study._execution_environment()


@pytest.mark.parametrize("pin", ["3", "3.11\n3.12", "python-3.11"])
def test_execution_environment_rejects_malformed_repository_pin(
    tmp_path, monkeypatch, pin
):
    python_version_file = tmp_path / ".python-version"
    python_version_file.write_text(pin, encoding="utf-8")
    monkeypatch.setattr(
        run_budget_main_study, "PYTHON_VERSION_FILE", python_version_file
    )

    with pytest.raises(SystemExit, match="Invalid repository Python version pin"):
        run_budget_main_study._execution_environment()


def test_execution_environment_rejects_missing_repository_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(
        run_budget_main_study,
        "PYTHON_VERSION_FILE",
        tmp_path / ".python-version",
    )

    with pytest.raises(SystemExit, match="Cannot read the repository Python version pin"):
        run_budget_main_study._execution_environment()


def test_main_study_rejects_unpinned_python_before_treatment_imports(
    tmp_path, monkeypatch
):
    python_version_file = tmp_path / ".python-version"
    python_version_file.write_text("3.11\n", encoding="utf-8")
    monkeypatch.setattr(
        run_budget_main_study, "PYTHON_VERSION_FILE", python_version_file
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "platform",
        types.SimpleNamespace(
            python_implementation=lambda: "CPython",
            python_version=lambda: "3.12.1",
            platform=lambda: "synthetic-runner",
        ),
        raising=False,
    )
    monkeypatch.setattr(run_budget_main_study, "_check_environment", lambda: None)
    monkeypatch.setattr(
        run_budget_main_study,
        "_load_task_file",
        lambda _path: (
            "main-budget-v1-test",
            [_valid_payload()["tasks"][0]],
            {"path": "tasks.json", "size_bytes": 1, "sha256": "a" * 64},
        ),
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_load_pricing",
        lambda _path: (
            {
                "models": {
                    "test-smart": {"input": 1.0, "output": 2.0},
                    "test-fast": {"input": 0.5, "output": 1.0},
                }
            },
            {"path": "pricing.json", "size_bytes": 1, "sha256": "b" * 64},
        ),
    )
    monkeypatch.setattr(
        run_budget_main_study, "_preflight_new_study_state", lambda _pricing: 0.0
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_git_source_state",
        lambda: {"commit": "1" * 40, "tree": "2" * 40},
    )
    monkeypatch.setattr(
        run_budget_main_study.sys, "argv", ["run_budget_main_study.py"]
    )
    monkeypatch.setenv("SMART_LLM_MODEL", "test-smart")
    monkeypatch.setenv("FAST_LLM_MODEL", "test-fast")

    real_import = builtins.__import__

    def reject_treatment_import(name, *args, **kwargs):
        if name in {"logic.experiment", "logic.run"}:
            raise AssertionError(f"treatment module imported before Python gate: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_treatment_import)

    with pytest.raises(SystemExit, match="does not match repository pin 3.11"):
        asyncio.run(run_budget_main_study.main())


def test_task_loader_binds_validated_tasks_to_exact_file_snapshot(tmp_path):
    task_file = tmp_path / "tasks.json"
    raw = _write_payload(task_file, _valid_payload())

    task_set_id, tasks, snapshot = run_budget_main_study._load_task_file(task_file)

    assert task_set_id == "main-budget-v1-test"
    assert tasks == _valid_payload()["tasks"]
    assert snapshot == {
        "path": str(task_file.resolve()),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([{"tasks": []}], "top level must be an object"),
        ({"task_set_id": " ", "tasks": [{}]}, "task_set_id must be a non-empty string"),
        ({"task_set_id": "test", "tasks": "main-01"}, "tasks must be a non-empty list"),
        ({"task_set_id": "test", "tasks": ["main-01"]}, "task 1 must be an object"),
        (
            {
                "task_set_id": "test",
                "tasks": [
                    {"id": "../main-01", "category": "test", "question": "Question?"}
                ],
            },
            "task 1 id must be a safe non-empty identifier",
        ),
        (
            {
                "task_set_id": "test",
                "tasks": [
                    {"id": "main-01", "category": "test", "question": "Question?"},
                    {"id": "main-01", "category": "test", "question": "Other?"},
                ],
            },
            "duplicate task id: main-01",
        ),
        (
            {
                "task_set_id": "test",
                "tasks": [{"id": "main-01", "category": " ", "question": "Question?"}],
            },
            "task 1 category must be a non-empty string",
        ),
        (
            {
                "task_set_id": "test",
                "tasks": [{"id": "main-01", "category": "test", "question": " "}],
            },
            "task 1 question must be a non-empty string",
        ),
    ],
)
def test_task_loader_rejects_malformed_or_ambiguous_tasks(tmp_path, payload, message):
    task_file = tmp_path / "tasks.json"
    _write_payload(task_file, payload)

    with pytest.raises(SystemExit, match=message):
        run_budget_main_study._load_task_file(task_file)


def test_task_loader_rejects_duplicate_json_keys(tmp_path):
    task_file = tmp_path / "tasks.json"
    task_file.write_text(
        '{"task_set_id":"test","tasks":[{"id":"main-01",'
        '"category":"test","question":"first","question":"second"}]}',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="duplicate JSON key: question"):
        run_budget_main_study._load_task_file(task_file)


def test_main_study_manifest_records_task_snapshot_before_execution(tmp_path, monkeypatch):
    task_file = tmp_path / "tasks.json"
    raw = _write_payload(task_file, _valid_payload())
    pricing_file = tmp_path / "experiments" / "pricing.json"
    pricing_file.parent.mkdir()
    pricing_file.write_text(
        json.dumps(
            {
                "unit": "per_1m_text_tokens",
                "models": {
                    "test-smart": {"input": 1.0, "output": 2.0},
                    "test-fast": {"input": 0.5, "output": 1.0},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_budget_main_study, "PRICING_FILE", pricing_file)
    expected_environment = {
        "python_implementation": "SyntheticPython",
        "python_version_pin": "3.11",
        "python_version": "3.11.99",
        "platform": "synthetic-runner",
        "installed_distributions": [
            {"name": "example-package", "version": "1.2.3"},
        ],
    }
    monkeypatch.setattr(
        run_budget_main_study,
        "_execution_environment",
        lambda: expected_environment,
        raising=False,
    )
    expected_source_state = {
        "commit": "1" * 40,
        "tree": "2" * 40,
    }
    monkeypatch.setattr(
        run_budget_main_study,
        "_git_source_state",
        lambda: expected_source_state,
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "TRACE_ROOT",
        tmp_path / "outputs" / "experiment_traces",
    )
    monkeypatch.setattr(
        run_budget_main_study.sys,
        "argv",
        ["run_budget_main_study.py", f"--task-file={task_file}"],
    )
    for name, value in {
        "OPENAI_API_KEY": "test-key",
        "SMART_LLM_MODEL": "test-smart",
        "FAST_LLM_MODEL": "test-fast",
        "TEMPERATURE": "1",
    }.items():
        monkeypatch.setenv(name, value)

    @dataclass(frozen=True)
    class FakeConfig:
        browse_timeout_seconds: int = 1
        run_timeout_seconds: int = 2
        max_concurrent_browses: int = 3
        task_set_id: str = ""
        task_id: str = ""

    class FakeExperimentConfig:
        @classmethod
        def from_variant(cls, _variant):
            return FakeConfig()

    async def fake_run_agent(**_kwargs):
        return None

    experiment_module = types.ModuleType("logic.experiment")
    experiment_module.__file__ = str(tmp_path / "logic" / "experiment.py")
    experiment_module.ExperimentConfig = FakeExperimentConfig
    run_module = types.ModuleType("logic.run")
    run_module.__file__ = str(tmp_path / "logic" / "run.py")
    run_module.run_agent = fake_run_agent
    monkeypatch.setitem(sys.modules, "logic.experiment", experiment_module)
    monkeypatch.setitem(sys.modules, "logic.run", run_module)

    asyncio.run(run_budget_main_study.main())

    manifest = json.loads(
        (tmp_path / "outputs" / "main_study_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["task_file"] == "tasks.json"
    assert manifest["task_file_size_bytes"] == len(raw)
    assert manifest["task_file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["execution_environment"] == expected_environment
    assert manifest["git_commit"] == expected_source_state["commit"]
    assert manifest["git_tree"] == expected_source_state["tree"]


def test_main_study_rejects_source_drift_while_loading_treatment_code(
    tmp_path, monkeypatch
):
    task_file = tmp_path / "tasks.json"
    _write_payload(task_file, _valid_payload())
    pricing_file = tmp_path / "experiments" / "pricing.json"
    pricing_file.parent.mkdir()
    pricing_file.write_text(
        json.dumps(
            {
                "unit": "per_1m_text_tokens",
                "models": {
                    "test-smart": {"input": 1.0, "output": 2.0},
                    "test-fast": {"input": 0.5, "output": 1.0},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(run_budget_main_study, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_budget_main_study, "PRICING_FILE", pricing_file)
    monkeypatch.setattr(
        run_budget_main_study,
        "TRACE_ROOT",
        tmp_path / "outputs" / "experiment_traces",
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_execution_environment",
        lambda: {
            "python_implementation": "SyntheticPython",
            "python_version_pin": "3.11",
            "python_version": "3.11.99",
            "platform": "synthetic-runner",
            "installed_distributions": [],
        },
    )
    source_states = iter(
        [
            {"commit": "1" * 40, "tree": "2" * 40},
            {"commit": "1" * 40, "tree": "3" * 40},
        ]
    )
    monkeypatch.setattr(
        run_budget_main_study,
        "_git_source_state",
        lambda: next(source_states),
    )
    monkeypatch.setattr(
        run_budget_main_study.sys,
        "argv",
        ["run_budget_main_study.py", f"--task-file={task_file}"],
    )
    for name, value in {
        "OPENAI_API_KEY": "test-key",
        "SMART_LLM_MODEL": "test-smart",
        "FAST_LLM_MODEL": "test-fast",
        "TEMPERATURE": "1",
    }.items():
        monkeypatch.setenv(name, value)

    @dataclass(frozen=True)
    class FakeConfig:
        browse_timeout_seconds: int = 1
        run_timeout_seconds: int = 2
        max_concurrent_browses: int = 3
        task_set_id: str = ""
        task_id: str = ""

    class FakeExperimentConfig:
        @classmethod
        def from_variant(cls, _variant):
            return FakeConfig()

    model_calls = []

    async def fake_run_agent(**kwargs):
        model_calls.append(kwargs)

    experiment_module = types.ModuleType("logic.experiment")
    experiment_module.__file__ = str(tmp_path / "logic" / "experiment.py")
    experiment_module.ExperimentConfig = FakeExperimentConfig
    run_module = types.ModuleType("logic.run")
    run_module.__file__ = str(tmp_path / "logic" / "run.py")
    run_module.run_agent = fake_run_agent
    monkeypatch.setitem(sys.modules, "logic.experiment", experiment_module)
    monkeypatch.setitem(sys.modules, "logic.run", run_module)

    with pytest.raises(SystemExit, match="source state changed"):
        asyncio.run(run_budget_main_study.main())

    assert model_calls == []
    assert not (tmp_path / "outputs" / "main_study_manifest.json").exists()
