"""Synthetic-only tests for the pre-unblinding annotator attestation gate."""

import csv
import hashlib
import json

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as verify


def _write_attestations(tmp_path, rows, *, fields=None):
    path = tmp_path / "annotator_attestations.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields or freeze.ANNOTATOR_ATTESTATION_FIELDS),
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(annotator_id, **changes):
    row = {
        "annotator_id": annotator_id,
        "eligibility_decided_before_report_access": "true",
        "treatment_identity_unseen_during_scoring": "true",
        "scored_independently": "true",
        "human_only_scoring": "true",
        "generated_or_selected_treatment_reports": "false",
        "material_conflicts_resolved_before_assignment": "true",
    }
    row.update(changes)
    return row


def _rating_rows(*annotator_ids):
    return [
        {"annotator_id": annotator_id, "blind_id": "H001"}
        for annotator_id in annotator_ids
    ]


def _freeze_inputs(tmp_path):
    packet = tmp_path / "packet.jsonl"
    packet.write_text(
        json.dumps(
            {
                "blind_id": "H001",
                "task_id": "main-01",
                "question": "Synthetic question",
                "report_markdown": "Synthetic report",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ratings = []
    for annotator_id in ("synthetic-a", "synthetic-b"):
        path = tmp_path / f"{annotator_id}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(freeze.RATING_FIELDS))
            writer.writeheader()
            writer.writerow(
                {
                    "annotator_id": annotator_id,
                    "blind_id": "H001",
                    **{field: "3" for field in freeze.SCORE_FIELDS},
                    "notes": "",
                }
            )
        ratings.append(path)
    return packet, ratings


def test_valid_attestations_bind_exact_pseudonymous_annotator_set(tmp_path):
    path = _write_attestations(
        tmp_path,
        [_row("synthetic-a"), _row("synthetic-b")],
    )

    rows, source, captured = freeze._load_annotator_attestations(path)
    freeze._validate_annotator_attestation_coverage(
        rows,
        _rating_rows("synthetic-a", "synthetic-b"),
    )

    assert [row["annotator_id"] for row in rows] == ["synthetic-a", "synthetic-b"]
    assert source == {
        "name": "annotator_attestations.csv",
        "bytes": len(captured),
        "sha256": freeze.hashlib.sha256(captured).hexdigest(),
        "n_annotators": 2,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("eligibility_decided_before_report_access", "false"),
        ("treatment_identity_unseen_during_scoring", "false"),
        ("scored_independently", "false"),
        ("human_only_scoring", "false"),
        ("generated_or_selected_treatment_reports", "true"),
        ("human_only_scoring", "TRUE"),
        ("human_only_scoring", " true"),
        ("material_conflicts_resolved_before_assignment", "false"),
    ],
)
def test_attestation_declarations_fail_closed(tmp_path, field, value):
    path = _write_attestations(tmp_path, [_row("synthetic-a", **{field: value})])

    with pytest.raises(ValueError, match=field):
        freeze._load_annotator_attestations(path)


def test_attestation_schema_rejects_personal_name_field(tmp_path):
    fields = [*freeze.ANNOTATOR_ATTESTATION_FIELDS, "personal_name"]
    row = {**_row("synthetic-a"), "personal_name": "Not retained"}
    path = _write_attestations(tmp_path, [row], fields=fields)

    with pytest.raises(ValueError, match="schema must exactly match"):
        freeze._load_annotator_attestations(path)


def test_attestation_schema_excludes_free_text_conflict_notes(tmp_path):
    fields = [*freeze.ANNOTATOR_ATTESTATION_FIELDS[:-1], "conflict_notes"]
    row = {
        **{key: value for key, value in _row("synthetic-a").items() if key in fields},
        "conflict_notes": "Jane Doe; H001 is D3; correctness=5",
    }
    path = _write_attestations(tmp_path, [row], fields=fields)

    with pytest.raises(ValueError, match="schema must exactly match"):
        freeze._load_annotator_attestations(path)


def test_canonically_equivalent_attestation_ids_are_duplicates(tmp_path):
    path = _write_attestations(
        tmp_path,
        [_row("synthetic-é"), _row("synthetic-e\u0301")],
    )

    with pytest.raises(ValueError, match="canonically equivalent|duplicate"):
        freeze._load_annotator_attestations(path)


def test_attested_ids_must_exactly_match_rating_submitters(tmp_path):
    path = _write_attestations(
        tmp_path,
        [_row("synthetic-a"), _row("synthetic-unsubmitted")],
    )
    rows, _, _ = freeze._load_annotator_attestations(path)

    with pytest.raises(ValueError, match="annotator ID set mismatch"):
        freeze._validate_annotator_attestation_coverage(
            rows,
            _rating_rows("synthetic-a", "synthetic-b"),
        )


def test_attestation_id_rejects_spreadsheet_active_cells(tmp_path):
    row = _row("synthetic-a")
    row["annotator_id"] = '=HYPERLINK("https://example.test")'
    path = _write_attestations(
        tmp_path,
        [row],
    )

    with pytest.raises(ValueError, match="spreadsheet-active"):
        freeze._load_annotator_attestations(path)


def test_freeze_requires_annotator_attestations_before_publication(tmp_path):
    packet, ratings = _freeze_inputs(tmp_path)
    output = tmp_path / "frozen"

    with pytest.raises(ValueError, match="annotator attestations are required"):
        freeze.freeze_ratings(ratings, packet_path=packet, output_root=output)

    assert not output.exists()


def test_freeze_retains_exact_annotator_attestation_bytes(tmp_path):
    packet, ratings = _freeze_inputs(tmp_path)
    attestations = _write_attestations(
        tmp_path,
        [_row("synthetic-a"), _row("synthetic-b")],
    )
    original = attestations.read_bytes()
    output = tmp_path / "frozen"

    manifest = freeze.freeze_ratings(
        ratings,
        annotator_attestations_path=attestations,
        packet_path=packet,
        output_root=output,
    )

    entry = manifest["annotator_attestations"]
    assert entry == {
        "archive_path": "governing_inputs/annotator_attestations.csv",
        "name": "annotator_attestations.csv",
        "bytes": len(original),
        "sha256": hashlib.sha256(original).hexdigest(),
        "n_annotators": 2,
    }
    assert (output / entry["archive_path"]).read_bytes() == original


def test_verifier_rejects_false_retained_attestation_after_coherent_rehash(tmp_path):
    packet, ratings = _freeze_inputs(tmp_path)
    attestations = _write_attestations(
        tmp_path,
        [_row("synthetic-a"), _row("synthetic-b")],
    )
    output = tmp_path / "frozen"
    freeze.freeze_ratings(
        ratings,
        annotator_attestations_path=attestations,
        packet_path=packet,
        output_root=output,
    )

    retained = output / freeze.ATTESTATION_ARCHIVE_PATH
    with retained.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["human_only_scoring"] = "false"
    with retained.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(freeze.ANNOTATOR_ATTESTATION_FIELDS),
        )
        writer.writeheader()
        writer.writerows(rows)
    changed = retained.read_bytes()

    manifest_path = output / "freeze_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["annotator_attestations"].update(
        bytes=len(changed),
        sha256=hashlib.sha256(changed).hexdigest(),
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="human_only_scoring"):
        verify.verify_frozen_snapshot(freeze_root=output, use_retained_inputs=True)
