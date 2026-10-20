"""Run the frozen complementary human-evaluation analysis offline.

The published result bundle is create-only and includes an output manifest that
binds the canonical JSON, deterministic Markdown rendering, and the exact
analysis and publication-verification implementation files used to produce and
validate them. The bundle is verified after writing before the CLI reports
success.
"""
import argparse
import ctypes
import errno
import hashlib
import json
import os
import platform
import stat
import tempfile
from contextlib import ExitStack
from pathlib import Path

from scripts import freeze_human_eval_ratings as freeze
from scripts import human_eval_analysis_core as core

OUTPUT_ROOT = core.PACKET_ROOT / "analysis-v1"
ANALYSIS_JSON = "analysis.json"
ANALYSIS_MARKDOWN = "analysis.md"
ANALYSIS_MANIFEST = "analysis_manifest.json"
ANALYSIS_VERIFIER_SOURCE = Path(__file__).with_name(
    "verify_human_eval_analysis_outputs.py"
)
ANALYSIS_REQUIREMENTS = core.ROOT / "requirements.txt"
ANALYSIS_CI_REQUIREMENTS = core.ROOT / "requirements-ci.lock"
ANALYSIS_PYTHON_VERSION = core.ROOT / ".python-version"
ANALYSIS_INTEGRITY_NOTE = (
    "The manifest binds the exact canonical analysis JSON, deterministic "
    "Markdown rendering, analysis/verification implementation source "
    "bytes, governing-input anchor and verifier implementation bytes, "
    "pinned environment files, and actual Python/PRNG runtime contract. "
    "It is written last; the analysis command independently recomputes the "
    "payload from verified inputs before the result is published."
)


def analysis_runtime_contract() -> dict:
    """Describe the interpreter and PRNG state contract for numeric outputs."""
    return {
        "schema_version": 1,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "random_state_version": core.random.Random.VERSION,
    }


