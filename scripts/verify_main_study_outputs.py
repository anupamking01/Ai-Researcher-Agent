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
from pathlib import Path

from scripts import analyze_main_study

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = Path("outputs/main_study_inference.json")
DEFAULT_MARKDOWN = Path("paper/MAIN_STUDY_INFERENCE.md")


def verify_outputs(
    *,
    root: Path = REPO_ROOT,
    json_path: Path = DEFAULT_JSON,
    markdown_path: Path = DEFAULT_MARKDOWN,
) -> None:
    """Require the Markdown result to be an exact rendering of canonical JSON."""
    json_file = json_path if json_path.is_absolute() else root / json_path
    markdown_file = markdown_path if markdown_path.is_absolute() else root / markdown_path

    if not json_file.is_file():
        raise ValueError(f"canonical inference JSON is missing: {json_file}")
    if not markdown_file.is_file():
        raise ValueError(f"manuscript inference Markdown is missing: {markdown_file}")

    try:
        payload = json.loads(json_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"canonical inference JSON is malformed: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("canonical inference JSON must contain an object")

    try:
        expected = analyze_main_study._markdown(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"canonical inference JSON does not satisfy the renderer schema: {exc}") from exc

    actual = markdown_file.read_text(encoding="utf-8")
    # analyze_main_study writes exactly one trailing newline after _markdown().
    expected_file = expected + "\n"
    if actual != expected_file:
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
