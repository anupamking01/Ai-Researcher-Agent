"""Verify a blinded human-evaluation freeze before any unblinding.

The verifier never reads the coordinator-only blinding key. It checks that the
frozen outputs, archived raw rating inputs, coordinator attestations, blinded
packet, protocol, assignment plan, and annotator guide still match the freeze manifest, then independently
recomputes the normalized ratings, assignment coverage, and pre-unblinding
agreement.

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
DEFAULT_ANNOTATOR_GUIDE = freeze.DEFAULT_ANNOTATOR_GUIDE


def _require_regular_file(path: Path, *, label: str) -> bytes:
    """Capture one path-bound file through the freeze's descriptor contract."""
    return freeze._capture_regular_input(path, label=label)


def _load_json_bytes(content: bytes, *, label: str) -> dict:
    def unique_object(pairs):
        value = {}
        for key, child in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key {key!r} in {label}")
            value[key] = child
        return value

    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=unique_object)
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


def _require_object_schema(
    value,
    *,
    required: set[str] | frozenset[str],
    label: str,
    optional: set[str] | frozenset[str] = frozenset(),
) -> None:
    """Reject missing or undeclared manifest members at one object boundary."""
    if not isinstance(value, dict):
        raise ValueError(
            f"freeze manifest schema mismatch at {label}: expected an object"
        )
    actual = set(value)
    missing = sorted(set(required) - actual)
    undeclared = sorted(actual - set(required) - set(optional))
    if missing or undeclared:
        raise ValueError(
            f"freeze manifest schema mismatch at {label}: "
            f"missing={missing}, undeclared={undeclared}"
        )


def _require_field_types(
    value: dict,
    *,
    field_types: dict[str, type],
    label: str,
    optional_types: dict[str, type] | None = None,
) -> None:
    """Require producer-exact JSON scalar/container types, including int != bool."""
    type_names = {
        str: "string",
        int: "integer",
        bool: "boolean",
        dict: "object",
        list: "array",
    }
    for field, expected_type in {
        **field_types,
        **(optional_types or {}),
    }.items():
        if field not in value:
            continue
        if type(value[field]) is not expected_type:
            expected_name = type_names.get(expected_type, expected_type.__name__)
            raise ValueError(
                f"freeze manifest schema mismatch at {label}.{field}: "
                f"expected {expected_name}"
            )


def _require_json_shape(value, expected, *, label: str) -> None:
    """Require an exact recursively typed object shape without comparing values."""
    if isinstance(expected, dict):
        _require_object_schema(value, required=set(expected), label=label)
        for field, expected_child in expected.items():
            _require_json_shape(
                value[field],
                expected_child,
                label=f"{label}.{field}",
            )
        return
    _require_field_types(
        {"value": value},
        field_types={"value": type(expected)},
        label=label,
    )


def _require_safe_filename(value, *, label: str) -> None:
    """Require one portable, non-reserved filename with no control characters."""
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(
            f"freeze manifest schema mismatch at {label}: expected a safe filename"
        )


