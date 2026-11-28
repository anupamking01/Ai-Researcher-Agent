"""Verify that manuscript-facing main-study outputs are internally consistent.

The canonical JSON is the machine-readable analysis result. The Markdown table is
considered a rendered view of that result, not an independently editable source.
This verifier fails closed if either artifact is missing/malformed or if the
Markdown no longer exactly matches the deterministic renderer used by the frozen
analysis implementation.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from scripts import analyze_main_study
from scripts.evaluate_posthoc_support import _read_regular_bytes

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = Path("outputs/main_study_inference.json")
DEFAULT_MARKDOWN = Path("paper/MAIN_STUDY_INFERENCE.md")
# Fail closed on unexpectedly large local artifacts, not just malformed JSON.
MAX_CANONICAL_RESULT_BYTES = 8 * 1024 * 1024


def _parse_canonical_json(content: str) -> dict:
    """Parse canonical results without ambiguous or non-standard JSON values."""

    def unique_object(pairs):
        value = {}
        for key, child in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON field: {key}")
            value[key] = child
        return value

    def reject_non_finite(token: str):
        raise ValueError(f"non-finite JSON number: {token}")

    payload = json.loads(
        content,
        object_pairs_hook=unique_object,
        parse_constant=reject_non_finite,
    )
    if not isinstance(payload, dict):
        raise ValueError("canonical inference JSON must contain an object")

    def require_finite(value, path: str = "$") -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"non-finite JSON number at {path}")
        if isinstance(value, dict):
            for key, child in value.items():
                require_finite(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                require_finite(child, f"{path}[{index}]")

    require_finite(payload)
    return payload


def verify_outputs(
    *,
    root: Path = REPO_ROOT,
    json_path: Path = DEFAULT_JSON,
    markdown_path: Path = DEFAULT_MARKDOWN,
) -> None:
    """Require the Markdown result to be the exact canonical renderer output."""
    json_file = json_path if json_path.is_absolute() else root / json_path
    markdown_file = markdown_path if markdown_path.is_absolute() else root / markdown_path

    if not json_file.is_file():
        raise ValueError(f"canonical inference JSON is missing: {json_file}")
    if not markdown_file.is_file():
        raise ValueError(f"manuscript inference Markdown is missing: {markdown_file}")

    # Capture the exact bytes from bounded, non-symlink regular sources. Path.read_text()
    # performs universal-newline translation and would accept a CRLF rewrite of
    # the manuscript as byte-identical to the frozen LF-only renderer output.
    try:
        json_bytes = _read_regular_bytes(
            json_file, label="canonical inference JSON",
            max_bytes=MAX_CANONICAL_RESULT_BYTES,
        )
        markdown_bytes = _read_regular_bytes(
            markdown_file, label="canonical inference Markdown",
            max_bytes=MAX_CANONICAL_RESULT_BYTES,
        )
    except SystemExit as exc:
        raise ValueError(f"unsafe canonical inference artifact: {exc}") from exc

    try:
        payload = _parse_canonical_json(json_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("canonical inference JSON must contain valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"canonical inference JSON is malformed: {exc}") from exc

    try:
        expected = analyze_main_study._markdown(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"canonical inference JSON does not satisfy the renderer schema: {exc}") from exc

    # Compare the exact on-disk UTF-8 stream, including line endings and BOMs.
    # This is local source consistency, not an external custody attestation.
    if markdown_bytes != expected.encode("utf-8"):
        raise ValueError(
            "manuscript inference Markdown does not match canonical JSON; "
            "regenerate it with scripts/analyze_main_study.py rather than editing results by hand"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    try:
        verify_outputs(json_path=args.json, markdown_path=args.markdown)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"MAIN-STUDY OUTPUT VERIFICATION: FAIL: {exc}") from exc
    print("MAIN-STUDY OUTPUT VERIFICATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
