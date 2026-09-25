"""Verify a published human-evaluation analysis result bundle.

The canonical JSON is the machine-readable human-validation result. Markdown is
only a deterministic rendering of that JSON. The manifest must bind both output
byte streams and the exact analysis implementation source files used to produce
them. This verifier makes no model/API calls and does not generate ratings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts import analyze_human_eval
from scripts import human_eval_analysis_core as core

DEFAULT_OUTPUT_ROOT = analyze_human_eval.OUTPUT_ROOT


def _regular_bytes(path: Path, *, label: str) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _load_json(content: bytes, *, label: str) -> dict:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _fingerprint(content: bytes) -> dict:
    return {
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _require_equal(actual, expected, *, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def _verify_entry(entry, *, expected_path: str, content: bytes, label: str) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} manifest entry must be an object")
    _require_equal(entry.get("path"), expected_path, label=f"{label} path")
    _require_equal(
        {"bytes": entry.get("bytes"), "sha256": entry.get("sha256")},
        _fingerprint(content),
        label=f"{label} fingerprint",
    )


def _validate_analysis_identity(payload: dict) -> None:
    required = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "human_validation_analysis",
        "analysis_scope": "complementary_not_main_confirmatory",
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests": "none_predeclared_for_human_validation",
    }
    for key, expected in required.items():
        _require_equal(payload.get(key), expected, label=f"analysis {key}")

    _require_equal(payload.get("variants"), list(core.VARIANTS), label="analysis variants")
    _require_equal(payload.get("dimensions"), list(core.DIMS), label="analysis dimensions")


def verify_bundle(output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    """Verify exact outputs, deterministic rendering, and implementation hashes."""
    output_root = Path(output_root)
    if output_root.is_symlink() or not output_root.is_dir():
        raise ValueError(f"human-analysis output root must be a regular directory: {output_root}")

    json_path = output_root / analyze_human_eval.ANALYSIS_JSON
    markdown_path = output_root / analyze_human_eval.ANALYSIS_MARKDOWN
    manifest_path = output_root / analyze_human_eval.ANALYSIS_MANIFEST

    json_bytes = _regular_bytes(json_path, label="canonical human-analysis JSON")
    markdown_bytes = _regular_bytes(markdown_path, label="human-analysis Markdown")
    manifest_bytes = _regular_bytes(manifest_path, label="human-analysis output manifest")

    payload = _load_json(json_bytes, label="canonical human-analysis JSON")
    manifest = _load_json(manifest_bytes, label="human-analysis output manifest")
    _validate_analysis_identity(payload)

    expected_markdown = analyze_human_eval.render_markdown(payload).encode("utf-8")
    if markdown_bytes != expected_markdown:
        raise ValueError(
            "human-analysis Markdown does not match canonical JSON; regenerate the "
            "bundle instead of editing manuscript-facing results by hand"
        )

    _require_equal(manifest.get("schema_version"), 1, label="manifest schema_version")
    _require_equal(manifest.get("study_id"), payload["study_id"], label="manifest study_id")
    _require_equal(
        manifest.get("status"),
        "human_validation_analysis_bundle",
        label="manifest status",
    )

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("analysis manifest artifacts must be an object")
    _require_equal(
        set(artifacts),
        {"canonical_analysis", "manuscript_rendering"},
        label="analysis manifest artifact set",
    )
    _verify_entry(
        artifacts["canonical_analysis"],
        expected_path=analyze_human_eval.ANALYSIS_JSON,
        content=json_bytes,
        label="canonical analysis",
    )
    _verify_entry(
        artifacts["manuscript_rendering"],
        expected_path=analyze_human_eval.ANALYSIS_MARKDOWN,
        content=markdown_bytes,
        label="manuscript rendering",
    )

    implementation = manifest.get("implementation")
    if not isinstance(implementation, dict):
        raise ValueError("analysis manifest implementation must be an object")
    _require_equal(
        set(implementation),
        {"analysis_core", "analysis_renderer"},
        label="analysis manifest implementation set",
    )

    core_bytes = _regular_bytes(Path(core.__file__), label="current human-analysis core")
    renderer_bytes = _regular_bytes(
        Path(analyze_human_eval.__file__),
        label="current human-analysis renderer",
    )
    _verify_entry(
        implementation["analysis_core"],
        expected_path="scripts/human_eval_analysis_core.py",
        content=core_bytes,
        label="analysis core implementation",
    )
    _verify_entry(
        implementation["analysis_renderer"],
        expected_path="scripts/analyze_human_eval.py",
        content=renderer_bytes,
        label="analysis renderer implementation",
    )

    return {
        "schema_version": 1,
        "study_id": payload["study_id"],
        "status": "human_validation_analysis_bundle_verified",
        "analysis_scope": payload["analysis_scope"],
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "canonical_analysis_sha256": _fingerprint(json_bytes)["sha256"],
        "manuscript_rendering_sha256": _fingerprint(markdown_bytes)["sha256"],
        "implementation_bound": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    try:
        receipt = verify_bundle(args.output_root)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL ANALYSIS VERIFY: FAIL: {exc}") from exc
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("HUMAN EVAL ANALYSIS VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