def _verify_manifest_schema(manifest: dict) -> None:
    """Require the exact schema emitted by the blinded-freeze producer."""
    if "content_validator_runtime" not in manifest:
        raise ValueError(
            "freeze manifest schema mismatch: content validator runtime "
            "contract is missing"
        )
    _require_object_schema(
        manifest,
        required={
            "schema_version",
            "study_id",
            "status",
            "blinding_key_used",
            "packet",
            "protocol",
            "assignment_plan",
            "annotator_guide",
            "annotator_attestations",
            "assignment_coverage",
            "producer",
            "content_validator",
            "content_validator_runtime",
            "rating_inputs",
            "frozen_ratings",
            "agreement",
            "integrity_note",
        },
        optional={"submission_preflights"},
        label="root",
    )
    _require_field_types(
        manifest,
        field_types={
            "schema_version": int,
            "study_id": str,
            "status": str,
            "blinding_key_used": bool,
            "packet": dict,
            "protocol": dict,
            "assignment_plan": dict,
            "annotator_guide": dict,
            "annotator_attestations": dict,
            "assignment_coverage": dict,
            "producer": dict,
            "content_validator": dict,
            "content_validator_runtime": dict,
            "rating_inputs": list,
            "frozen_ratings": dict,
            "agreement": dict,
            "integrity_note": str,
        },
        optional_types={"submission_preflights": list},
        label="root",
    )
    _require_object_schema(
        manifest["packet"],
        required={"name", "bytes", "sha256", "n_blind_ids"},
        optional={"archive_path"},
        label="packet",
    )
    _require_field_types(
        manifest["packet"],
        field_types={
            "name": str,
            "bytes": int,
            "sha256": str,
            "n_blind_ids": int,
        },
        optional_types={"archive_path": str},
        label="packet",
    )
    _require_safe_filename(manifest["packet"]["name"], label="packet.name")
    for role in ("protocol", "assignment_plan", "annotator_guide"):
        _require_object_schema(
            manifest[role],
            required={"bytes", "path", "sha256"},
            optional={"archive_path"},
            label=role,
        )
        _require_field_types(
            manifest[role],
            field_types={"bytes": int, "path": str, "sha256": str},
            optional_types={"archive_path": str},
            label=role,
        )
    _require_object_schema(
        manifest["annotator_attestations"],
        required={"archive_path", "bytes", "sha256", "n_annotators"},
        label="annotator_attestations",
    )
    _require_field_types(
        manifest["annotator_attestations"],
        field_types={
            "archive_path": str,
            "bytes": int,
            "sha256": str,
            "n_annotators": int,
        },
        label="annotator_attestations",
    )
    _require_object_schema(
        manifest["assignment_coverage"],
        required={
            "required_min_raters_per_item",
            "n_items",
            "min_observed_raters_per_item",
            "max_observed_raters_per_item",
            "items_by_rater_count",
        },
        label="assignment_coverage",
    )
    _require_field_types(
        manifest["assignment_coverage"],
        field_types={
            "required_min_raters_per_item": int,
            "n_items": int,
            "min_observed_raters_per_item": int,
            "max_observed_raters_per_item": int,
            "items_by_rater_count": dict,
        },
        label="assignment_coverage",
    )
    rater_histogram = manifest["assignment_coverage"]["items_by_rater_count"]
    for count, n_items in rater_histogram.items():
        if not isinstance(count, str) or type(n_items) is not int:
            raise ValueError(
                "freeze manifest schema mismatch at "
                "assignment_coverage.items_by_rater_count: "
                "expected string keys and integer counts"
            )
    for role in ("producer", "content_validator"):
        _require_object_schema(
            manifest[role],
            required={"path", "bytes", "sha256"},
            label=role,
        )
        _require_field_types(
            manifest[role],
            field_types={"path": str, "bytes": int, "sha256": str},
            label=role,
        )
    _require_json_shape(
        manifest["content_validator_runtime"],
        freeze.packet_build.content_validator_runtime_contract(),
        label="content_validator_runtime",
    )

    rating_entries = manifest["rating_inputs"]
    if not isinstance(rating_entries, list) or not rating_entries:
        raise ValueError(
            "freeze manifest schema mismatch at rating_inputs: "
            "expected a non-empty list"
        )
    for index, entry in enumerate(rating_entries, start=1):
        _require_object_schema(
            entry,
            required={"input_index", "bytes", "sha256"},
            optional={"archive_path"},
            label=f"rating_inputs[{index}]",
        )
        _require_field_types(
            entry,
            field_types={"input_index": int, "bytes": int, "sha256": str},
            optional_types={"archive_path": str},
            label=f"rating_inputs[{index}]",
        )

    if "submission_preflights" in manifest:
        preflight_entries = manifest["submission_preflights"]
        if len(preflight_entries) != len(rating_entries):
            raise ValueError(
                "freeze manifest schema mismatch at submission_preflights: "
                "expected one entry per rating input"
            )
        for index, entry in enumerate(preflight_entries, start=1):
            _require_object_schema(
                entry,
                required={
                    "input_index",
                    "archive_path",
                    "annotator_id",
                    "presentation_order",
                    "receipt_bytes",
                    "receipt_sha256",
                },
                label=f"submission_preflights[{index}]",
            )
            _require_field_types(
                entry,
                field_types={
                    "input_index": int,
                    "archive_path": str,
                    "annotator_id": str,
                    "presentation_order": str,
                    "receipt_bytes": int,
                    "receipt_sha256": str,
                },
                label=f"submission_preflights[{index}]",
            )
    frozen_entry = manifest["frozen_ratings"]
    _require_object_schema(
        frozen_entry,
        required={
            "path",
            "bytes",
            "sha256",
            "n_rows",
            "n_annotators",
            "n_unique_blind_ids_rated",
            "dimension_counts",
        },
        label="frozen_ratings",
    )
    _require_field_types(
        frozen_entry,
        field_types={
            "path": str,
            "bytes": int,
            "sha256": str,
            "n_rows": int,
            "n_annotators": int,
            "n_unique_blind_ids_rated": int,
            "dimension_counts": dict,
        },
        label="frozen_ratings",
    )
    dimension_counts = frozen_entry["dimension_counts"]
    _require_object_schema(
        dimension_counts,
        required=set(freeze.SCORE_FIELDS),
        label="frozen_ratings.dimension_counts",
    )
    for field in freeze.SCORE_FIELDS:
        _require_object_schema(
            dimension_counts[field],
            required={"rated", "missing"},
            label=f"frozen_ratings.dimension_counts.{field}",
        )
        _require_field_types(
            dimension_counts[field],
            field_types={"rated": int, "missing": int},
            label=f"frozen_ratings.dimension_counts.{field}",
        )
    _require_object_schema(
        manifest["agreement"],
        required={"path", "bytes", "sha256"},
        label="agreement",
    )
    _require_field_types(
        manifest["agreement"],
        field_types={"path": str, "bytes": int, "sha256": str},
        label="agreement",
    )