def render_markdown(payload):
    def fmt(value):
        return "NA" if value is None else f"{value:.3f}"

    def cell(value):
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("|", "\\|")
            .replace("\r\n", " ")
            .replace("\r", " ")
            .replace("\n", " ")
        )

    def joined(values):
        return ", ".join(cell(value) for value in values) if values else "—"

    lines = [
        "# Human-evaluation analysis",
        "",
        "Complementary validation; not part of the automated confirmatory p-value family.",
        "",
        "## Variant summaries",
        "",
        "| Variant | Dimension | Reports scored/total | Raw scores | Mean | Median | Raw counts (1–5) |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for variant in core.VARIANTS:
        for field in core.DIMS:
            block = payload["variant_summary"][variant][field]
            distribution = block["raw_score_distribution"]
            counts = "; ".join(
                f"{score}:{distribution[str(score)]}" for score in range(1, 6)
            )
            lines.append(
                f"| {variant} | {field} | "
                f"{block['n_reports_scored']}/{block['n_reports_total']} | "
                f"{block['n_raw_scores']} | {fmt(block['mean_report_score'])} | "
                f"{fmt(block['median_report_score'])} | {counts} |"
            )

    lines += [
        "",
        "## Paired contrasts",
        "",
        "Differences are right minus left. Confidence intervals use the frozen "
        f"paired bootstrap ({payload['bootstrap_draws']:,} draws; base seed "
        f"{payload['bootstrap_seed']}).",
        "",
        "| Contrast | Dimension | Included tasks | Missing tasks | Left mean | Right mean | Mean difference | Median difference | Paired dz | 95% bootstrap CI | +/−/tie | Task differences |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---|",
    ]
    for _, _, contrast in core.CONTRASTS:
        for field in core.DIMS:
            block = payload["paired_contrasts"][contrast][field]
            interval = block["bootstrap_95pct_ci_mean_difference"]
            interval_text = (
                "NA" if interval is None else f"[{fmt(interval[0])}, {fmt(interval[1])}]"
            )
            differences = "; ".join(
                f"{cell(task_id)}:{fmt(block['task_differences'][task_id])}"
                for task_id in block["task_ids_included"]
            ) or "—"
            lines.append(
                f"| {contrast} | {field} | {joined(block['task_ids_included'])} | "
                f"{joined(block['missing_pair_tasks'])} | {fmt(block['left_mean'])} | "
                f"{fmt(block['right_mean'])} | {fmt(block['mean_difference'])} | "
                f"{fmt(block['median_difference'])} | {fmt(block['paired_dz'])} | "
                f"{interval_text} | "
                f"{block['positive_tasks']}/{block['negative_tasks']}/{block['tied_tasks']} | "
                f"{differences} |"
            )

    agreement = payload["pre_unblinding_agreement"]
    lines += [
        "",
        "## Pre-unblinding agreement",
        "",
        f"Frozen agreement artifact status: `{cell(agreement['status'])}`; "
        f"annotators: {agreement['n_annotators']}.",
        "",
        "| Annotator pair | Dimension | Double-rated | Exact agreement | Mean absolute difference | Quadratic-weighted kappa |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for pair in agreement["pairwise"]:
        pair_label = f"{cell(pair['annotator_a'])} / {cell(pair['annotator_b'])}"
        for field in core.DIMS:
            block = pair["dimensions"][field]
            lines.append(
                f"| {pair_label} | {field} | {block['n_double_rated']} | "
                f"{fmt(block['raw_exact_agreement'])} | "
                f"{fmt(block['mean_absolute_difference'])} | "
                f"{fmt(block['quadratic_weighted_cohen_kappa'])} |"
            )

    lines += [
        "",
        "Missing scores and incomplete task pairs are retained explicitly and are not "
        "imputed. Raw distributions and task-level differences remain visible so "
        "ordinal scores and cross-task consistency are not reduced to means alone. "
        "No human-validation null-hypothesis p-values are computed.",
        "",
    ]
    return "\n".join(lines)


def _fingerprint_bytes(content):
    return {
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _regular_file_bytes(path, *, label):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _implementation_fingerprint(path, *, logical_path):
    content = _regular_file_bytes(path, label=f"analysis implementation {logical_path}")
    return {
        "path": logical_path,
        **_fingerprint_bytes(content),
    }


def _write_exclusive(path, content):
    path = Path(path)
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite human-analysis artifact: {path}") from exc


def _open_bound_directory(path, *, dir_fd=None):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        directory_fd = os.open(path, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise ValueError(
            f"human-analysis staging root must be a regular directory: {path}"
        ) from exc
    try:
        is_directory = stat.S_ISDIR(os.fstat(directory_fd).st_mode)
    except BaseException:
        os.close(directory_fd)
        raise
    if not is_directory:
        os.close(directory_fd)
        raise ValueError(
            f"human-analysis staging root must be a regular directory: {path}"
        )
    return directory_fd


def _ensure_output_parent(path):
    """Create missing output-parent directories with durable parent entries."""
    path = Path(path)
    missing = []
    existing = path
    while not existing.exists():
        if existing.is_symlink():
            raise ValueError(
                f"human-analysis output parent must be a regular directory: {path}"
            )
        missing.append(existing)
        parent = existing.parent
        if parent == existing:
            break
        existing = parent
    if existing.is_symlink() or not existing.is_dir():
        raise ValueError(
            f"human-analysis output parent must be a regular directory: {path}"
        )

    with ExitStack() as descriptors:
        parent_fd = _open_bound_directory(existing)
        descriptors.callback(os.close, parent_fd)
        for directory in reversed(missing):
            try:
                os.mkdir(directory.name, mode=0o777, dir_fd=parent_fd)
            except FileExistsError as exc:
                raise ValueError(
                    "human-analysis output parent changed during durable creation: "
                    f"{directory}"
                ) from exc
            directory_fd = _open_bound_directory(directory.name, dir_fd=parent_fd)
            descriptors.callback(os.close, directory_fd)
            _require_directory_path_binding(
                directory,
                directory_fd,
                label="new output parent",
            )
            os.fsync(directory_fd)
            os.fsync(parent_fd)
            parent_fd = directory_fd


def _require_directory_entry_binding(parent_fd, name, directory_fd, *, label):
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(
            f"human-analysis {label} changed during publication: {name}"
        ) from exc
    opened = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise ValueError(
            f"human-analysis {label} changed during publication: {name}"
        )


def _require_directory_path_binding(path, directory_fd, *, label):
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(
            f"human-analysis {label} changed during publication: {path}"
        ) from exc
    opened = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise ValueError(
            f"human-analysis {label} changed during publication: {path}"
        )


def _publish_directory(
    source_parent_fd,
    source_name,
    destination_parent_fd,
    destination_name,
    *,
    output_root,
):
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise ValueError(
            "atomic no-replace human-analysis publication is unavailable on this platform"
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
        raise ValueError(f"refusing to overwrite human-analysis output: {output_root}")
    raise OSError(
        error_number,
        f"could not atomically publish human-analysis output: {output_root}",
    )


def write_bundle(payload, output_root, *, verify_candidate=None):
    """Verify off-path, then publish a create-only human-analysis result bundle."""
    output_root = Path(output_root)
    destination_error = f"refusing to overwrite human-analysis output: {output_root}"
    if output_root.exists() or output_root.is_symlink():
        raise ValueError(destination_error)

    # Validate the complete canonical JSON before reserving the immutable
    # destination. A missing rubric score must be null, never NaN/Infinity.
    try:
        json_bytes = (
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8")
    except ValueError as exc:
        raise ValueError(
            "non-finite human-analysis values are invalid; use null for missing scores"
        ) from exc
    markdown_bytes = render_markdown(payload).encode("utf-8")

    from scripts.verify_human_eval_analysis_outputs import (
        _validate_analysis_identity,
        verify_bundle,
    )

    # A create-only version path should not be consumed by a deterministic
    # identity or source-provenance failure. Complete that preflight, including
    # every source read needed by the manifest, before reserving the directory.
    _validate_analysis_identity(payload)
    implementation = {
        "analysis_core": _implementation_fingerprint(
            core.__file__,
            logical_path="scripts/human_eval_analysis_core.py",
        ),
        "analysis_renderer": _implementation_fingerprint(
            __file__,
            logical_path="scripts/analyze_human_eval.py",
        ),
        "analysis_verifier": _implementation_fingerprint(
            ANALYSIS_VERIFIER_SOURCE,
            logical_path="scripts/verify_human_eval_analysis_outputs.py",
        ),
        "blinded_freeze_verifier": _implementation_fingerprint(
            core.blind_verify.__file__,
            logical_path="scripts/verify_human_eval_freeze.py",
        ),
        "packet_builder": _implementation_fingerprint(
            core.packet.__file__,
            logical_path="scripts/build_human_eval_packet.py",
        ),
        "packet_verifier": _implementation_fingerprint(
            core.map_verify.__file__,
            logical_path="scripts/verify_human_eval_packet.py",
        ),
        "ratings_freezer": _implementation_fingerprint(
            freeze.__file__,
            logical_path="scripts/freeze_human_eval_ratings.py",
        ),
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
        "status": "human_validation_analysis_bundle",
        "artifacts": {
            "canonical_analysis": {
                "path": ANALYSIS_JSON,
                **_fingerprint_bytes(json_bytes),
            },
            "manuscript_rendering": {
                "path": ANALYSIS_MARKDOWN,
                **_fingerprint_bytes(markdown_bytes),
            },
        },
        "implementation": implementation,
        "analysis_environment": analysis_environment,
        "integrity_note": ANALYSIS_INTEGRITY_NOTE,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")

    _ensure_output_parent(output_root.parent)
    # The private random 0700 container and retained dirfds isolate normal
    # concurrent publishers. Hostile same-UID or root mutation of owned paths
    # during the creation-to-open interval is outside this threat model.
    with ExitStack() as descriptors:
        output_parent_fd = _open_bound_directory(output_root.parent)
        descriptors.callback(os.close, output_parent_fd)
        _require_directory_path_binding(
            output_root.parent,
            output_parent_fd,
            label="output parent",
        )

        # Create every staging entry relative to the retained output-parent fd.
        # A pathname replacement of that parent can therefore be detected without
        # redirecting setup or writes into the replacement directory.
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

        anchored_candidate = (
            Path(f"/proc/self/fd/{staging_container_fd}") / candidate_name
        )

        json_path = anchored_candidate / ANALYSIS_JSON
        markdown_path = anchored_candidate / ANALYSIS_MARKDOWN
        manifest_path = anchored_candidate / ANALYSIS_MANIFEST

        _write_exclusive(json_path, json_bytes)
        _write_exclusive(markdown_path, markdown_bytes)
        _write_exclusive(manifest_path, manifest_bytes)
        # Persist artifact contents and the candidate/source directory entries
        # before making the verified bundle visible. Atomic rename alone does
        # not make either the files or their directory metadata crash-durable.
        os.fsync(candidate_fd)
        os.fsync(staging_container_fd)

        receipt = verify_bundle(anchored_candidate)
        if verify_candidate is not None:
            receipt = verify_candidate(anchored_candidate)
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
        _publish_directory(
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ratings", nargs="+", type=Path)
    parser.add_argument("--freeze-root", type=Path, default=core.FREEZE_ROOT)
    parser.add_argument("--packet-root", type=Path, default=core.PACKET_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--analysis-plan", type=Path, default=core.PLAN)
    parser.add_argument("--task-manifest", type=Path, default=core.TASKS)
    parser.add_argument(
        "--annotator-guide",
        type=Path,
        default=core.freeze.DEFAULT_ANNOTATOR_GUIDE,
    )
    args = parser.parse_args()
    try:
        payload = core.analyze(
            args.ratings,
            freeze_root=args.freeze_root,
            packet_root=args.packet_root,
            annotator_guide_path=args.annotator_guide,
            analysis_plan_path=args.analysis_plan,
            task_manifest_path=args.task_manifest,
        )
        from scripts.verify_human_eval_analysis_outputs import (
            verify_bundle_against_inputs,
        )

        def verify_candidate(candidate_root):
            return verify_bundle_against_inputs(
                candidate_root,
                rating_paths=args.ratings,
                freeze_root=args.freeze_root,
                packet_root=args.packet_root,
                annotator_guide_path=args.annotator_guide,
                analysis_plan_path=args.analysis_plan,
                task_manifest_path=args.task_manifest,
            )

        write_bundle(
            payload,
            args.output_root,
            verify_candidate=verify_candidate,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL ANALYSIS: FAIL: {exc}") from exc
    print(json.dumps(payload, indent=2, sort_keys=True))
    print("HUMAN EVAL ANALYSIS: PASS (result bundle verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
