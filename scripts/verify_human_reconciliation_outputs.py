"""Verify a published automated-human reconciliation result bundle.

Verification is offline and read-only. It checks byte-level provenance,
deterministic manuscript rendering, implementation fingerprints, and
independently recomputes the frozen descriptive reconciliation from the same
verified automated and human analysis artifacts. It does not generate ratings,
rerun treatments/evaluators, or add inferential tests.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from scripts import reconcile_human_automated as reconcile
from scripts import verify_human_reconciliation_readiness as readiness


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


def _require_equal(actual, expected, *, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def _verify_entry(entry, *, expected_path: str, content: bytes, label: str) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} manifest entry must be an object")
    _require_equal(entry.get("path"), expected_path, label=f"{label} path")
    _require_equal(
        {"bytes": entry.get("bytes"), "sha256": entry.get("sha256")},
        reconcile._fingerprint_bytes(content),
        label=f"{label} fingerprint",
    )


def _validate_identity(payload: dict) -> None:
    expected = {
        "schema_version": 1,
        "study_id": readiness.STUDY,
        "status": "automated_human_descriptive_reconciliation",
        "analysis_scope": "descriptive_reconciliation_only",
        "primary_outcome": "strict_support_rate",
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests_added": False,
    }
    for key, value in expected.items():
        _require_equal(payload.get(key), value, label=f"reconciliation {key}")
    _require_equal(
        payload.get("human_dimensions"),
        list(readiness.DIMS),
        label="reconciliation human dimensions",
    )
    _require_equal(
        payload.get("contrasts"),
        list(readiness.CONTRASTS),
        label="reconciliation contrasts",
    )
    method = payload.get("method")
    if not isinstance(method, dict):
        raise ValueError("reconciliation method must be an object")
    _require_equal(
        method,
        {
            "task_pairing": "same_frozen_task_id",
            "missingness": "preserve_missing_human_pairs_without_imputation",
            "direction_categories": list(reconcile.CATEGORIES),
            "non_tie_directional_concordance_denominator": (
                "concordant_positive + concordant_negative + discordant"
            ),
            "inference": "descriptive_only",
        },
        label="reconciliation method",
    )


def verify_bundle(
    output_root: Path = reconcile.OUTPUT_ROOT,
    *,
    root: Path = reconcile.ROOT,
    human_root: Path | None = None,
    contract: Path | None = None,
) -> dict:
    """Verify a saved bundle and independently recompute its canonical result."""
    output_root = Path(output_root)
    if output_root.is_symlink() or not output_root.is_dir():
        raise ValueError(f"reconciliation output root must be a regular directory: {output_root}")

    json_bytes = _regular_bytes(
        output_root / reconcile.RECONCILIATION_JSON,
        label="canonical reconciliation JSON",
    )
    markdown_bytes = _regular_bytes(
        output_root / reconcile.RECONCILIATION_MARKDOWN,
        label="reconciliation Markdown",
    )
    manifest_bytes = _regular_bytes(
        output_root / reconcile.RECONCILIATION_MANIFEST,
        label="reconciliation output manifest",
    )

    payload = _load_json(json_bytes, label="canonical reconciliation JSON")
    manifest = _load_json(manifest_bytes, label="reconciliation output manifest")
    _validate_identity(payload)

    expected_markdown = reconcile.render_markdown(payload).encode("utf-8")
    if markdown_bytes != expected_markdown:
        raise ValueError(
            "reconciliation Markdown does not match canonical JSON; regenerate the "
            "bundle instead of editing manuscript-facing results by hand"
        )

    _require_equal(manifest.get("schema_version"), 1, label="manifest schema_version")
    _require_equal(manifest.get("study_id"), payload["study_id"], label="manifest study_id")
    _require_equal(
        manifest.get("status"),
        "automated_human_reconciliation_bundle",
        label="manifest status",
    )
    producer = manifest.get("producer_git_commit")
    if not isinstance(producer, str) or not re.fullmatch(r"[0-9a-f]{40}", producer):
        raise ValueError("manifest producer_git_commit must be a full 40-character SHA")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("reconciliation manifest artifacts must be an object")
    _require_equal(
        set(artifacts),
        {"canonical_reconciliation", "manuscript_rendering"},
        label="reconciliation manifest artifact set",
    )
    _verify_entry(
        artifacts["canonical_reconciliation"],
        expected_path=reconcile.RECONCILIATION_JSON,
        content=json_bytes,
        label="canonical reconciliation",
    )
    _verify_entry(
        artifacts["manuscript_rendering"],
        expected_path=reconcile.RECONCILIATION_MARKDOWN,
        content=markdown_bytes,
        label="manuscript rendering",
    )

    verified_inputs = payload.get("verified_input_fingerprints")
    if not isinstance(verified_inputs, dict) or not verified_inputs:
        raise ValueError("canonical reconciliation lacks verified input fingerprints")
    _require_equal(
        manifest.get("verified_input_fingerprints"),
        verified_inputs,
        label="manifest verified input fingerprints",
    )

    implementation = manifest.get("implementation")
    if not isinstance(implementation, dict):
        raise ValueError("reconciliation manifest implementation must be an object")
    _require_equal(
        set(implementation),
        {"reconciler", "readiness_gate"},
        label="reconciliation manifest implementation set",
    )
    _verify_entry(
        implementation["reconciler"],
        expected_path="scripts/reconcile_human_automated.py",
        content=_regular_bytes(Path(reconcile.__file__), label="current reconciler"),
        label="reconciler implementation",
    )
    _verify_entry(
        implementation["readiness_gate"],
        expected_path="scripts/verify_human_reconciliation_readiness.py",
        content=_regular_bytes(Path(readiness.__file__), label="current readiness gate"),
        label="readiness-gate implementation",
    )

    recomputed = reconcile.reconcile_verified(
        root=Path(root),
        human_root=human_root,
        contract=contract,
    )
    _require_equal(recomputed, payload, label="independently recomputed reconciliation")

    return {
        "schema_version": 1,
        "study_id": payload["study_id"],
        "status": "automated_human_reconciliation_bundle_verified",
        "analysis_scope": payload["analysis_scope"],
        "producer_git_commit": producer,
        "canonical_reconciliation_sha256": reconcile._fingerprint_bytes(json_bytes)["sha256"],
        "manuscript_rendering_sha256": reconcile._fingerprint_bytes(markdown_bytes)["sha256"],
        "verified_input_fingerprints_bound": True,
        "implementation_bound": True,
        "independent_recomputation_verified": True,
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests_added": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=reconcile.OUTPUT_ROOT)
    parser.add_argument("--root", type=Path, default=reconcile.ROOT)
    parser.add_argument("--human-root", type=Path)
    parser.add_argument("--contract", type=Path)
    args = parser.parse_args()
    try:
        receipt = verify_bundle(
            args.output_root,
            root=args.root,
            human_root=args.human_root,
            contract=args.contract,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"HUMAN RECONCILIATION VERIFY: FAIL: {exc}") from exc
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("HUMAN RECONCILIATION VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