def _verify_bundle_layout(freeze_root: Path, manifest: dict) -> None:
    """Reject every freeze artifact not declared by the fixed bundle contract."""
    rating_entries = manifest.get("rating_inputs")
    if (
        not isinstance(rating_entries, list)
        or not rating_entries
        or any(not isinstance(entry, dict) for entry in rating_entries)
    ):
        raise ValueError("freeze manifest rating_inputs must be a non-empty list of objects")
    rating_archive_flags = ["archive_path" in entry for entry in rating_entries]
    if any(rating_archive_flags) and not all(rating_archive_flags):
        raise ValueError("freeze manifest raw rating archive paths are incomplete")

    governing_entries = [manifest.get(role) for role in freeze.GOVERNING_INPUT_PATHS]
    if any(not isinstance(entry, dict) for entry in governing_entries):
        raise ValueError("governing input manifest entries must be objects")
    governing_archive_flags = ["archive_path" in entry for entry in governing_entries]
    if any(governing_archive_flags) and not all(governing_archive_flags):
        raise ValueError("retained governing input archive paths are incomplete")

    expected_names = {*freeze.OUTPUT_FILES, "provenance"}
    if all(rating_archive_flags):
        expected_names.add("raw_rating_inputs")
    if all(governing_archive_flags) or "annotator_attestations" in manifest:
        expected_names.add("governing_inputs")
    if "submission_preflights" in manifest:
        expected_names.add(freeze.SUBMISSION_PREFLIGHT_ARCHIVE_ROOT)
    extra_names = {child.name for child in freeze_root.iterdir()} - expected_names
    if extra_names:
        raise ValueError(
            f"freeze root contents mismatch: undeclared artifacts {sorted(extra_names)!r}"
        )

    provenance_root = freeze_root / "provenance"
    if provenance_root.is_symlink() or not provenance_root.is_dir():
        raise ValueError(f"provenance archive must be a regular directory: {provenance_root}")
    extra_names = {
        child.name for child in provenance_root.iterdir()
    } - {"freeze_human_eval_ratings.py", "build_human_eval_packet.py"}
    if extra_names:
        raise ValueError(
            "provenance archive contents mismatch: "
            f"undeclared artifacts {sorted(extra_names)!r}"
        )


