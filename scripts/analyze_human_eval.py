"""Run the frozen complementary human-evaluation analysis offline.

The published result bundle is create-only and includes an output manifest that
binds the canonical JSON, deterministic Markdown rendering, and the exact
analysis implementation files used to produce them. The bundle is verified
after writing before the CLI reports success.
"""
import argparse
import hashlib
import json
from pathlib import Path

from scripts import human_eval_analysis_core as core

OUTPUT_ROOT = core.PACKET_ROOT / "analysis-v1"
ANALYSIS_JSON = "analysis.json"
ANALYSIS_MARKDOWN = "analysis.md"
ANALYSIS_MANIFEST = "analysis_manifest.json"


def render_markdown(payload):
    def fmt(value):
        return "NA" if value is None else f"{value:.3f}"

    lines = [
        "# Human-evaluation analysis",
        "",
        "Complementary validation; not part of the automated confirmatory p-value family.",
        "",
        "| Dimension | D3 | D6 | P6 | P6V |",
        "|---|---:|---:|---:|---:|",
    ]
    for field in core.DIMS:
        means = [
            fmt(payload["variant_summary"][variant][field]["mean_report_score"])
            for variant in core.VARIANTS
        ]
        lines.append(f"| {field} | " + " | ".join(means) + " |")
    lines += [
        "",
        "Missing scores are not imputed. "
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
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite human-analysis artifact: {path}") from exc


def write_bundle(payload, output_root):
    """Publish and verify a create-only human-analysis result bundle."""
    output_root = Path(output_root)
    try:
        output_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError(
            f"refusing to overwrite human-analysis output: {output_root}"
        ) from exc

    json_bytes = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    markdown_bytes = render_markdown(payload).encode("utf-8")

    json_path = output_root / ANALYSIS_JSON
    markdown_path = output_root / ANALYSIS_MARKDOWN
    manifest_path = output_root / ANALYSIS_MANIFEST

    _write_exclusive(json_path, json_bytes)
    _write_exclusive(markdown_path, markdown_bytes)

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
        "implementation": {
            "analysis_core": _implementation_fingerprint(
                core.__file__,
                logical_path="scripts/human_eval_analysis_core.py",
            ),
            "analysis_renderer": _implementation_fingerprint(
                __file__,
                logical_path="scripts/analyze_human_eval.py",
            ),
        },
        "integrity_note": (
            "The manifest binds the exact canonical analysis JSON, deterministic "
            "Markdown rendering, and analysis implementation source bytes. "
            "It is written last and independently verified before success is reported."
        ),
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_exclusive(manifest_path, manifest_bytes)

    from scripts.verify_human_eval_analysis_outputs import verify_bundle
    return verify_bundle(output_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ratings", nargs="+", type=Path)
    parser.add_argument("--freeze-root", type=Path, default=core.FREEZE_ROOT)
    parser.add_argument("--packet-root", type=Path, default=core.PACKET_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--analysis-plan", type=Path, default=core.PLAN)
    parser.add_argument("--task-manifest", type=Path, default=core.TASKS)
    args = parser.parse_args()
    try:
        payload = core.analyze(
            args.ratings,
            freeze_root=args.freeze_root,
            packet_root=args.packet_root,
            analysis_plan_path=args.analysis_plan,
            task_manifest_path=args.task_manifest,
        )
        write_bundle(payload, args.output_root)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL ANALYSIS: FAIL: {exc}") from exc
    print(json.dumps(payload, indent=2, sort_keys=True))
    print("HUMAN EVAL ANALYSIS: PASS (result bundle verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
