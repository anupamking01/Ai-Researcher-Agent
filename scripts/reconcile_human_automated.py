"""Compute and publish the frozen descriptive automated-human reconciliation.

This module does not create ratings, rerun treatments/evaluators, add hypothesis
tests, or alter the confirmatory automated analysis. It only executes the
pre-frozen descriptive reconciliation contract after the readiness gate passes.

Published reconciliation results are create-only and atomically visible:
canonical JSON is the source of truth, manuscript Markdown is a deterministic
rendering, and a manifest binds both artifacts, the verified upstream inputs,
the producing Git commit, and the exact reconciliation implementation bytes.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import platform
import re
import stat
import statistics
import subprocess
import tempfile
from contextlib import ExitStack
from pathlib import Path

from scripts import analyze_human_eval
from scripts import build_analysis_provenance
from scripts import build_human_eval_packet
from scripts import export_human_eval_annotator_bundle
from scripts import fingerprint_research_artifacts
from scripts import freeze_human_eval_ratings
from scripts import verify_human_eval_freeze
from scripts import verify_human_eval_packet
from scripts import verify_human_eval_submission_preflight
from scripts import verify_human_reconciliation_readiness as readiness
from scripts import verify_research_artifact_manifest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "outputs" / "human_eval" / "reconciliation-v1"
RECONCILIATION_JSON = "reconciliation.json"
RECONCILIATION_MARKDOWN = "reconciliation.md"
RECONCILIATION_MANIFEST = "reconciliation_manifest.json"
ANALYSIS_REQUIREMENTS = ROOT / "requirements.txt"
ANALYSIS_CI_REQUIREMENTS = ROOT / "requirements-ci.lock"
ANALYSIS_PYTHON_VERSION = ROOT / ".python-version"
MANIFEST_INTEGRITY_NOTE = (
    "Canonical JSON is the source of truth. The deterministic Markdown, "
    "upstream verified-input fingerprints, producing Git commit, and exact "
    "direct and transitive verification implementation source bytes, pinned "
    "environment files, and actual Python runtime are bound here. The verifier "
    "independently recomputes the frozen descriptive reconciliation before success."
)

CATEGORIES = (
    "concordant_positive",
    "concordant_negative",
    "discordant",
    "automated_tie",
    "human_tie",
    "both_tie",
)

# This ten-task descriptive output bundle is metadata, not an arbitrary-size
# research dataset. Keep the producer and independent verifier in agreement.
MAX_RECONCILIATION_ARTIFACT_BYTES = 16 * 1024 * 1024


def _require_reconciliation_artifact_size(content: bytes, *, label: str) -> None:
    if len(content) > MAX_RECONCILIATION_ARTIFACT_BYTES:
        raise ValueError(
            f"{label} exceeds {MAX_RECONCILIATION_ARTIFACT_BYTES} byte "
            "reconciliation artifact limit"
        )


def analysis_runtime_contract() -> dict:
    """Describe the interpreter contract for descriptive numeric outputs."""
    return {
        "schema_version": 1,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
    }


def _category(automated_difference: float, human_difference: float) -> str:
    """Classify two directional differences according to the frozen contract."""
    if automated_difference == 0 and human_difference == 0:
        return "both_tie"
    if automated_difference == 0:
        return "automated_tie"
    if human_difference == 0:
        return "human_tie"
    if automated_difference > 0 and human_difference > 0:
        return "concordant_positive"
    if automated_difference < 0 and human_difference < 0:
        return "concordant_negative"
    return "discordant"


def _dimension_result(tasks, automated_result, human_result):
    auto_by_task = dict(zip(tasks, automated_result["task_differences"]))
    included = list(human_result["task_ids_included"])
    missing = list(human_result["missing_pair_tasks"])
    human_by_task = human_result["task_differences"]

    taskwise = []
    counts = {category: 0 for category in CATEGORIES}
    automated_values = []
    human_values = []
    for task_id in included:
        automated_difference = float(auto_by_task[task_id])
        human_difference = float(human_by_task[task_id])
        category = _category(automated_difference, human_difference)
        counts[category] += 1
        automated_values.append(automated_difference)
        human_values.append(human_difference)
        taskwise.append(
            {
                "task_id": task_id,
                "automated_difference": automated_difference,
                "human_difference": human_difference,
                "direction_category": category,
            }
        )

    denominator = (
        counts["concordant_positive"]
        + counts["concordant_negative"]
        + counts["discordant"]
    )
    if included:
        automated_mean = statistics.mean(automated_values)
        human_mean = statistics.mean(human_values)
        mean_category = _category(automated_mean, human_mean)
    else:
        automated_mean = None
        human_mean = None
        mean_category = None

    return {
        "n_comparable_tasks": len(included),
        "task_ids_included": included,
        "missing_pair_tasks": missing,
        "direction_category_counts": counts,
        "non_tie_directional_concordance": (
            (counts["concordant_positive"] + counts["concordant_negative"]) / denominator
            if denominator
            else None
        ),
        "mean_automated_difference_on_comparable_tasks": automated_mean,
        "mean_human_difference_on_comparable_tasks": human_mean,
        "mean_direction_category": mean_category,
        "taskwise": taskwise,
    }


def reconcile_payloads(automated: dict, human: dict) -> dict:
    """Execute only the descriptive operations frozen before human unblinding."""
    identity = readiness.validate_payloads(automated, human)
    tasks = identity["task_ids"]

    results = {}
    for contrast in readiness.CONTRASTS:
        results[contrast] = {}
        automated_result = automated["primary_contrasts"][contrast]
        for dimension in readiness.DIMS:
            results[contrast][dimension] = _dimension_result(
                tasks,
                automated_result,
                human["paired_contrasts"][contrast][dimension],
            )

    return {
        "schema_version": 1,
        "study_id": readiness.STUDY,
        "status": "automated_human_descriptive_reconciliation",
        "analysis_scope": "descriptive_reconciliation_only",
        "primary_outcome": "strict_support_rate",
        "human_dimensions": list(readiness.DIMS),
        "contrasts": list(readiness.CONTRASTS),
        "task_ids": tasks,
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests_added": False,
        "method": {
            "task_pairing": "same_frozen_task_id",
            "missingness": "preserve_missing_human_pairs_without_imputation",
            "direction_categories": list(CATEGORIES),
            "non_tie_directional_concordance_denominator": (
                "concordant_positive + concordant_negative + discordant"
            ),
            "inference": "descriptive_only",
        },
        "results": results,
    }


def reconcile_verified(root=ROOT, human_root=None, contract=None) -> dict:
    """Run reconciliation from bytes bound to a passing readiness receipt."""
    root = Path(root)
    human_root = Path(human_root) if human_root else root / readiness.HUMAN_ROOT
    contract = Path(contract) if contract else root / readiness.CONTRACT

    receipt = readiness.verify_readiness(
        root=root,
        human_root=human_root,
        contract=contract,
    )

    paths = {
        "automated_analysis": root / readiness.AUTO_JSON,
        "human_analysis": human_root / "analysis.json",
    }
    with readiness._capture_regular_inputs(paths) as captured:
        verified = receipt["verified_input_fingerprints"]
        for name, content in captured.items():
            current = readiness._fingerprint(content)
            readiness._require(
                current == verified.get(name),
                f"{name} changed after readiness verification",
            )

        result = reconcile_payloads(
            readiness._load(captured["automated_analysis"], "automated analysis"),
            readiness._load(captured["human_analysis"], "human analysis"),
        )
        result["verified_input_fingerprints"] = verified
        result["verification"] = {
            **receipt["verification"],
            "reconciliation_inputs_bound_to_readiness_receipt": True,
            "reconciliation_inputs_descriptor_bound": True,
        }
        return result


def render_markdown(payload: dict) -> str:
    """Render a compact manuscript-facing view deterministically from canonical JSON."""
    lines = [
        "# Automated–human descriptive reconciliation",
        "",
        "Descriptive reconciliation only; automated confirmatory and human-validation "
        "claims remain separate.",
        "",
        "| Contrast | Human dimension | Comparable tasks | Non-tie concordance | Mean direction |",
        "|---|---|---:|---:|---|",
    ]
    for contrast in readiness.CONTRASTS:
        for dimension in readiness.DIMS:
            block = payload["results"][contrast][dimension]
            concordance = block["non_tie_directional_concordance"]
            concordance_text = "NA" if concordance is None else f"{concordance:.3f}"
            mean_direction = block["mean_direction_category"] or "NA"
            lines.append(
                f"| {contrast} | {dimension} | {block['n_comparable_tasks']} | "
                f"{concordance_text} | {mean_direction} |"
            )
    lines += [
        "",
        "Missing human pairs are preserved without imputation. No reconciliation "
        "p-values, multiplicity rules, correlations, composite scores, or treatment-"
        "validation thresholds are added.",
        "",
    ]
    return "\n".join(lines)


def _fingerprint_bytes(content: bytes) -> dict:
    return {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def _regular_file_bytes(path: Path, *, label: str) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _implementation_fingerprint(path: Path, *, logical_path: str) -> dict:
    content = _regular_file_bytes(path, label=f"reconciliation implementation {logical_path}")
    return {"path": logical_path, **_fingerprint_bytes(content)}


def implementation_source_specs(output_verifier_path: Path):
    """Return every source file that can authorize reconciliation inputs/results."""
    return (
        (
            "reconciler",
            Path(__file__),
            "scripts/reconcile_human_automated.py",
            "reconciler implementation",
        ),
        (
            "readiness_gate",
            Path(readiness.__file__),
            "scripts/verify_human_reconciliation_readiness.py",
            "readiness-gate implementation",
        ),
        (
            "reconciliation_verifier",
            Path(output_verifier_path),
            "scripts/verify_human_reconciliation_outputs.py",
            "reconciliation verifier implementation",
        ),
        (
            "main_study_analyzer",
            Path(readiness.analyze_main_study.__file__),
            "scripts/analyze_main_study.py",
            "main-study analyzer implementation",
        ),
        (
            "human_analysis_core",
            Path(readiness.human_core.__file__),
            "scripts/human_eval_analysis_core.py",
            "human analysis core implementation",
        ),
        (
            "automated_provenance_verifier",
            Path(readiness.verify_analysis_provenance.__file__),
            "scripts/verify_analysis_provenance.py",
            "automated provenance verifier implementation",
        ),
        (
            "human_analysis_output_verifier",
            Path(readiness.verify_human_eval_analysis_outputs.__file__),
            "scripts/verify_human_eval_analysis_outputs.py",
            "human analysis output verifier implementation",
        ),
        (
            "main_study_execution_verifier",
            Path(readiness.verify_main_study_execution.__file__),
            "scripts/verify_main_study_execution.py",
            "main-study execution verifier implementation",
        ),
        (
            "main_study_output_verifier",
            Path(readiness.verify_main_study_outputs.__file__),
            "scripts/verify_main_study_outputs.py",
            "main-study output verifier implementation",
        ),
        (
            "automated_provenance_builder",
            Path(build_analysis_provenance.__file__),
            "scripts/build_analysis_provenance.py",
            "automated provenance builder implementation",
        ),
        (
            "research_artifact_fingerprinter",
            Path(fingerprint_research_artifacts.__file__),
            "scripts/fingerprint_research_artifacts.py",
            "research artifact fingerprinter implementation",
        ),
        (
            "research_artifact_manifest_verifier",
            Path(verify_research_artifact_manifest.__file__),
            "scripts/verify_research_artifact_manifest.py",
            "research artifact manifest verifier implementation",
        ),
        (
            "human_analysis_renderer",
            Path(analyze_human_eval.__file__),
            "scripts/analyze_human_eval.py",
            "human analysis renderer implementation",
        ),
        (
            "human_freeze_verifier",
            Path(verify_human_eval_freeze.__file__),
            "scripts/verify_human_eval_freeze.py",
            "human freeze verifier implementation",
        ),
        (
            "human_packet_builder",
            Path(build_human_eval_packet.__file__),
            "scripts/build_human_eval_packet.py",
            "human packet builder implementation",
        ),
        (
            "human_packet_verifier",
            Path(verify_human_eval_packet.__file__),
            "scripts/verify_human_eval_packet.py",
            "human packet verifier implementation",
        ),
        (
            "human_ratings_freezer",
            Path(freeze_human_eval_ratings.__file__),
            "scripts/freeze_human_eval_ratings.py",
            "human ratings freezer implementation",
        ),
        (
            "human_annotator_bundle_exporter",
            Path(export_human_eval_annotator_bundle.__file__),
            "scripts/export_human_eval_annotator_bundle.py",
            "human annotator bundle exporter implementation",
        ),
        (
            "human_submission_preflight_verifier",
            Path(verify_human_eval_submission_preflight.__file__),
            "scripts/verify_human_eval_submission_preflight.py",
            "human submission preflight verifier implementation",
        ),
    )


def _producer_commit(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("unable to resolve producing Git commit") from exc
    sha = completed.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("producing Git commit must be a full 40-character SHA")
    return sha


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with Path(path).open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite reconciliation artifact: {path}") from exc


def _open_bound_directory(path: Path, *, dir_fd: int | None = None) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        directory_fd = os.open(path, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise ValueError(
            f"reconciliation staging root must be a regular directory: {path}"
        ) from exc
    if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
        os.close(directory_fd)
        raise ValueError(
            f"reconciliation staging root must be a regular directory: {path}"
        )
    return directory_fd


def _require_directory_entry_binding(
    parent_fd: int,
    name: str,
    directory_fd: int,
    *,
    label: str,
) -> None:
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(
            f"reconciliation {label} changed during publication: {name}"
        ) from exc
    opened = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise ValueError(
            f"reconciliation {label} changed during publication: {name}"
        )


def _require_directory_path_binding(
    path: Path,
    directory_fd: int,
    *,
    label: str,
) -> None:
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(
            f"reconciliation {label} changed during publication: {path}"
        ) from exc
    opened = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise ValueError(
            f"reconciliation {label} changed during publication: {path}"
        )


def _publish_directory_noreplace(
    source_parent_fd: int,
    source_name: str,
    destination_parent_fd: int,
    destination_name: str,
    *,
    output_root: Path,
) -> None:
    """Atomically install a verified result without replacing any path."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise ValueError(
            "atomic no-replace reconciliation publication is unavailable on this platform"
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    if (
        renameat2(
            source_parent_fd,
            os.fsencode(source_name),
            destination_parent_fd,
            os.fsencode(destination_name),
            1,
        )
        == 0
    ):
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ValueError(f"refusing to overwrite reconciliation output: {output_root}")
    raise OSError(
        error_number,
        f"could not atomically publish reconciliation output: {output_root}",
    )