def _verify_governing_archive(freeze_root: Path, manifest: dict, *, required: bool):
    """Verify fixed, in-bundle governing inputs; never follow manifest paths."""
    entries = {role: manifest.get(role) for role in freeze.GOVERNING_INPUT_PATHS}
    if any(not isinstance(entry, dict) for entry in entries.values()):
        raise ValueError("governing input manifest entries must be objects")
    flags = ["archive_path" in entry for entry in entries.values()]
    archive_root = freeze_root / "governing_inputs"
    if not any(flags):
        if required:
            raise ValueError("retained governing inputs are required for --retained-inputs")
        if archive_root.exists() or archive_root.is_symlink():
            if archive_root.is_symlink() or not archive_root.is_dir():
                raise ValueError("undeclared governing input archive")
            if {child.name for child in archive_root.iterdir()} != {
                Path(freeze.ATTESTATION_ARCHIVE_PATH).name
            }:
                raise ValueError("undeclared governing input archive")
        return None  # Legacy freezes still require external governing files.
    if not all(flags):
        raise ValueError("retained governing input archive paths are incomplete")
    if archive_root.is_symlink() or not archive_root.is_dir():
        raise ValueError(f"governing input archive must be a regular directory: {archive_root}")

    expected_names = {
        *(Path(path).name for path in freeze.GOVERNING_INPUT_PATHS.values()),
        Path(freeze.ATTESTATION_ARCHIVE_PATH).name,
    }
    _require_equal(
        {child.name for child in archive_root.iterdir()}, expected_names,
        label="governing input archive contents",
    )
    captured = {}
    for role, relative in freeze.GOVERNING_INPUT_PATHS.items():
        entry = entries[role]
        _require_equal(entry.get("archive_path"), relative,
                       label=f"retained {role} archive path")
        content = _require_regular_file(freeze_root / relative, label=f"retained {role}")
        _require_equal(
            {"bytes": entry.get("bytes"), "sha256": entry.get("sha256")},
            _fingerprint(content), label=f"retained {role} fingerprint",
        )
        captured[role] = content
    return captured


def _verify_attestation_archive(freeze_root: Path, manifest: dict) -> bytes:
    entry = manifest["annotator_attestations"]
    _require_equal(
        entry["archive_path"],
        freeze.ATTESTATION_ARCHIVE_PATH,
        label="retained annotator attestation archive path",
    )
    content = _require_regular_file(
        freeze_root / freeze.ATTESTATION_ARCHIVE_PATH,
        label="retained annotator attestations",
    )
    _require_equal(
        {"bytes": entry["bytes"], "sha256": entry["sha256"]},
        _fingerprint(content),
        label="retained annotator attestation fingerprint",
    )
    return content


