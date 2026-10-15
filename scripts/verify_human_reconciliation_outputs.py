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
import os
import re
import subprocess
from pathlib import Path

from scripts import reconcile_human_automated as reconcile
from scripts import verify_human_reconciliation_readiness as readiness


def _regular_bytes(path: Path, *, label: str) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _load_json(content: bytes, *, label: str) -> dict:
    payload = readiness._load(content, label)
    # Re-encoding in strict mode also catches exponent-overflow JSON numbers
    # (e.g. 1e400), which permissive json.loads converts to infinity.
    try:
        json.dumps(payload, allow_nan=False)
    except ValueError as exc:
        raise ValueError(f"{label} contains non-finite JSON numbers") from exc
    return payload


def _require_equal(actual, expected, *, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def _canonical_json_bytes(value) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _verify_entry(entry, *, expected_path: str, content: bytes, label: str) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} manifest entry must be an object")
    _require_equal(entry.get("path"), expected_path, label=f"{label} path")
    _require_equal(
        {"bytes": entry.get("bytes"), "sha256": entry.get("sha256")},
        reconcile._fingerprint_bytes(content),
        label=f"{label} fingerprint",
    )


def _verify_exact_entry(entry, *, expected_path: str, content: bytes, label: str) -> None:
    """Verify a fingerprint entry without JSON numeric coercion or extra keys."""
    if not isinstance(entry, dict) or set(entry) != {"path", "bytes", "sha256"}:
        raise ValueError(
            f"{label} manifest entry must contain exactly path, bytes, and sha256"
        )
    if (
        not isinstance(entry["path"], str)
        or not isinstance(entry["bytes"], int)
        or isinstance(entry["bytes"], bool)
        or not isinstance(entry["sha256"], str)
    ):
        raise ValueError(
            f"{label} manifest entry must use string path/sha256 and integer bytes"
        )
    _verify_entry(
        entry,
        expected_path=expected_path,
        content=content,
        label=label,
    )


def _verify_producer_commit_implementation(
    producer: str,
    implementation: dict,
    *,
    root: Path,
) -> None:
    """Bind the recorded producer commit to the manifest's exact source bytes."""
    root = Path(root)
    git_env = {
        **os.environ,
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    try:
        object_type = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-t", producer],
            check=True,
            capture_output=True,
            env=git_env,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError(
            f"producer Git commit cannot be resolved: {producer}"
        ) from exc
    if object_type != "commit":
        raise ValueError(
            f"producer Git SHA must identify a commit object, got {object_type!r}"
        )

    for name in ("reconciler", "readiness_gate", "reconciliation_verifier"):
        entry = implementation[name]
        path = entry["path"]
        try:
            content = subprocess.run(
                ["git", "-C", str(root), "show", f"{producer}:{path}"],
                check=True,
                capture_output=True,
                env=git_env,
                timeout=10,
            ).stdout
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError(
                f"producer {name} cannot be read from commit {producer}: {path}"
            ) from exc
        _require_equal(
            reconcile._fingerprint_bytes(content),
            {"bytes": entry.get("bytes"), "sha256": entry.get("sha256")},
            label=f"producer {name} fingerprint",
        )


def _verify_producer_commit_environment(
    producer: str,
    environment: dict,
    *,
    root: Path,
) -> None:
    """Bind pinned environment bytes to the recorded producer commit."""
    root = Path(root)
    git_env = {
        **os.environ,
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    try:
        object_type = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-t", producer],
            check=True,
            capture_output=True,
            env=git_env,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError(
            f"producer Git commit cannot be resolved: {producer}"
        ) from exc
    if object_type != "commit":
        raise ValueError(
            f"producer Git SHA must identify a commit object, got {object_type!r}"
        )

    for name, path in (
        ("requirements", "requirements.txt"),
        ("python_version", ".python-version"),
    ):
        entry = environment[name]
        try:
            content = subprocess.run(
                ["git", "-C", str(root), "show", f"{producer}:{path}"],
                check=True,
                capture_output=True,
                env=git_env,
                timeout=10,
            ).stdout
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ValueError(
                f"producer {name} cannot be read from commit {producer}: {path}"
            ) from exc
        _require_equal(
            reconcile._fingerprint_bytes(content),
            {"bytes": entry.get("bytes"), "sha256": entry.get("sha256")},
            label=f"producer {name} fingerprint",
        )


def _verify_analysis_environment(manifest: dict) -> dict:
    """Verify current pins and the exact runtime contract before result trust."""
    environment = manifest.get("analysis_environment")
    if not isinstance(environment, dict) or set(environment) != {
        "requirements",
        "python_version",
        "runtime",
    }:
        raise ValueError(
            "analysis environment must bind requirements, Python version, and runtime"
        )
    _verify_exact_entry(
        environment["requirements"],
        expected_path="requirements.txt",
        content=_regular_bytes(
            reconcile.ANALYSIS_REQUIREMENTS,
            label="current analysis requirements",
        ),
        label="analysis requirements",
    )
    _verify_exact_entry(
        environment["python_version"],
        expected_path=".python-version",
        content=_regular_bytes(
            reconcile.ANALYSIS_PYTHON_VERSION,
            label="current analysis Python version contract",
        ),
        label="analysis Python version contract",
    )
    expected_runtime = reconcile.analysis_runtime_contract()
    if _canonical_json_bytes(environment["runtime"]) != _canonical_json_bytes(
        expected_runtime
    ):
        raise ValueError(
            "analysis runtime contract mismatch: "
            f"expected {expected_runtime!r}, got {environment['runtime']!r}"
        )
    return environment


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
    analysis_environment = _verify_analysis_environment(manifest)
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
        {"reconciler", "readiness_gate", "reconciliation_verifier"},
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
    _verify_entry(
        implementation["reconciliation_verifier"],
        expected_path="scripts/verify_human_reconciliation_outputs.py",
        content=_regular_bytes(Path(__file__), label="current reconciliation verifier"),
        label="reconciliation verifier implementation",
    )
    _verify_producer_commit_implementation(
        producer,
        implementation,
        root=Path(root),
    )
    _verify_producer_commit_environment(
        producer,
        analysis_environment,
        root=Path(root),
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
        "analysis_environment_bound": True,
        "implementation_bound": True,
        "producer_commit_environment_bound": True,
        "producer_commit_implementation_bound": True,
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
