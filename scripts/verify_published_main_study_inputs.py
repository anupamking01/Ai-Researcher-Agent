"""Guard VERA's published frozen input fingerprint against coherent local rewrites.

Unlike a self-recomputed artifact manifest, this check pins the historical
aggregate digest published with the canonical main-study analysis. It is
an offline repository regression gate, not an external signature or a new
statistical analysis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.verify_research_artifact_manifest import verify_manifest_file

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "outputs/main_study_analysis_inputs_manifest.json"
FROZEN_INPUT_AGGREGATE_SHA256 = (
    "4e94308472e87cc14b85e5911c40b5f72c63225862a347e624fc0725afd632aa"
)
FROZEN_INPUTS = (
    "outputs/main_study_runs.csv",
    "outputs/posthoc_support_runs.csv",
)


def verify_published_frozen_inputs(
    *,
    repo_root: Path = ROOT,
    manifest_path: Path | None = None,
    expected_manifest_sha256: str | None = None,
) -> dict:
    """Verify the saved manifest AND its independently published aggregate.

    The existing manifest verifier checks exact contents, pathname safety,
    duplicate identities, and coherent file capture. This final fixed anchor
    prevents an accidental or convenient simultaneous rewrite of the CSVs
    and their local manifest from silently redefining the frozen analysis.
    """
    root = Path(repo_root)
    entries = verify_manifest_file(
        Path(manifest_path) if manifest_path is not None else root / MANIFEST,
        root=root,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    if {entry["path"] for entry in entries} != set(FROZEN_INPUTS):
        raise ValueError("published frozen inputs must contain exactly the two canonical CSVs")
    serialized = json.dumps(
        sorted(entries, key=lambda item: item["path"]),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    actual = hashlib.sha256(serialized).hexdigest()
    if actual != FROZEN_INPUT_AGGREGATE_SHA256:
        raise ValueError(
            "published frozen input aggregate SHA-256 mismatch: "
            "the input CSVs or locally saved manifest no longer match the "
            "historically published research fingerprint"
        )
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "published_frozen_input_fingerprint_matches",
        "n_input_artifacts": len(entries),
        "published_aggregate_sha256": FROZEN_INPUT_AGGREGATE_SHA256,
        "experimental_treatments_rerun": False,
        "human_ratings_used": False,
        "interpretation": (
            "Offline guard against accidental canonical input drift; not "
            "independent authentication of the historical archive"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--manifest-path", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    try:
        result = verify_published_frozen_inputs(
            repo_root=args.repo_root,
            manifest_path=args.manifest_path,
            expected_manifest_sha256=args.expected_manifest_sha256,
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"PUBLISHED FROZEN MAIN-STUDY INPUTS: FAIL: {exc}\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
