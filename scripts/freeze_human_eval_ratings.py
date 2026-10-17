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
import ctypes
import errno
import hashlib
import io
import json
import os
import stat
import tempfile
import unicodedata
from itertools import combinations
from pathlib import Path

from scripts import build_human_eval_packet as packet_build


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET = REPO_ROOT / "outputs" / "human_eval" / "packet.jsonl"
DEFAULT_PROTOCOL = REPO_ROOT / "paper" / "HUMAN_EVAL_PROTOCOL.md"
DEFAULT_ASSIGNMENT_PLAN = REPO_ROOT / "paper" / "HUMAN_EVAL_ASSIGNMENT_PLAN.md"
DEFAULT_ANNOTATOR_GUIDE = REPO_ROOT / "paper" / "HUMAN_EVAL_ANNOTATOR_GUIDE.md"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "human_eval" / "frozen-v1"
FROZEN_PROTOCOL_SHA256 = (
    "8dadc9b25bd8f3c33dd2ddeb10b672d97c844b83cbd63101520002dcac8f409f"
)
FROZEN_ASSIGNMENT_PLAN_SHA256 = (
    "ad66f5fc97e13d93365341fd650d00951e4923c2919676922e5a97ef500def71"
)
FROZEN_ANNOTATOR_GUIDE_SHA256 = (
    "3e27ef38231ed70fe36370af31ced7762a253a72dc5cc4997d8ef62d0a6e3370"
)
MIN_RATERS_PER_ITEM = 2
PACKET_FIELDS = ("blind_id", "task_id", "question", "report_markdown")
GOVERNING_INPUT_PATHS = {
    "packet": "governing_inputs/packet.jsonl",
    "protocol": "governing_inputs/HUMAN_EVAL_PROTOCOL.md",
    "assignment_plan": "governing_inputs/HUMAN_EVAL_ASSIGNMENT_PLAN.md",
    "annotator_guide": "governing_inputs/HUMAN_EVAL_ANNOTATOR_GUIDE.md",
}

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
SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")
FREEZE_INTEGRITY_NOTE = (
    "This snapshot is blinded and pre-unblinding. It retains the exact raw "
    "rating bytes that were parsed, validates and freezes human-entered ratings "
    "only, and does not generate, impute, adjudicate, or join ratings to "
    "treatment identities."
)


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"required file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_frozen_governing_documents(
    protocol_content: bytes,
    assignment_content: bytes,
    annotator_guide_content: bytes,
) -> tuple[str, str, str]:
    """Require every frozen human-evaluation instruction byte-for-byte."""
    protocol_sha256 = hashlib.sha256(protocol_content).hexdigest()
    assignment_plan_sha256 = hashlib.sha256(assignment_content).hexdigest()
    annotator_guide_sha256 = hashlib.sha256(annotator_guide_content).hexdigest()
    if protocol_sha256 != FROZEN_PROTOCOL_SHA256:
        raise ValueError(
            "frozen human-evaluation protocol fingerprint mismatch: "
            f"expected {FROZEN_PROTOCOL_SHA256}, got {protocol_sha256}"
        )
    if assignment_plan_sha256 != FROZEN_ASSIGNMENT_PLAN_SHA256:
        raise ValueError(
            "frozen human-evaluation assignment plan fingerprint mismatch: "
            f"expected {FROZEN_ASSIGNMENT_PLAN_SHA256}, got {assignment_plan_sha256}"
        )
    if annotator_guide_sha256 != FROZEN_ANNOTATOR_GUIDE_SHA256:
        raise ValueError(
            "frozen human-evaluation annotator guide fingerprint mismatch: "
            f"expected {FROZEN_ANNOTATOR_GUIDE_SHA256}, got {annotator_guide_sha256}"
        )
    return protocol_sha256, assignment_plan_sha256, annotator_guide_sha256


def _unique_json_object(pairs):
    """Build a JSON object while rejecting ambiguous duplicate members."""
    value = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r} in annotator packet")
        value[key] = child
    return value


