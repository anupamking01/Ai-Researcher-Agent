"""Audit continuity from a verified counterbalanced submission pair to a blinded freeze.

Read-only coordinator audit: no treatment key, report scoring, human-rating
generation, or changes to the frozen protocol and estimands.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as freeze_verify

ORDERS = ("canonical", "reverse")
MAX_RECEIPT_BYTES = 64 * 1024


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _object(data: bytes, label: str) -> dict:
    try:
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc
    _require(type(parsed) is dict, f"{label} must be an object")
    return parsed


def _digest(value) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _pinned_pair(path: Path, independently_pinned_sha256: str):
    _require(_digest(independently_pinned_sha256),
             "independent pair receipt SHA-256 must be lowercase 64-hex")
    data = freeze._capture_regular_input(path, label="pair receipt")
    _require(len(data) <= MAX_RECEIPT_BYTES, "pair receipt exceeds resource bound")
    _require(hashlib.sha256(data).hexdigest() == independently_pinned_sha256,
             "pair receipt does not match independent SHA-256")
    pair = _object(data, "pair receipt")
    _require(set(pair) == {
        "schema_version", "study_id", "status", "n_reports",
        "coordinator_manifest_sha256", "presentation_orders",
        "distinct_annotator_pseudonyms", "submissions", "interpretation",
    }, "pair receipt has missing or unexpected fields")
    _require(
        type(pair["schema_version"]) is int and pair["schema_version"] == 1
        and pair["study_id"] == "budget-main-v1"
        and pair["status"] == "human_eval_counterbalanced_submissions_source_bound"
        and pair["presentation_orders"] == list(ORDERS)
        and pair["distinct_annotator_pseudonyms"] is True
        and _digest(pair["coordinator_manifest_sha256"])
        and type(pair["interpretation"]) is str and bool(pair["interpretation"]),
        "pair receipt identity or counterbalance contract mismatch",
    )
    count = pair["n_reports"]
    _require(type(count) is int and count >= 2, "invalid pair report count")
    submissions = pair["submissions"]
    _require(type(submissions) is dict and set(submissions) == set(ORDERS),
             "pair must contain canonical and reverse submissions")
    for order in ORDERS:
        sub = submissions[order]
        _require(type(sub) is dict and set(sub) == {
            "submission_sha256", "annotator_manifest_sha256",
            "n_reports", "n_missing_dimension_values",
        }, f"{order} submission receipt schema mismatch")
        missing = sub["n_missing_dimension_values"]
        _require(
            _digest(sub["submission_sha256"])
            and _digest(sub["annotator_manifest_sha256"])
            and type(sub["n_reports"]) is int and sub["n_reports"] == count
            and type(missing) is int
            and 0 <= missing <= count * len(freeze.SCORE_FIELDS),
            f"{order} submission receipt values invalid",
        )
    _require(
        submissions["canonical"]["submission_sha256"]
        != submissions["reverse"]["submission_sha256"],
        "pair must represent distinct submitted bytes",
    )
    return data, pair


def verify_counterbalanced_freeze_link(
    *,
    freeze_root: Path,
    pair_receipt_path: Path,
    expected_pair_receipt_sha256: str,
    expected_n_reports: int = 40,
) -> dict:
    """Require exact pre-freeze submission hashes and orders in the verified archive."""
    _require(type(expected_n_reports) is int and expected_n_reports >= 2,
             "expected report count must be an integer >= 2")
    freeze_root = Path(freeze_root)
    pair_receipt_path = Path(pair_receipt_path)
    prior_bytes, pair = _pinned_pair(pair_receipt_path, expected_pair_receipt_sha256)
    _require(pair["n_reports"] == expected_n_reports,
             "pair receipt report count disagrees with expected count")
    initial = freeze_verify._capture_freeze_inventory(freeze_root)
    verified = freeze_verify.verify_frozen_snapshot(
        freeze_root=freeze_root, use_retained_inputs=True
    )
    _require(
        verified["status"] == "blinded_human_ratings_verified"
        and verified["blinding_key_used"] is False,
        "frozen snapshot has no verified blinded status",
    )
    raw_manifest = freeze._capture_regular_input(
        freeze_root / "freeze_manifest.json", label="freeze manifest"
    )
    manifest = _object(raw_manifest, "freeze manifest")
    inputs = manifest.get("rating_inputs")
    preflights = manifest.get("submission_preflights")
    _require(type(inputs) is list and len(inputs) == 2
             and type(preflights) is list and len(preflights) == 2,
             "exactly two archived rating inputs and submission preflights required")
    packet = manifest.get("packet")
    _require(type(packet) is dict and packet.get("n_blind_ids") == expected_n_reports,
             "frozen packet report count mismatch")
    observed = set()
    canonical_packet = None
    for index, (source, preflight) in enumerate(zip(inputs, preflights), start=1):
        _require(type(source) is dict and type(preflight) is dict
                 and source.get("input_index") == index
                 and preflight.get("input_index") == index,
                 "frozen input/preflight ordinal mismatch")
        order = preflight.get("presentation_order")
        _require(order in ORDERS and order not in observed,
                 "frozen preflights lack opposite presentation orders")
        observed.add(order)
        expected = pair["submissions"][order]
        _require(source.get("sha256") == expected["submission_sha256"],
                 f"{order} archived raw rating differs from pre-freeze pair")
        stored_path = (
            freeze_root / freeze.SUBMISSION_PREFLIGHT_ARCHIVE_ROOT
            / f"{index:04d}" / "receipt" / "preflight_receipt.json"
        )
        retained = _object(
            freeze._capture_regular_input(stored_path, label=f"{order} retained receipt"),
            f"{order} retained receipt",
        )
        submitted = retained.get("submission")
        _require(
            type(submitted) is dict
            and retained.get("presentation_order") == order
            and submitted.get("sha256") == expected["submission_sha256"]
            and retained.get("annotator_manifest_sha256")
                == expected["annotator_manifest_sha256"]
            and retained.get("n_reports") == expected_n_reports
            and retained.get("n_missing_dimension_values")
                == expected["n_missing_dimension_values"],
            f"{order} retained preflight differs from pinned pair",
        )
        if order == "canonical":
            canonical_packet = retained.get("packet_sha256")
    _require(observed == set(ORDERS), "both presentation orders not archived")
    _require(packet.get("sha256") == canonical_packet,
             "frozen governing packet differs from canonical distribution")
    _require(freeze._capture_regular_input(
        pair_receipt_path, label="pair receipt recheck"
    ) == prior_bytes, "pair receipt changed during verification")
    _require(freeze_verify._capture_freeze_inventory(freeze_root) == initial,
             "freeze archive changed during verification")
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "counterbalanced_pair_bound_to_verified_blinded_freeze",
        "n_reports": expected_n_reports,
        "n_raw_submissions": 2,
        "both_presentation_orders_preserved": True,
        "blinding_key_used": False,
        "pair_receipt_sha256": expected_pair_receipt_sha256,
        "freeze_manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "interpretation": (
            "Coordinator-only byte-continuity check; no human identity, independence, "
            "agreement validity, treatment result, or unblinding established"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-root", required=True, type=Path)
    parser.add_argument("--pair-receipt", required=True, type=Path)
    parser.add_argument("--pair-receipt-sha256", required=True)
    parser.add_argument("--expected-n-reports", default=40, type=int)
    args = parser.parse_args()
    try:
        result = verify_counterbalanced_freeze_link(
            freeze_root=args.freeze_root, pair_receipt_path=args.pair_receipt,
            expected_pair_receipt_sha256=args.pair_receipt_sha256,
            expected_n_reports=args.expected_n_reports,
        )
    except (ValueError, OSError) as exc:
        parser.exit(1, f"COUNTERBALANCED FREEZE LINK: FAIL: {exc}\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
