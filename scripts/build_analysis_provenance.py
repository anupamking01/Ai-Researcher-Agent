"""Build a deterministic provenance receipt for manuscript-facing inference.

The receipt binds exact input bytes to the frozen analysis implementation,
analysis plan, pinned dependency environment, interpreter contract, and both
verification implementations. It contains no experimental conclusions and makes no
network calls. A changed dataset, analysis script, preregistered plan, dependency
specification, Python version contract, or verifier necessarily changes the receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts import analyze_main_study
from scripts.verify_research_artifact_manifest import REPO_ROOT, verify_manifest

ANALYSIS_SCRIPT = "scripts/analyze_main_study.py"
ANALYSIS_PLAN = "paper/ANALYSIS_PLAN.md"
ANALYSIS_REQUIREMENTS = "requirements.txt"
ANALYSIS_PYTHON_VERSION = ".python-version"
ANALYSIS_VERIFIER = "scripts/verify_analysis_provenance.py"
ANALYSIS_OUTPUT_VERIFIER = "scripts/verify_main_study_outputs.py"


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"required analysis artifact is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_receipt(manifest: dict, *, root: Path = REPO_ROOT) -> dict:
    """Return deterministic provenance for inputs, code, plan, environment, and knobs.

    The validated manifest entries are embedded in the receipt rather than only
    retaining their aggregate digest. This lets an independent reviewer later
    re-verify the exact input files without needing the original manifest as a
    separate sidecar artifact.
    """
    verified_inputs = verify_manifest(manifest, root=root)
    return {
        "schema_version": 1,
        "input_manifest_aggregate_sha256": manifest["aggregate_sha256"],
        "verified_inputs": verified_inputs,
        "analysis_implementation": {
            "path": ANALYSIS_SCRIPT,
            "sha256": _sha256(root / ANALYSIS_SCRIPT),
        },
        "analysis_plan": {
            "path": ANALYSIS_PLAN,
            "sha256": _sha256(root / ANALYSIS_PLAN),
        },
        "analysis_environment": {
            "requirements": {
                "path": ANALYSIS_REQUIREMENTS,
                "sha256": _sha256(root / ANALYSIS_REQUIREMENTS),
            },
            "python_version": {
                "path": ANALYSIS_PYTHON_VERSION,
                "sha256": _sha256(root / ANALYSIS_PYTHON_VERSION),
            },
        },
        "verification_implementations": {
            "provenance": {
                "path": ANALYSIS_VERIFIER,
                "sha256": _sha256(root / ANALYSIS_VERIFIER),
            },
            "output_consistency": {
                "path": ANALYSIS_OUTPUT_VERIFIER,
                "sha256": _sha256(root / ANALYSIS_OUTPUT_VERIFIER),
            },
        },
        "frozen_configuration": {
            "variants": list(analyze_main_study.VARIANTS),
            "primary_contrasts": [list(item) for item in analyze_main_study.PRIMARY_CONTRASTS],
            "bootstrap_seed": analyze_main_study.BOOTSTRAP_SEED,
            "bootstrap_draws": analyze_main_study.BOOTSTRAP_DRAWS,
            "expected_tasks": analyze_main_study.EXPECTED_TASKS,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/main_study_analysis_provenance.json"))
    args = parser.parse_args()
    manifest_path = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    output = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        receipt = build_receipt(manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"ANALYSIS PROVENANCE: FAIL: {exc}") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"ANALYSIS PROVENANCE: PASS: {output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