def write_bundle(payload: dict, output_root: Path, *, root: Path = ROOT) -> dict:
    """Publish and independently verify a create-only reconciliation bundle."""
    from scripts import verify_human_reconciliation_outputs as output_verifier

    output_root = Path(output_root)
    destination_error = f"refusing to overwrite reconciliation output: {output_root}"
    if output_root.exists() or output_root.is_symlink():
        raise ValueError(destination_error)

    # Complete all deterministic validation and provenance capture before
    # reserving the publication path. A bad payload or unavailable Git/source
    # provenance must not leave a partial create-only bundle that blocks a
    # corrected publication attempt at the same versioned destination.
    try:
        json_bytes = (
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8")
    except ValueError as exc:
        raise ValueError("non-finite reconciliation values are invalid JSON") from exc
    markdown_bytes = render_markdown(payload).encode("utf-8")
    _require_reconciliation_artifact_size(json_bytes, label="canonical reconciliation JSON")
    _require_reconciliation_artifact_size(markdown_bytes, label="reconciliation Markdown")

    verified_inputs = payload.get("verified_input_fingerprints")
    if not isinstance(verified_inputs, dict) or not verified_inputs:
        raise ValueError("reconciliation payload lacks verified input fingerprints")

    producer_git_commit = _producer_commit(Path(root))
    implementation = {
        name: _implementation_fingerprint(path, logical_path=logical_path)
        for name, path, logical_path, _label in implementation_source_specs(
            Path(output_verifier.__file__)
        )
    }
    analysis_environment = {
        "requirements": _implementation_fingerprint(
            ANALYSIS_REQUIREMENTS,
            logical_path="requirements.txt",
        ),
        "ci_requirements": _implementation_fingerprint(
            ANALYSIS_CI_REQUIREMENTS,
            logical_path="requirements-ci.lock",
        ),
        "python_version": _implementation_fingerprint(
            ANALYSIS_PYTHON_VERSION,
            logical_path=".python-version",
        ),
        "runtime": analysis_runtime_contract(),
    }
    manifest = {
        "schema_version": 1,
        "study_id": payload.get("study_id"),
        "status": "automated_human_reconciliation_bundle",
        "producer_git_commit": producer_git_commit,
        "verified_input_fingerprints": verified_inputs,
        "artifacts": {
            "canonical_reconciliation": {
                "path": RECONCILIATION_JSON,
                **_fingerprint_bytes(json_bytes),
            },
            "manuscript_rendering": {
                "path": RECONCILIATION_MARKDOWN,
                **_fingerprint_bytes(markdown_bytes),
            },
        },
        "implementation": implementation,
        "analysis_environment": analysis_environment,
        "integrity_note": MANIFEST_INTEGRITY_NOTE,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _require_reconciliation_artifact_size(manifest_bytes, label="reconciliation output manifest")

    output_verifier._verify_producer_commit_implementation(
        producer_git_commit,
        implementation,
        root=Path(root),
    )
    output_verifier._verify_producer_commit_environment(
        producer_git_commit,
        analysis_environment,
        root=Path(root),
    )

    # Build and independently verify the complete result off-path. The final
    # destination remains absent until one atomic no-replace publication step.
    output_root.parent.mkdir(parents=True, exist_ok=True)
    # The private 0700 container and retained dirfds isolate normal concurrent
    # publishers. As with the other research publishers, a hostile same-UID or
    # root process can still mutate owned files and is outside the threat model.
    with ExitStack() as descriptors:
        output_parent_fd = _open_bound_directory(output_root.parent)
        descriptors.callback(os.close, output_parent_fd)
        _require_directory_path_binding(
            output_root.parent,
            output_parent_fd,
            label="output parent",
        )
        anchored_output_parent = Path(f"/proc/self/fd/{output_parent_fd}")
        staging_container = Path(
            tempfile.mkdtemp(
                prefix=f".{output_root.name}.staging-",
                dir=anchored_output_parent,
            )
        )
        staging_container_name = staging_container.name
        _require_directory_path_binding(
            output_root.parent,
            output_parent_fd,
            label="output parent",
        )
        staging_container_fd = _open_bound_directory(
            staging_container_name,
            dir_fd=output_parent_fd,
        )
        descriptors.callback(os.close, staging_container_fd)
        _require_directory_entry_binding(
            output_parent_fd,
            staging_container_name,
            staging_container_fd,
            label="staging container",
        )
        candidate_name = "candidate"
        os.mkdir(candidate_name, mode=0o700, dir_fd=staging_container_fd)
        candidate_fd = _open_bound_directory(
            candidate_name,
            dir_fd=staging_container_fd,
        )
        descriptors.callback(os.close, candidate_fd)

        candidate_root = (
            Path(f"/proc/self/fd/{staging_container_fd}") / candidate_name
        )

        _write_exclusive(candidate_root / RECONCILIATION_JSON, json_bytes)
        _write_exclusive(candidate_root / RECONCILIATION_MARKDOWN, markdown_bytes)
        _write_exclusive(candidate_root / RECONCILIATION_MANIFEST, manifest_bytes)
        # Persist artifact contents and the candidate/source directory entries
        # before making the verified bundle visible. Atomic rename alone does
        # not make either the files or their directory metadata crash-durable.
        os.fsync(candidate_fd)
        os.fsync(staging_container_fd)

        # Resolve the verifier's path through the retained container fd, so an
        # external rename/replacement of the hidden container cannot redirect
        # verification to different bytes.
        receipt = output_verifier.verify_bundle(candidate_root, root=Path(root))
        _require_directory_entry_binding(
            staging_container_fd,
            candidate_name,
            candidate_fd,
            label="staged candidate",
        )
        _require_directory_path_binding(
            output_root.parent,
            output_parent_fd,
            label="output parent",
        )
        _publish_directory_noreplace(
            staging_container_fd,
            candidate_name,
            output_parent_fd,
            output_root.name,
            output_root=output_root,
        )
        # The move updates both source and destination directories. Sync both
        # before reporting success so a completed command cannot precede the
        # durable publication record.
        os.fsync(staging_container_fd)
        os.fsync(output_parent_fd)
        _require_directory_entry_binding(
            output_parent_fd,
            output_root.name,
            candidate_fd,
            label="published output",
        )
        _require_directory_path_binding(
            output_root.parent,
            output_parent_fd,
            label="output parent",
        )
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--human-root", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    try:
        result = reconcile_verified(args.root, args.human_root, args.contract)
        write_bundle(result, args.output_root, root=args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"HUMAN RECONCILIATION: FAIL: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    print("HUMAN RECONCILIATION: PASS (result bundle verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
