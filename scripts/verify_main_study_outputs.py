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

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = Path("outputs/main_study_inference.json")
DEFAULT_MARKDOWN = Path("paper/MAIN_STUDY_INFERENCE.md")


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

    try:
        payload = _parse_canonical_json(json_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"canonical inference JSON is malformed: {exc}") from exc

    try:
        expected = analyze_main_study._markdown(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"canonical inference JSON does not satisfy the renderer schema: {exc}") from exc

    actual = markdown_file.read_text(encoding="utf-8")
    # Keep this byte-for-byte aligned with analyze_main_study.main(), which writes
    # _markdown(payload) directly without appending or stripping whitespace.
    if actual != expected:
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
