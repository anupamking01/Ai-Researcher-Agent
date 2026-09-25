"""Validate and freeze blinded human-evaluation ratings before unblinding.

This module never reads the coordinator-only blinding key. It validates real
annotator CSVs against the blinded packet, enforces the frozen rubric contract,
writes an immutable blinded snapshot, fingerprints the inputs/outputs/protocol,
and reports pre-unblinding inter-annotator agreement.
See docs/HUMAN_EVAL_INPUT_PROVENANCE.md for snapshot and retention limits.
See docs/HUMAN_EVAL_OUTPUT_SAFETY.md for create-only destination rules.

No ratings are generated, imputed, adjudicated, or joined to treatment labels.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from itertools import combinations
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET = REPO_ROOT / "outputs" / "human_eval" / "packet.jsonl"
DEFAULT_PROTOCOL = REPO_ROOT / "paper" / "HUMAN_EVAL_PROTOCOL.md"
DEFAULT_ASSIGNMENT_PLAN = REPO_ROOT / "paper" / "HUMAN_EVAL_ASSIGNMENT_PLAN.md"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "human_eval" / "frozen-v1"
MIN_RATERS_PER_ITEM = 2

SCORE_FIELDS = (
    "correctness_1_5",
    "completeness_1_5",
    "source_quality_1_5",
    "synthesis_reasoning_1_5",
    "clarity_1_5",
)
RATING_FIELDS = ("annotator_id", "blind_id", *SCORE_FIELDS, "notes")
FORBIDDEN_COLUMNS = {
    "variant_id",
    "run_id",
    "task_id",
    "treatment",
    "condition",
    "model",
}
OUTPUT_FILES = (
    "frozen_ratings.csv",
    "agreement.json",
    "freeze_manifest.json",
)


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"required file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _packet_blind_ids(packet_path: Path, *, content: bytes | None = None) -> list[str]:
    if content is None:
        if not packet_path.is_file():
            raise ValueError(f"blinded packet is missing: {packet_path}")
        content = packet_path.read_bytes()

    ids: list[str] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(content.decode("utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed packet JSON on line {line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"packet line {line_number} must contain an object")
        if "variant_id" in row or "run_id" in row:
            raise ValueError("annotator packet leaks treatment/run identity")
        blind_id = str(row.get("blind_id") or "").strip()
        if not blind_id:
            raise ValueError(f"packet line {line_number} is missing blind_id")
        if blind_id in seen:
            raise ValueError(f"duplicate blind_id in packet: {blind_id}")
        seen.add(blind_id)
        ids.append(blind_id)

    if not ids:
        raise ValueError("blinded packet contains no evaluation items")
    return ids


def _parse_score(value: str, *, field: str, annotator_id: str, blind_id: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        score = int(text)
    except ValueError as exc:
        raise ValueError(
            f"{annotator_id}/{blind_id} {field} must be an integer from 1 to 5 or blank"
        ) from exc
    if str(score) != text and text not in {f"+{score}"}:
        raise ValueError(
            f"{annotator_id}/{blind_id} {field} must be an integer from 1 to 5 or blank"
        )
    if score < 1 or score > 5:
        raise ValueError(f"{annotator_id}/{blind_id} {field} is outside the 1-5 rubric")
    return score


def _load_ratings(rating_paths: list[Path], *, allowed_blind_ids: set[str]) -> tuple[list[dict], list[dict]]:
    if not rating_paths:
        raise ValueError("at least one completed annotator ratings CSV is required")

    rows: list[dict] = []
    sources: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for source_index, path in enumerate(rating_paths, start=1):
        if not path.is_file():
            raise ValueError(f"ratings file is missing: {path}")
        # Parse and fingerprint the same captured bytes. Reopening a live CSV
        # after hashing can bind one revision's digest to another's scores.
        content = path.read_bytes()
        sources.append(
            {
                "input_index": source_index,
                "name": path.name,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )

        with io.StringIO(content.decode("utf-8"), newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            # A set-only schema check loses duplicate headers; DictReader would
            # then silently replace an earlier score with the last same-name cell.
            duplicates = sorted({name for name in fieldnames if fieldnames.count(name) > 1})
            if duplicates:
                raise ValueError(f"{path.name}: duplicate ratings CSV columns: {duplicates}")
            unexpected = set(fieldnames) - set(RATING_FIELDS)
            forbidden = set(fieldnames) & FORBIDDEN_COLUMNS
            missing = set(RATING_FIELDS) - set(fieldnames)
            if forbidden:
                raise ValueError(
                    f"ratings file must stay blinded; forbidden columns present: {sorted(forbidden)}"
                )
            if missing or unexpected:
                raise ValueError(
                    "ratings CSV schema must exactly match the frozen template; "
                    f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
                )

            for raw in reader:
                line_number = reader.line_num
                # Surplus cells are stored under None, and absent cells have
                # value None. Neither is the explicit empty string allowed by
                # the rubric; reject both before normalizing or dropping data.
                if None in raw:
                    raise ValueError(f"{path.name}:{line_number}: extra ratings CSV fields")
                missing_fields = [name for name, value in raw.items() if value is None]
                if missing_fields:
                    raise ValueError(
                        f"{path.name}:{line_number}: missing ratings CSV fields: {missing_fields}"
                    )
                annotator_id = str(raw.get("annotator_id") or "").strip()
                blind_id = str(raw.get("blind_id") or "").strip()
                notes = str(raw.get("notes") or "").strip()

                if not annotator_id:
                    raise ValueError(f"{path.name}:{line_number} is missing annotator_id")
                if blind_id not in allowed_blind_ids:
                    raise ValueError(
                        f"{path.name}:{line_number} references unknown blind_id {blind_id!r}"
                    )

                key = (annotator_id, blind_id)
                if key in seen:
                    raise ValueError(
                        f"duplicate independent rating for annotator/blind item: "
                        f"{annotator_id}/{blind_id}"
                    )
                seen.add(key)

                scores = {
                    field: _parse_score(
                        raw.get(field, ""),
                        field=field,
                        annotator_id=annotator_id,
                        blind_id=blind_id,
                    )
                    for field in SCORE_FIELDS
                }
                if any(value is None for value in scores.values()) and not notes:
                    raise ValueError(
                        f"{annotator_id}/{blind_id} has an unscored dimension without a reason in notes"
                    )
                if any(value in {1, 5} for value in scores.values()) and not notes:
                    raise ValueError(
                        f"{annotator_id}/{blind_id} uses an endpoint score (1 or 5) without the required note"
                    )

                rows.append(
                    {
                        "annotator_id": annotator_id,
                        "blind_id": blind_id,
                        **{field: "" if scores[field] is None else str(scores[field]) for field in SCORE_FIELDS},
                        "notes": notes,
                    }
                )

    if not rows:
        raise ValueError("ratings files contain no annotation rows")

    rows.sort(key=lambda row: (row["annotator_id"], row["blind_id"]))
    return rows, sources


def _validate_assignment_coverage(rows: list[dict], blind_ids: list[str]) -> dict:
    """Require two distinct independent raters for every blinded report."""
    raters_by_item = {blind_id: set() for blind_id in blind_ids}
    for row in rows:
        raters_by_item[row["blind_id"]].add(row["annotator_id"])

    counts = {blind_id: len(raters) for blind_id, raters in raters_by_item.items()}
    incomplete = sorted(blind_id for blind_id, count in counts.items() if count < MIN_RATERS_PER_ITEM)
    if incomplete:
        preview = ", ".join(f"{blind_id}={counts[blind_id]}" for blind_id in incomplete[:10])
        raise ValueError(
            "human-evaluation assignment incomplete: every blinded report must have "
            f"at least {MIN_RATERS_PER_ITEM} distinct annotators before unblinding; "
            f"below requirement: {preview}"
        )

    histogram: dict[str, int] = {}
    for count in counts.values():
        key = str(count)
        histogram[key] = histogram.get(key, 0) + 1
    return {
        "required_min_raters_per_item": MIN_RATERS_PER_ITEM,
        "n_items": len(counts),
        "min_observed_raters_per_item": min(counts.values()),
        "max_observed_raters_per_item": max(counts.values()),
        "items_by_rater_count": dict(sorted(histogram.items(), key=lambda item: int(item[0]))),
    }


def _score(row: dict, field: str) -> int | None:
    value = str(row.get(field) or "").strip()
    return int(value) if value else None


def quadratic_weighted_kappa(pairs: list[tuple[int, int]]) -> float | None:
    """Return quadratic-weighted Cohen's kappa for ordinal 1-5 pairs.

    ``None`` is returned when expected weighted disagreement is zero, where
    kappa is mathematically undefined (for example both raters use one identical
    category for every overlapping item).
    """
    if not pairs:
        return None

    n = len(pairs)
    first = [0] * 5
    second = [0] * 5
    observed = [[0] * 5 for _ in range(5)]

    for left, right in pairs:
        i, j = left - 1, right - 1
        observed[i][j] += 1
        first[i] += 1
        second[j] += 1

    max_distance_sq = 16.0
    observed_disagreement = 0.0
    expected_disagreement = 0.0
    for i in range(5):
        for j in range(5):
            weight = ((i - j) ** 2) / max_distance_sq
            observed_disagreement += weight * observed[i][j] / n
            expected_disagreement += weight * (first[i] * second[j]) / (n * n)

    if expected_disagreement == 0.0:
        return None
    return 1.0 - (observed_disagreement / expected_disagreement)


def build_agreement(rows: list[dict]) -> dict:
    by_annotator: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_annotator.setdefault(row["annotator_id"], {})[row["blind_id"]] = row

    annotators = sorted(by_annotator)
    pairwise: list[dict] = []

    for left_id, right_id in combinations(annotators, 2):
        left = by_annotator[left_id]
        right = by_annotator[right_id]
        common = sorted(set(left) & set(right))
        dimensions: dict[str, dict] = {}

        for field in SCORE_FIELDS:
            pairs: list[tuple[int, int]] = []
            for blind_id in common:
                left_score = _score(left[blind_id], field)
                right_score = _score(right[blind_id], field)
                if left_score is None or right_score is None:
                    continue
                pairs.append((left_score, right_score))

            if pairs:
                exact = sum(a == b for a, b in pairs) / len(pairs)
                mean_abs = sum(abs(a - b) for a, b in pairs) / len(pairs)
            else:
                exact = None
                mean_abs = None

            dimensions[field] = {
                "n_double_rated": len(pairs),
                "raw_exact_agreement": exact,
                "mean_absolute_difference": mean_abs,
                "quadratic_weighted_cohen_kappa": quadratic_weighted_kappa(pairs),
            }

        pairwise.append(
            {
                "annotator_a": left_id,
                "annotator_b": right_id,
                "n_shared_items": len(common),
                "dimensions": dimensions,
            }
        )

    return {
        "schema_version": 1,
        "status": "pre-unblinding_pairwise_agreement",
        "n_annotators": len(annotators),
        "annotators": annotators,
        "pairwise": pairwise,
        "interpretation": (
            "For exactly two annotators, the single pair supplies the protocol's "
            "two-rater agreement statistics. With more than two annotators, these "
            "are pairwise diagnostics only; a predeclared ordinal multi-rater "
            "statistic is still required before treatment-level analysis."
        ),
        "requires_predeclared_multi_rater_statistic": len(annotators) > 2,
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(RATING_FIELDS))
        writer.writeheader()
        writer.writerows(rows)


def freeze_ratings(
    rating_paths: list[Path],
    *,
    packet_path: Path = DEFAULT_PACKET,
    protocol_path: Path = DEFAULT_PROTOCOL,
    assignment_plan_path: Path = DEFAULT_ASSIGNMENT_PLAN,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict:
    """Validate ratings and persist a blinded, fingerprinted, immutable snapshot."""
    packet_path = Path(packet_path)
    protocol_path = Path(protocol_path)
    assignment_plan_path = Path(assignment_plan_path)
    output_root = Path(output_root)

    if not protocol_path.is_file():
        raise ValueError(f"frozen human-evaluation protocol is missing: {protocol_path}")
    if not assignment_plan_path.is_file():
        raise ValueError(f"frozen human-evaluation assignment plan is missing: {assignment_plan_path}")

    destination_error = (
        "refusing to overwrite an existing human-evaluation output path: "
        f"{output_root}; choose a new, nonexistent --output-root"
    )
    if output_root.exists() or output_root.is_symlink():
        raise ValueError(destination_error)

    # Capture packet and protocol identity before processing any ratings.
    # These are per-file snapshots, not a lock on the caller's working files.
    if not packet_path.is_file():
        raise ValueError(f"blinded packet is missing: {packet_path}")
    packet_content = packet_path.read_bytes()
    protocol_sha256 = sha256_file(protocol_path)
    assignment_plan_sha256 = sha256_file(assignment_plan_path)
    blind_ids = _packet_blind_ids(packet_path, content=packet_content)
    rows, sources = _load_ratings(
        [Path(path) for path in rating_paths],
        allowed_blind_ids=set(blind_ids),
    )
    assignment_coverage = _validate_assignment_coverage(rows, blind_ids)
    agreement = build_agreement(rows)

    dimension_counts = {}
    for field in SCORE_FIELDS:
        rated = sum(_score(row, field) is not None for row in rows)
        dimension_counts[field] = {
            "rated": rated,
            "missing": len(rows) - rated,
        }

    # Reserve the destination only after validation, but before any output write.
    # The earlier existence check is not a lock: another attempt may have won
    # during validation. Never adopt its directory, even if it is still empty.
    try:
        output_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError(destination_error) from exc
    frozen_path = output_root / "frozen_ratings.csv"
    agreement_path = output_root / "agreement.json"
    manifest_path = output_root / "freeze_manifest.json"

    _write_csv(frozen_path, rows)
    agreement_path.write_text(
        json.dumps(agreement, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "blinded_human_ratings_frozen",
        "blinding_key_used": False,
        "packet": {
            "name": packet_path.name,
            "bytes": len(packet_content),
            "sha256": hashlib.sha256(packet_content).hexdigest(),
            "n_blind_ids": len(blind_ids),
        },
        "protocol": {
            "path": "paper/HUMAN_EVAL_PROTOCOL.md",
            "sha256": protocol_sha256,
        },
        "assignment_plan": {
            "path": "paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md",
            "sha256": assignment_plan_sha256,
        },
        "assignment_coverage": assignment_coverage,
        "rating_inputs": sources,
        "frozen_ratings": {
            "path": "frozen_ratings.csv",
            "bytes": frozen_path.stat().st_size,
            "sha256": sha256_file(frozen_path),
            "n_rows": len(rows),
            "n_annotators": len({row["annotator_id"] for row in rows}),
            "n_unique_blind_ids_rated": len({row["blind_id"] for row in rows}),
            "dimension_counts": dimension_counts,
        },
        "agreement": {
            "path": "agreement.json",
            "bytes": agreement_path.stat().st_size,
            "sha256": sha256_file(agreement_path),
        },
        "integrity_note": (
            "This snapshot is blinded and pre-unblinding. It validates and freezes "
            "human-entered ratings only; it does not generate, impute, adjudicate, "
            "or join ratings to treatment identities."
        ),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ratings", nargs="+", type=Path, help="completed blinded annotator CSV files")
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--assignment-plan", type=Path, default=DEFAULT_ASSIGNMENT_PLAN)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    try:
        manifest = freeze_ratings(
            args.ratings,
            packet_path=args.packet,
            protocol_path=args.protocol,
            assignment_plan_path=args.assignment_plan,
            output_root=args.output_root,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL FREEZE: FAIL: {exc}") from exc

    print(json.dumps(manifest, indent=2, sort_keys=True))
    print("HUMAN EVAL FREEZE: PASS (ratings remain blinded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
