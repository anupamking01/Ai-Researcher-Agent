"""Keep artifact-audit push paths in sync with their Python verifier dependencies.

The historical ZIP and preserved-package audits must be scheduled when an
indirectly imported verifier changes, not just when the command-line entrypoint
changes. This offline contract test traverses Python's static import graph;
dynamic imports need explicit review when added.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDITS = (
    (
        ".github/workflows/retained-canonical-archive-audit.yml",
        "scripts/verify_retained_canonical_download.py",
    ),
    (
        ".github/workflows/preserved-canonical-package-audit.yml",
        "scripts/verify_preserved_canonical_package.py",
    ),
)


def _local_script_imports(relative: str) -> set[str]:
    """Find actual first-party script files imported anywhere in this module."""
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
    imports: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module == "scripts":
                names = [alias.name for alias in node.names]
            elif node.module and node.module.startswith("scripts."):
                names = [node.module.split(".", 2)[1]]
        elif isinstance(node, ast.Import):
            names = [
                alias.name.split(".", 2)[1]
                for alias in node.names
                if alias.name.startswith("scripts.")
            ]
        for name in names:
            candidate = f"scripts/{name}.py"
            if (ROOT / candidate).is_file():
                imports.add(candidate)
    return imports


def _transitive_script_sources(entrypoint: str) -> set[str]:
    assert (ROOT / entrypoint).is_file(), f"missing audit entrypoint: {entrypoint}"
    required: set[str] = set()
    pending = [entrypoint]
    while pending:
        module = pending.pop()
        if module not in required:
            required.add(module)
            pending.extend(_local_script_imports(module) - required)
    return required


def _workflow_push_paths(relative: str) -> set[str]:
    """Read the workflow's narrowly structured push.paths block without YAML deps."""
    lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
    assert lines.count("  push:") == 1, f"{relative}: expected one push event"
    assert lines.count("    paths:") == 1, f"{relative}: expected one push.paths"
    push_at = lines.index("  push:")
    paths_at = lines.index("    paths:")
    assert push_at < paths_at
    assert "    branches:" in lines[push_at:paths_at]
    assert "      - research-paper-eval-2027" in lines[push_at:paths_at]
    paths: list[str] = []
    for line in lines[paths_at + 1 :]:
        if not line.startswith("      - "):
            break
        paths.append(line[8:])
    assert paths and len(paths) == len(set(paths)), f"{relative}: missing or repeated path"
    return set(paths)


@pytest.mark.parametrize("workflow,entrypoint", AUDITS)
def test_archive_audits_trigger_for_all_static_transitive_verifier_changes(
    workflow: str, entrypoint: str
) -> None:
    required = _transitive_script_sources(entrypoint)
    configured = _workflow_push_paths(workflow)
    missing = sorted(required - configured)
    assert not missing, f"{workflow} skips transitive verifier changes: {missing}"
    assert workflow in configured, "audit workflow changes must self-trigger"


@pytest.mark.parametrize("_,entrypoint", AUDITS)
def test_import_walker_reaches_shared_provenance_and_zip_dependencies(
    _: str, entrypoint: str
) -> None:
    required = _transitive_script_sources(entrypoint)
    assert {
        "scripts/preflight_recovered_artifact_zip.py",
        "scripts/verify_canonical_archive_checkout.py",
        "scripts/verify_analysis_provenance.py",
        "scripts/fingerprint_research_artifacts.py",
    } <= required