def _packet_blind_ids(packet_path: Path, *, content: bytes | None = None) -> list[str]:
    if content is None:
        if not packet_path.is_file():
            raise ValueError(f"blinded packet is missing: {packet_path}")
        content = packet_path.read_bytes()

    ids: list[str] = []
    packet_rows: list[dict] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(content.decode("utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw, object_pairs_hook=_unique_json_object)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed packet JSON on line {line_number}") from exc
        if not isinstance(row, dict) or set(row) != set(PACKET_FIELDS):
            raise ValueError(
                f"packet line {line_number} schema must be exactly {sorted(PACKET_FIELDS)}"
            )
        for field in PACKET_FIELDS:
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(
                    f"packet line {line_number} {field} must be non-empty text"
                )
        blind_id = row["blind_id"].strip()
        if blind_id in seen:
            raise ValueError(f"duplicate blind_id in packet: {blind_id}")
        seen.add(blind_id)
        ids.append(blind_id)
        packet_rows.append(row)

    if not ids:
        raise ValueError("blinded packet contains no evaluation items")
    packet_build.validate_annotator_facing_content(
        packet_rows, label="blinded packet"
    )
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


def _physical_line_number(handle: io.StringIO) -> int:
    """Return the last physical input line consumed by the CSV parser."""
    consumed = handle.getvalue()[: handle.tell()]
    normalized = consumed.replace("\r\n", "\n").replace("\r", "\n")
    return max(1, normalized.count("\n") + int(not normalized.endswith("\n")))


def _strict_csv_rows(reader: csv.DictReader, *, path: Path, handle: io.StringIO):
    """Yield rows while translating strict CSV syntax failures into input errors."""
    while True:
        try:
            yield next(reader)
        except StopIteration:
            return
        except csv.Error as exc:
            raise ValueError(
                f"{path.name}:{_physical_line_number(handle)}: "
                f"malformed ratings CSV: {exc}"
            ) from exc


def _reject_spreadsheet_active_text(
    value: str, *, field: str, path: Path, line_number: int
) -> None:
    """Keep text cells inert when a frozen CSV is opened in a spreadsheet."""
    if value.startswith(SPREADSHEET_FORMULA_PREFIXES):
        raise ValueError(
            f"{path.name}:{line_number}: {field} begins with a spreadsheet-active "
            "formula marker; rewrite it as plain text before freezing"
        )


def _annotator_identity_key(annotator_id: str) -> str:
    """Collapse canonically equivalent Unicode spellings for identity checks."""
    return unicodedata.normalize("NFC", annotator_id)


def _validate_annotator_id_characters(annotator_id: str) -> None:
    """Require visible, auditable text for an independent-rater identifier."""
    for character in annotator_id:
        if unicodedata.category(character) in {"Cc", "Cf"}:
            raise ValueError(
                "annotator_id contains a Unicode control or format character "
                f"(U+{ord(character):04X}); use a visible stable identifier"
            )


def _validate_annotator_identity_spellings(rows: list[dict]) -> None:
    """Reject multiple display spellings for one canonical annotator identity."""
    spellings: dict[str, str] = {}
    for row in rows:
        annotator_id = row["annotator_id"]
        _validate_annotator_id_characters(annotator_id)
        identity_key = _annotator_identity_key(annotator_id)
        previous = spellings.get(identity_key)
        if previous is not None and previous != annotator_id:
            raise ValueError(
                "canonically equivalent annotator_id values cannot represent "
                f"independent raters: {previous!r} and {annotator_id!r}"
            )
        spellings[identity_key] = annotator_id


def _load_ratings(
    rating_paths: list[Path],
    *,
    allowed_blind_ids: set[str],
    return_captured: bool = False,
    require_single_annotator: bool = False,
):
    """Parse ratings; raw ingestion enables the per-file annotator identity gate."""
    if not rating_paths:
        raise ValueError("at least one completed annotator ratings CSV is required")

    rows: list[dict] = []
    sources: list[dict] = []
    captured_inputs: list[bytes] = []
    seen: dict[tuple[str, str], str] = {}
    annotator_source_indices: dict[str, int] = {}

    for source_index, path in enumerate(rating_paths, start=1):
        source_annotators: set[str] = set()
        if not path.is_file():
            raise ValueError(f"ratings file is missing: {path}")
        # Parse and fingerprint the same captured bytes. Reopening a live CSV
        # after hashing can bind one revision's digest to another's scores.
        content = path.read_bytes()
        captured_inputs.append(content)
        sources.append(
            {
                "input_index": source_index,
                "name": path.name,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
        }
        )

        with io.StringIO(content.decode("utf-8"), newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            try:
                fieldnames = reader.fieldnames or []
            except csv.Error as exc:
                raise ValueError(
                    f"{path.name}:{_physical_line_number(handle)}: "
                    f"malformed ratings CSV: {exc}"
                ) from exc
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

            for raw in _strict_csv_rows(reader, path=path, handle=handle):
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
                submitted_annotator_id = str(raw.get("annotator_id") or "")
                _validate_annotator_id_characters(submitted_annotator_id)
                annotator_id = submitted_annotator_id.strip()
                blind_id = str(raw.get("blind_id") or "").strip()
                notes = str(raw.get("notes") or "").strip()

                if not annotator_id:
                    raise ValueError(f"{path.name}:{line_number} is missing annotator_id")
                _reject_spreadsheet_active_text(
                    annotator_id,
                    field="annotator_id",
                    path=path,
                    line_number=line_number,
                )
                _reject_spreadsheet_active_text(
                    notes,
                    field="notes",
                    path=path,
                    line_number=line_number,
                )
                source_annotators.add(annotator_id)
                if require_single_annotator and len(source_annotators) > 1:
                    raise ValueError(
                        f"{path.name}:{line_number}: each submitted ratings CSV must "
                        "contain exactly one annotator_id"
                    )
                if blind_id not in allowed_blind_ids:
                    raise ValueError(
                        f"{path.name}:{line_number} references unknown blind_id {blind_id!r}"
                    )

                key = (_annotator_identity_key(annotator_id), blind_id)
                if key in seen:
                    previous_annotator_id = seen[key]
                    if previous_annotator_id != annotator_id:
                        raise ValueError(
                            "canonically equivalent annotator_id values cannot supply "
                            "independent ratings: "
                            f"{previous_annotator_id!r} and {annotator_id!r} for {blind_id}"
                        )
                    raise ValueError(
                        f"duplicate independent rating for annotator/blind item: "
                        f"{annotator_id}/{blind_id}"
                    )
                seen[key] = annotator_id

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

        if not source_annotators:
            raise ValueError(f"{path.name}: ratings CSV contains no annotation rows")
        if require_single_annotator:
            annotator_id = next(iter(source_annotators))
            identity_key = _annotator_identity_key(annotator_id)
            previous_source = annotator_source_indices.get(identity_key)
            if previous_source is not None:
                raise ValueError(
                    f"annotator_id {annotator_id!r} appears in multiple submitted ratings CSV "
                    f"files (inputs {previous_source} and {source_index}); "
                    "one complete submission per annotator is required"
                )
            annotator_source_indices[identity_key] = source_index

    if not rows:
        raise ValueError("ratings files contain no annotation rows")

    rows.sort(key=lambda row: (row["annotator_id"], row["blind_id"]))
    if return_captured:
        return rows, sources, captured_inputs
    return rows, sources


def _validate_assignment_coverage(rows: list[dict], blind_ids: list[str]) -> dict:
    """Require two distinct independent raters for every blinded report."""
    _validate_annotator_identity_spellings(rows)
    raters_by_item = {blind_id: set() for blind_id in blind_ids}
    for row in rows:
        raters_by_item[row["blind_id"]].add(
            _annotator_identity_key(row["annotator_id"])
        )

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


def _validate_submission_coverage(rows: list[dict], blind_ids: list[str]) -> None:
    """Require every independent annotator submission to cover the full packet."""
    expected = set(blind_ids)
    by_annotator: dict[str, set[str]] = {}
    for row in rows:
        by_annotator.setdefault(row["annotator_id"], set()).add(row["blind_id"])

    incomplete = []
    for annotator_id, observed in sorted(by_annotator.items()):
        missing = sorted(expected - observed)
        if missing:
            preview = ", ".join(missing[:10])
            suffix = "" if len(missing) <= 10 else ", ..."
            incomplete.append(f"{annotator_id!r} missing {preview}{suffix}")
    if incomplete:
        raise ValueError(
            "each submitted ratings CSV must cover every blinded report exactly "
            f"once; incomplete annotators: {'; '.join(incomplete)}"
        )


def preflight_annotator_submission(
    rating_path: Path,
    *,
    annotator_bundle_root: Path,
) -> dict:
    """Validate one complete human submission without opening coordinator data."""
    from scripts import export_human_eval_annotator_bundle as exporter

    rating_path = Path(rating_path)
    annotator_bundle_root = Path(annotator_bundle_root)
    with tempfile.TemporaryDirectory(prefix="vera-annotator-preflight-") as tmp_name:
        snapshot_root = Path(tmp_name) / "bundle"
        snapshot_root.mkdir()
        captured = exporter._snapshot_annotator_bundle(
            annotator_bundle_root,
            snapshot_root,
        )
        bundle_receipt = exporter.verify_annotator_bundle(snapshot_root)
        packet_rows = exporter._read_jsonl_packet(captured["packet.jsonl"])
        blind_ids = [row["blind_id"].strip() for row in packet_rows]
        rows, sources = _load_ratings(
            [rating_path],
            allowed_blind_ids=set(blind_ids),
            require_single_annotator=True,
        )
        _validate_submission_coverage(rows, blind_ids)

    source = sources[0]
    return {
        "schema_version": 1,
        "study_id": bundle_receipt["study_id"],
        "status": "human_eval_annotator_submission_verified",
        "annotator_id": rows[0]["annotator_id"],
        "n_reports": len(rows),
        "n_missing_dimension_values": sum(
            not str(row[field]).strip()
            for row in rows
            for field in SCORE_FIELDS
        ),
        "submission": {
            "name": source["name"],
            "bytes": source["bytes"],
            "sha256": source["sha256"],
        },
        "annotator_manifest_sha256": hashlib.sha256(
            captured["annotator_manifest.json"]
        ).hexdigest(),
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
    _validate_annotator_identity_spellings(rows)
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


def _open_bound_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        directory_fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(
            f"human-evaluation staging root must be a regular directory: {path}"
        ) from exc
    if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
        os.close(directory_fd)
        raise ValueError(
            f"human-evaluation staging root must be a regular directory: {path}"
        )
    return directory_fd


def _require_directory_binding(path: Path, directory_fd: int) -> None:
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(
            f"human-evaluation staging root changed during publication: {path}"
        ) from exc
    opened = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise ValueError(
            f"human-evaluation staging root changed during publication: {path}"
        )


def _publish_directory_noreplace(staging_root: Path, output_root: Path) -> None:
    """Atomically install a verified freeze without replacing any path."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise ValueError(
            "atomic no-replace freeze publication is unavailable on this platform"
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    at_fdcwd = -100
    rename_noreplace = 1
    if (
        renameat2(
            at_fdcwd,
            os.fsencode(staging_root),
            at_fdcwd,
            os.fsencode(output_root),
            rename_noreplace,
        )
        == 0
    ):
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ValueError(
            f"refusing to overwrite human-evaluation output: {output_root}"
        )
    raise OSError(
        error_number,
        f"could not atomically publish human-evaluation freeze: {output_root}",
    )


def freeze_ratings(
    rating_paths: list[Path],
    *,
    packet_path: Path = DEFAULT_PACKET,
    protocol_path: Path = DEFAULT_PROTOCOL,
    assignment_plan_path: Path = DEFAULT_ASSIGNMENT_PLAN,
    annotator_guide_path: Path = DEFAULT_ANNOTATOR_GUIDE,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict:
    """Validate ratings and persist a blinded, fingerprinted, immutable snapshot."""
    packet_path = Path(packet_path)
    protocol_path = Path(protocol_path)
    assignment_plan_path = Path(assignment_plan_path)
    annotator_guide_path = Path(annotator_guide_path)
    output_root = Path(output_root)
    producer_content = Path(__file__).resolve().read_bytes()
    content_validator_content = Path(packet_build.__file__).resolve().read_bytes()
    content_validator_runtime = packet_build.content_validator_runtime_contract()

    if not protocol_path.is_file():
        raise ValueError(f"frozen human-evaluation protocol is missing: {protocol_path}")
    if not assignment_plan_path.is_file():
        raise ValueError(f"frozen human-evaluation assignment plan is missing: {assignment_plan_path}")
    if not annotator_guide_path.is_file():
        raise ValueError(f"frozen human-evaluation annotator guide is missing: {annotator_guide_path}")

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
    protocol_content = protocol_path.read_bytes()
    assignment_content = assignment_plan_path.read_bytes()
    annotator_guide_content = annotator_guide_path.read_bytes()
    (
        protocol_sha256,
        assignment_plan_sha256,
        annotator_guide_sha256,
    ) = _verify_frozen_governing_documents(
        protocol_content,
        assignment_content,
        annotator_guide_content,
    )
    blind_ids = _packet_blind_ids(packet_path, content=packet_content)
    rows, sources, captured_inputs = _load_ratings(
        [Path(path) for path in rating_paths],
        allowed_blind_ids=set(blind_ids),
        return_captured=True,
        require_single_annotator=True,
    )
    assignment_coverage = _validate_assignment_coverage(rows, blind_ids)
    _validate_submission_coverage(rows, blind_ids)
    agreement = build_agreement(rows)

    dimension_counts = {}
    for field in SCORE_FIELDS:
        rated = sum(_score(row, field) is not None for row in rows)
        dimension_counts[field] = {
            "rated": rated,
            "missing": len(rows) - rated,
        }

    # Build the entire freeze off-path. The final path remains absent until a
    # fully written candidate has passed independent retained-input verification.
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.staging-",
            dir=output_root.parent,
        )
    )
    output_fd = _open_bound_directory(staging_root)
    try:
        frozen_path = staging_root / "frozen_ratings.csv"
        agreement_path = staging_root / "agreement.json"
        manifest_path = staging_root / "freeze_manifest.json"

        _write_csv(frozen_path, rows)
        agreement_path.write_text(
            json.dumps(agreement, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        raw_root = staging_root / "raw_rating_inputs"
        raw_root.mkdir(exist_ok=False)
        for index, (source, content) in enumerate(
            zip(sources, captured_inputs), start=1
        ):
            archive_name = f"{index:04d}.csv"
            archive_path = raw_root / archive_name
            with archive_path.open("xb") as handle:
                handle.write(content)
            source["archive_path"] = f"raw_rating_inputs/{archive_name}"

        provenance_root = staging_root / "provenance"
        provenance_root.mkdir(exist_ok=False)
        producer_rel = "provenance/freeze_human_eval_ratings.py"
        producer_archive = staging_root / producer_rel
        with producer_archive.open("xb") as handle:
            handle.write(producer_content)
        content_validator_rel = "provenance/build_human_eval_packet.py"
        content_validator_archive = staging_root / content_validator_rel
        with content_validator_archive.open("xb") as handle:
            handle.write(content_validator_content)

        # Retain the same governing bytes captured before ratings processing.
        # Do not reopen working files here: they may have changed or disappeared.
        (staging_root / "governing_inputs").mkdir(exist_ok=False)
        for role, content in {
            "packet": packet_content,
            "protocol": protocol_content,
            "assignment_plan": assignment_content,
            "annotator_guide": annotator_guide_content,
        }.items():
            with (staging_root / GOVERNING_INPUT_PATHS[role]).open("xb") as handle:
                handle.write(content)

        manifest = {
            "schema_version": 1,
            "study_id": "budget-main-v1",
            "status": "blinded_human_ratings_frozen",
            "blinding_key_used": False,
            "packet": {
                "archive_path": GOVERNING_INPUT_PATHS["packet"],
                "name": packet_path.name,
                "bytes": len(packet_content),
                "sha256": hashlib.sha256(packet_content).hexdigest(),
                "n_blind_ids": len(blind_ids),
            },
            "protocol": {
                "archive_path": GOVERNING_INPUT_PATHS["protocol"],
                "bytes": len(protocol_content),
                "path": "paper/HUMAN_EVAL_PROTOCOL.md",
                "sha256": protocol_sha256,
            },
            "assignment_plan": {
                "archive_path": GOVERNING_INPUT_PATHS["assignment_plan"],
                "bytes": len(assignment_content),
                "path": "paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md",
                "sha256": assignment_plan_sha256,
            },
            "annotator_guide": {
                "archive_path": GOVERNING_INPUT_PATHS["annotator_guide"],
                "bytes": len(annotator_guide_content),
                "path": "paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md",
                "sha256": annotator_guide_sha256,
            },
            "assignment_coverage": assignment_coverage,
            "producer": {
                "path": producer_rel,
                "bytes": len(producer_content),
                "sha256": hashlib.sha256(producer_content).hexdigest(),
            },
            "content_validator": {
                "path": content_validator_rel,
                "bytes": len(content_validator_content),
                "sha256": hashlib.sha256(content_validator_content).hexdigest(),
            },
            "content_validator_runtime": content_validator_runtime,
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
            "integrity_note": FREEZE_INTEGRITY_NOTE,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        _require_directory_binding(staging_root, output_fd)
        # Local import avoids a module-import cycle: the verifier intentionally
        # imports this producer to recompute normalized ratings and agreement.
        from scripts import verify_human_eval_freeze as verifier

        verifier.verify_frozen_snapshot(
            freeze_root=staging_root,
            use_retained_inputs=True,
        )
        _require_directory_binding(staging_root, output_fd)
        _publish_directory_noreplace(staging_root, output_root)
        _require_directory_binding(output_root, output_fd)
        return manifest
    finally:
        # Retain failed staging trees for forensics. Path-based cleanup could
        # delete a concurrent replacement after a binding check.
        os.close(output_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ratings", nargs="+", type=Path, help="completed blinded annotator CSV files")
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--assignment-plan", type=Path, default=DEFAULT_ASSIGNMENT_PLAN)
    parser.add_argument("--annotator-guide", type=Path, default=DEFAULT_ANNOTATOR_GUIDE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--preflight-bundle",
        type=Path,
        help=(
            "validate exactly one completed ratings CSV against this treatment-blind "
            "annotator distribution bundle without freezing or writing outputs"
        ),
    )
    args = parser.parse_args()

    if args.preflight_bundle is not None:
        if len(args.ratings) != 1:
            raise SystemExit(
                "HUMAN EVAL SUBMISSION PREFLIGHT: FAIL: exactly one completed "
                "annotator CSV is required"
            )
        try:
            receipt = preflight_annotator_submission(
                args.ratings[0],
                annotator_bundle_root=args.preflight_bundle,
            )
        except (OSError, ValueError) as exc:
            raise SystemExit(
                f"HUMAN EVAL SUBMISSION PREFLIGHT: FAIL: {exc}"
            ) from exc
        print(json.dumps(receipt, indent=2, sort_keys=True))
        print("HUMAN EVAL SUBMISSION PREFLIGHT: PASS (ratings remain blinded)")
        return 0

    try:
        manifest = freeze_ratings(
            args.ratings,
            packet_path=args.packet,
            protocol_path=args.protocol,
            assignment_plan_path=args.assignment_plan,
            annotator_guide_path=args.annotator_guide,
            output_root=args.output_root,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL FREEZE: FAIL: {exc}") from exc

    print(json.dumps(manifest, indent=2, sort_keys=True))
    print("HUMAN EVAL FREEZE: PASS (ratings remain blinded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
