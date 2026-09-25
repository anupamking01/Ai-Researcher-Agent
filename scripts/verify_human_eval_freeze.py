"""Verify a blinded human-evaluation freeze before any unblinding.

The verifier never reads the coordinator-only blinding key. It checks that the
frozen outputs, archived raw rating inputs, blinded packet, protocol, and
assignment plan still match the freeze manifest, then independently recomputes
the normalized ratings, assignment coverage, and pre-unblinding agreement.

No ratings are generated, imputed, adjudicated, or joined to treatment labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts import freeze_human_eval_ratings as freeze


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FREEZE_ROOT = REPO_ROOT / "outputs" / "human_eval" / "frozen-v1"
DEFAULT_PACKET = freeze.DEFAULT_PACKET
DEFAULT_PROTOCOL = freeze.DEFAULT_PROTOCOL
DEFAULT_ASSIGNMENT_PLAN = freeze.DEFAULT_ASSIGNMENT_PLAN


def _require_regular_file(path: Path, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _load_json_bytes(content: bytes, *, label: str) -> dict:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _fingerprint(content: bytes) -> dict:
    return {
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _require_equal(actual, expected, *, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def verify_frozen_snapshot(
    rating_paths: list[Path],
    *,
    freeze_root: Path = DEFAULT_FREEZE_ROOT,
    packet_path: Path = DEFAULT_PACKET,
    protocol_path: Path = DEFAULT_PROTOCOL,
    assignment_plan_path: Path = DEFAULT_ASSIGNMENT_PLAN,
) -> dict:
    """Verify a frozen blinded snapshot and its retained pre-unblinding inputs."""
    freeze_root = Path(freeze_root)
    packet_path = Path(packet_path)
    protocol_path = Path(protocol_path)
    assignment_plan_path = Path(assignment_plan_path)
    rating_paths = [Path(path) for path in rating_paths]

    if freeze_root.is_symlink() or not freeze_root.is_dir():
        raise ValueError(f"freeze root must be a regular directory: {freeze_root}")
    if not rating_paths:
        raise ValueError("archived raw rating CSVs are required for freeze verification")

    manifest_path = freeze_root / "freeze_manifest.json"
    manifest_content = _require_regular_file(manifest_path, label="freeze manifest")
    manifest = _load_json_bytes(manifest_content, label="freeze manifest")

    _require_equal(manifest.get("schema_version"), 1, label="freeze manifest schema_version")
    _require_equal(manifest.get("study_id"), "budget-main-v1", label="freeze manifest study_id")
    _require_equal(
        manifest.get("status"),
        "blinded_human_ratings_frozen",
        label="freeze manifest status",
    )
    _require_equal(manifest.get("blinding_key_used"), False, label="blinding_key_used")

    packet_content = _require_regular_file(packet_path, label="blinded packet")
    protocol_content = _require_regular_file(protocol_path, label="human-evaluation protocol")
    assignment_content = _require_regular_file(
        assignment_plan_path,
        label="human-evaluation assignment plan",
    )
    blind_ids = freeze._packet_blind_ids(packet_path, content=packet_content)

    packet_entry = manifest.get("packet")
    if not isinstance(packet_entry, dict):
        raise ValueError("freeze manifest packet entry must be an object")
    _require_equal(packet_entry.get("name"), packet_path.name, label="packet name")
    _require_equal(
        {"bytes": packet_entry.get("bytes"), "sha256": packet_entry.get("sha256")},
        _fingerprint(packet_content),
        label="packet fingerprint",
    )
    _require_equal(packet_entry.get("n_blind_ids"), len(blind_ids), label="packet blind-id count")

    protocol_entry = manifest.get("protocol")
    if not isinstance(protocol_entry, dict):
        raise ValueError("freeze manifest protocol entry must be an object")
    _require_equal(
        protocol_entry.get("path"),
        "paper/HUMAN_EVAL_PROTOCOL.md",
        label="protocol manifest path",
    )
    _require_equal(
        protocol_entry.get("sha256"),
        hashlib.sha256(protocol_content).hexdigest(),
        label="protocol fingerprint",
    )

    assignment_entry = manifest.get("assignment_plan")
    if not isinstance(assignment_entry, dict):
        raise ValueError("freeze manifest assignment_plan entry must be an object")
    _require_equal(
        assignment_entry.get("path"),
        "paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md",
        label="assignment-plan manifest path",
    )
    _require_equal(
        assignment_entry.get("sha256"),
        hashlib.sha256(assignment_content).hexdigest(),
        label="assignment-plan fingerprint",
    )

    raw_rows, raw_sources = freeze._load_ratings(
        rating_paths,
        allowed_blind_ids=set(blind_ids),
    )
    _require_equal(manifest.get("rating_inputs"), raw_sources, label="raw rating inputs")

    frozen_entry = manifest.get("frozen_ratings")
    if not isinstance(frozen_entry, dict):
        raise ValueError("freeze manifest frozen_ratings entry must be an object")
    _require_equal(
        frozen_entry.get("path"),
        "frozen_ratings.csv",
        label="frozen-ratings manifest path",
    )
    frozen_path = freeze_root / "frozen_ratings.csv"
    frozen_content = _require_regular_file(frozen_path, label="frozen ratings")
    _require_equal(
        {"bytes": frozen_entry.get("bytes"), "sha256": frozen_entry.get("sha256")},
        _fingerprint(frozen_content),
        label="frozen-ratings fingerprint",
    )

    frozen_rows, _ = freeze._load_ratings(
        [frozen_path],
        allowed_blind_ids=set(blind_ids),
    )
    _require_equal(frozen_rows, raw_rows, label="frozen ratings versus normalized raw inputs")

    coverage = freeze._validate_assignment_coverage(frozen_rows, blind_ids)
    _require_equal(manifest.get("assignment_coverage"), coverage, label="assignment coverage")

    dimension_counts = {}
    for field in freeze.SCORE_FIELDS:
        rated = sum(freeze._score(row, field) is not None for row in frozen_rows)
        dimension_counts[field] = {
            "rated": rated,
            "missing": len(frozen_rows) - rated,
        }

    _require_equal(frozen_entry.get("n_rows"), len(frozen_rows), label="frozen row count")
    _require_equal(
        frozen_entry.get("n_annotators"),
        len({row["annotator_id"] for row in frozen_rows}),
        label="frozen annotator count",
    )
    _require_equal(
        frozen_entry.get("n_unique_blind_ids_rated"),
        len({row["blind_id"] for row in frozen_rows}),
        label="frozen blind-id count",
    )
    _require_equal(
        frozen_entry.get("dimension_counts"),
        dimension_counts,
        label="frozen dimension counts",
    )

    agreement_entry = manifest.get("agreement")
    if not isinstance(agreement_entry, dict):
        raise ValueError("freeze manifest agreement entry must be an object")
    _require_equal(
        agreement_entry.get("path"),
        "agreement.json",
        label="agreement manifest path",
    )
    agreement_path = freeze_root / "agreement.json"
    agreement_content = _require_regular_file(agreement_path, label="agreement output")
    _require_equal(
        {"bytes": agreement_entry.get("bytes"), "sha256": agreement_entry.get("sha256")},
        _fingerprint(agreement_content),
        label="agreement fingerprint",
    )
    stored_agreement = _load_json_bytes(agreement_content, label="agreement output")
    recomputed_agreement = freeze.build_agreement(frozen_rows)
    _require_equal(stored_agreement, recomputed_agreement, label="recomputed agreement")

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "blinded_human_ratings_verified",
        "blinding_key_used": False,
        "n_raw_rating_inputs": len(rating_paths),
        "n_rows": len(frozen_rows),
        "n_annotators": len({row["annotator_id"] for row in frozen_rows}),
        "n_blind_ids": len(blind_ids),
        "requires_predeclared_multi_rater_statistic": recomputed_agreement[
            "requires_predeclared_multi_rater_statistic"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ratings",
        nargs="+",
        type=Path,
        help="archived completed annotator CSV files used for the freeze, in original order",
    )
    parser.add_argument("--freeze-root", type=Path, default=DEFAULT_FREEZE_ROOT)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--assignment-plan", type=Path, default=DEFAULT_ASSIGNMENT_PLAN)
    args = parser.parse_args()

    try:
        receipt = verify_frozen_snapshot(
            args.ratings,
            freeze_root=args.freeze_root,
            packet_path=args.packet,
            protocol_path=args.protocol,
            assignment_plan_path=args.assignment_plan,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL VERIFY: FAIL: {exc}") from exc

    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("HUMAN EVAL VERIFY: PASS (ratings remain blinded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