def verify_frozen_snapshot(
    rating_paths: list[Path] | None = None,
    *,
    freeze_root: Path = DEFAULT_FREEZE_ROOT,
    packet_path: Path = DEFAULT_PACKET,
    protocol_path: Path = DEFAULT_PROTOCOL,
    assignment_plan_path: Path = DEFAULT_ASSIGNMENT_PLAN,
    annotator_guide_path: Path = DEFAULT_ANNOTATOR_GUIDE,
    use_retained_inputs: bool = False,
) -> dict:
    """Verify a frozen blinded snapshot and its retained pre-unblinding inputs."""
    freeze_root = Path(freeze_root)
    packet_path = Path(packet_path)
    protocol_path = Path(protocol_path)
    assignment_plan_path = Path(assignment_plan_path)
    annotator_guide_path = Path(annotator_guide_path)
    rating_paths = [Path(path) for path in (rating_paths or [])]
    if use_retained_inputs and (
        packet_path != DEFAULT_PACKET
        or protocol_path != DEFAULT_PROTOCOL
        or assignment_plan_path != DEFAULT_ASSIGNMENT_PLAN
        or annotator_guide_path != DEFAULT_ANNOTATOR_GUIDE
    ):
        raise ValueError("cannot combine retained-input mode with external governing inputs")

    if freeze_root.is_symlink() or not freeze_root.is_dir():
        raise ValueError(f"freeze root must be a regular directory: {freeze_root}")

    manifest_path = freeze_root / "freeze_manifest.json"
    manifest_content = _require_regular_file(manifest_path, label="freeze manifest")
    manifest = _load_json_bytes(manifest_content, label="freeze manifest")
    _verify_manifest_schema(manifest)

    _require_equal(manifest.get("schema_version"), 1, label="freeze manifest schema_version")
    _require_equal(manifest.get("study_id"), "budget-main-v1", label="freeze manifest study_id")
    _require_equal(
        manifest.get("status"),
        "blinded_human_ratings_frozen",
        label="freeze manifest status",
    )
    _require_equal(manifest.get("blinding_key_used"), False, label="blinding_key_used")
    _require_equal(
        manifest.get("integrity_note"),
        freeze.FREEZE_INTEGRITY_NOTE,
        label="freeze manifest integrity note",
    )

    retained = _verify_governing_archive(freeze_root, manifest, required=use_retained_inputs)
    attestation_content = _verify_attestation_archive(freeze_root, manifest)
    if use_retained_inputs:
        # The name is descriptive only: file reads use fixed archive paths above.
        name = manifest["packet"].get("name")
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise ValueError("retained packet name must be a nonempty filename")
        packet_path = Path(name)
        packet_content = retained["packet"]
        protocol_content = retained["protocol"]
        assignment_content = retained["assignment_plan"]
        annotator_guide_content = retained["annotator_guide"]
    else:
        # Preserve the existing external-file cross-check. A valid archive must
        # never silently hide drift in working files explicitly being checked.
        packet_content = _require_regular_file(packet_path, label="blinded packet")
        protocol_content = _require_regular_file(protocol_path, label="human-evaluation protocol")
        assignment_content = _require_regular_file(
            assignment_plan_path,
            label="human-evaluation assignment plan",
        )
        annotator_guide_content = _require_regular_file(
            annotator_guide_path,
            label="human-evaluation annotator guide",
        )
    freeze._verify_frozen_governing_documents(
        protocol_content,
        assignment_content,
        annotator_guide_content,
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
        {
            "bytes": protocol_entry.get("bytes"),
            "sha256": protocol_entry.get("sha256"),
        },
        _fingerprint(protocol_content),
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
        {
            "bytes": assignment_entry.get("bytes"),
            "sha256": assignment_entry.get("sha256"),
        },
        _fingerprint(assignment_content),
        label="assignment-plan fingerprint",
    )

    annotator_guide_entry = manifest.get("annotator_guide")
    if not isinstance(annotator_guide_entry, dict):
        raise ValueError("freeze manifest annotator_guide entry must be an object")
    _require_equal(
        annotator_guide_entry.get("path"),
        "paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md",
        label="annotator-guide manifest path",
    )
    _require_equal(
        {
            "bytes": annotator_guide_entry.get("bytes"),
            "sha256": annotator_guide_entry.get("sha256"),
        },
        _fingerprint(annotator_guide_content),
        label="annotator-guide fingerprint",
    )

    producer_entry = manifest.get("producer")
    if not isinstance(producer_entry, dict):
        raise ValueError("freeze manifest producer entry must be an object")
    _require_equal(
        producer_entry.get("path"),
        "provenance/freeze_human_eval_ratings.py",
        label="freeze producer manifest path",
    )
    producer_path = freeze_root / "provenance" / "freeze_human_eval_ratings.py"
    producer_content = _require_regular_file(producer_path, label="archived freeze producer")
    _require_equal(
        {"bytes": producer_entry.get("bytes"), "sha256": producer_entry.get("sha256")},
        _fingerprint(producer_content),
        label="archived freeze producer fingerprint",
    )

    validator_entry = manifest.get("content_validator")
    if not isinstance(validator_entry, dict):
        raise ValueError("freeze manifest content_validator entry must be an object")
    _require_equal(
        validator_entry.get("path"),
        "provenance/build_human_eval_packet.py",
        label="content validator manifest path",
    )
    validator_path = freeze_root / "provenance" / "build_human_eval_packet.py"
    validator_content = _require_regular_file(
        validator_path, label="archived content validator"
    )
    _require_equal(
        {
            "bytes": validator_entry.get("bytes"),
            "sha256": validator_entry.get("sha256"),
        },
        _fingerprint(validator_content),
        label="archived content validator fingerprint",
    )
    runtime_entry = manifest.get("content_validator_runtime")
    _require_equal(
        runtime_entry,
        freeze.packet_build.content_validator_runtime_contract(),
        label="content validator runtime contract",
    )

    rating_entries = manifest.get("rating_inputs")
    if (
        not isinstance(rating_entries, list)
        or not rating_entries
        or any(not isinstance(entry, dict) for entry in rating_entries)
    ):
        raise ValueError("freeze manifest rating_inputs must be a non-empty list of objects")

    for index, entry in enumerate(rating_entries, start=1):
        _require_equal(
            entry.get("input_index"),
            index,
            label=f"rating input {index} index",
        )
    archive_flags = ["archive_path" in entry for entry in rating_entries]
    if any(archive_flags) and not all(archive_flags):
        raise ValueError("freeze manifest raw rating archive paths are incomplete")

    if all(archive_flags):
        archive_root = freeze_root / "raw_rating_inputs"
        if archive_root.is_symlink() or not archive_root.is_dir():
            raise ValueError(f"raw rating archive must be a regular directory: {archive_root}")

        archive_paths = []
        expected_names = []
        for index, entry in enumerate(rating_entries, start=1):
            expected_name = f"{index:04d}.csv"
            expected_rel = f"raw_rating_inputs/{expected_name}"
            _require_equal(
                entry.get("archive_path"),
                expected_rel,
                label=f"raw rating archive path {index}",
            )
            expected_names.append(expected_name)
            archive_paths.append(freeze_root / expected_rel)

        actual_names = []
        for child in archive_root.iterdir():
            if child.is_symlink() or not child.is_file():
                raise ValueError(f"raw rating archive contains a non-regular file: {child}")
            actual_names.append(child.name)
        _require_equal(
            sorted(actual_names),
            sorted(expected_names),
            label="raw rating archive contents",
        )

        raw_rows, archived_sources, archived_contents = freeze._load_ratings(
            archive_paths,
            allowed_blind_ids=set(blind_ids),
            return_captured=True,
            require_single_annotator=True,
        )
        for index, (entry, source) in enumerate(
            zip(rating_entries, archived_sources),
            start=1,
        ):
            _require_equal(
                {"bytes": source.get("bytes"), "sha256": source.get("sha256")},
                {"bytes": entry.get("bytes"), "sha256": entry.get("sha256")},
                label=f"archived raw rating input {index} fingerprint",
            )

        if rating_paths:
            external_rows, external_sources = freeze._load_ratings(
                rating_paths,
                allowed_blind_ids=set(blind_ids),
                require_single_annotator=True,
            )
            expected_external = [
                {
                    "input_index": index,
                    "bytes": entry.get("bytes"),
                    "sha256": entry.get("sha256"),
                }
                for index, entry in enumerate(rating_entries, start=1)
            ]
            external_sources = [
                {
                    key: source[key]
                    for key in ("input_index", "bytes", "sha256")
                }
                for source in external_sources
            ]
            _require_equal(
                external_sources,
                expected_external,
                label="raw rating inputs",
            )
            _require_equal(
                external_rows,
                raw_rows,
                label="external raw ratings versus in-bundle archive",
            )
    else:
        if not rating_paths:
            raise ValueError(
                "archived raw rating CSVs are required for legacy freeze verification"
            )
        raw_rows, raw_sources, archived_contents = freeze._load_ratings(
            rating_paths,
            allowed_blind_ids=set(blind_ids),
            return_captured=True,
            require_single_annotator=True,
        )
        raw_sources = [
            {
                key: source[key]
                for key in ("input_index", "bytes", "sha256")
            }
            for source in raw_sources
        ]
        _require_equal(rating_entries, raw_sources, label="raw rating inputs")

    if "submission_preflights" in manifest:
        preflight_root = freeze_root / freeze.SUBMISSION_PREFLIGHT_ARCHIVE_ROOT
        if preflight_root.is_symlink() or not preflight_root.is_dir():
            raise ValueError(
                f"submission preflight archive must be a regular directory: {preflight_root}"
            )
        expected_names = [f"{index:04d}" for index in range(1, len(rating_entries) + 1)]
        _require_equal(
            sorted(child.name for child in preflight_root.iterdir()),
            expected_names,
            label="submission preflight archive contents",
        )
        evidence = []
        for index, expected_name in enumerate(expected_names, start=1):
            evidence_root = preflight_root / expected_name
            if evidence_root.is_symlink() or not evidence_root.is_dir():
                raise ValueError(
                    f"submission preflight evidence must be a regular directory: {evidence_root}"
                )
            if {child.name for child in evidence_root.iterdir()} != {"receipt", "bundle"}:
                raise ValueError(
                    f"submission preflight evidence {index} artifact set mismatch"
                )
            evidence.append((evidence_root / "receipt", evidence_root / "bundle"))
        recomputed_preflights, _ = freeze._validate_and_capture_submission_preflights(
            rating_sources=archived_sources if all(archive_flags) else raw_sources,
            rating_contents=archived_contents,
            packet_content=packet_content,
            submission_preflights=evidence,
            neutralize_receipt_names=False,
        )
        _require_equal(
            manifest["submission_preflights"],
            recomputed_preflights,
            label="submission preflight evidence",
        )

    attestation_rows, attestation_source, _ = freeze._load_annotator_attestations(
        freeze_root / freeze.ATTESTATION_ARCHIVE_PATH,
        content=attestation_content,
    )
    _require_equal(
        {
            "bytes": manifest["annotator_attestations"]["bytes"],
            "sha256": manifest["annotator_attestations"]["sha256"],
            "n_annotators": manifest["annotator_attestations"]["n_annotators"],
        },
        {
            "bytes": attestation_source["bytes"],
            "sha256": attestation_source["sha256"],
            "n_annotators": attestation_source["n_annotators"],
        },
        label="annotator attestation summary",
    )
    freeze._validate_annotator_attestation_coverage(attestation_rows, raw_rows)

    _verify_bundle_layout(freeze_root, manifest)

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

    # Only this normalized artifact combines raters. Raw archived/external
    # submissions above still enforce one annotator per file, regardless of name.
    frozen_rows, frozen_sources = freeze._load_ratings(
        [frozen_path],
        allowed_blind_ids=set(blind_ids),
        require_single_annotator=False,
    )
    # The loader fingerprints the exact bytes it parses. Never attest one
    # file revision while validating normalized rows from a later revision.
    _require_equal(
        {"bytes": frozen_sources[0]["bytes"], "sha256": frozen_sources[0]["sha256"]},
        _fingerprint(frozen_content),
        label="frozen-ratings parsed fingerprint",
    )
    _require_equal(frozen_rows, raw_rows, label="frozen ratings versus normalized raw inputs")

    coverage = freeze._validate_assignment_coverage(frozen_rows, blind_ids)
    freeze._validate_submission_coverage(frozen_rows, blind_ids)
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
        "n_raw_rating_inputs": len(rating_entries),
        "n_rows": len(frozen_rows),
        "n_annotators": len({row["annotator_id"] for row in frozen_rows}),
        "n_blind_ids": len(blind_ids),
        "requires_predeclared_multi_rater_statistic": recomputed_agreement[
            "requires_predeclared_multi_rater_statistic"
        ],
        "annotator_attestations_verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ratings",
        nargs="*",
        type=Path,
        help=(
            "optional external copies of the completed annotator CSV files, in original "
            "order; new freezes verify from their in-bundle raw archive"
        ),
    )
    parser.add_argument("--freeze-root", type=Path, default=DEFAULT_FREEZE_ROOT)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--assignment-plan", type=Path)
    parser.add_argument("--annotator-guide", type=Path)
    parser.add_argument(
        "--retained-inputs", action="store_true",
        help="verify using retained packet/protocol/assignment/guide inputs only",
    )
    args = parser.parse_args()
    if args.retained_inputs and any(
        (args.packet, args.protocol, args.assignment_plan, args.annotator_guide)
    ):
        parser.error(
            "cannot combine --retained-inputs with external governing inputs"
        )

    try:
        receipt = verify_frozen_snapshot(
            args.ratings,
            freeze_root=args.freeze_root,
            packet_path=args.packet or DEFAULT_PACKET,
            protocol_path=args.protocol or DEFAULT_PROTOCOL,
            assignment_plan_path=args.assignment_plan or DEFAULT_ASSIGNMENT_PLAN,
            annotator_guide_path=args.annotator_guide or DEFAULT_ANNOTATOR_GUIDE,
            use_retained_inputs=args.retained_inputs,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL VERIFY: FAIL: {exc}") from exc

    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("HUMAN EVAL VERIFY: PASS (ratings remain blinded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
