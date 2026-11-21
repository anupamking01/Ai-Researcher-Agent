"""Synthetic-only regressions for one raw submission file per annotator.

These fixtures test ingestion and verification, not human independence or study
outcomes. No treatment mapping, evaluator, or model is used.
"""
import csv
import hashlib
import io
import json
import sys

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as verify
from human_eval_test_support import write_valid_annotator_attestations


def _csv_bytes(annotators):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(freeze.RATING_FIELDS)
    for annotator in annotators:
        for blind_id in ("H001", "H002"):
            writer.writerow([annotator, blind_id, "2", "3", "4", "3", "2", ""])
    return stream.getvalue().encode("utf-8")


@pytest.fixture
def submission_inputs(tmp_path):
    packet = tmp_path / "packet.jsonl"
    packet.write_text("".join(
        json.dumps({"blind_id": blind_id, "task_id": f"main-{index:02d}",
                    "question": "Synthetic question",
                    "report_markdown": "Synthetic report"}) + "\n"
        for index, blind_id in enumerate(("H001", "H002"), start=1)
    ), encoding="utf-8")
    protocol = tmp_path / "protocol.md"
    protocol.write_bytes(freeze.DEFAULT_PROTOCOL.read_bytes())
    assignment = tmp_path / "assignment.md"
    assignment.write_bytes(freeze.DEFAULT_ASSIGNMENT_PLAN.read_bytes())
    paths = [tmp_path / "a.csv", tmp_path / "b.csv"]
    for path, annotator in zip(paths, ("synthetic-a", "synthetic-b")):
        path.write_bytes(_csv_bytes([annotator]))
    return paths, {
        "annotator_attestations_path": write_valid_annotator_attestations(
            tmp_path / "annotator_attestations.csv",
            ("synthetic-a", "synthetic-b"),
        ),
        "packet_path": packet,
        "protocol_path": protocol,
        "assignment_plan_path": assignment,
        "output_root": tmp_path / "frozen",
    }


def _verify_options(options):
    return {
        "freeze_root" if key == "output_root" else key: value
        for key, value in options.items()
        if key != "annotator_attestations_path"
    }


@pytest.mark.parametrize("filename", ["combined.csv", "frozen_ratings.csv"])
def test_combined_submission_cannot_supply_two_independent_raters(submission_inputs, filename):
    paths, options = submission_inputs
    combined = paths[0].parent / filename
    original = _csv_bytes(["synthetic-a", "synthetic-b"])
    combined.write_bytes(original)
    # Four syntactically valid rows cover both items twice. The FILE identity,
    # not missing coverage, must reject this; even an output-like name is raw.
    with pytest.raises(ValueError, match="exactly one annotator_id"):
        freeze.freeze_ratings([combined], **options)
    assert not options["output_root"].exists()
    assert combined.read_bytes() == original


@pytest.mark.parametrize("position", [0, 1, 2])
def test_header_only_submission_is_not_silently_accepted(submission_inputs, position):
    paths, options = submission_inputs
    empty = paths[0].parent / "empty.csv"
    empty.write_bytes(_csv_bytes([]))
    submitted = paths.copy()
    submitted.insert(position, empty)
    with pytest.raises(ValueError, match="no annotation rows"):
        freeze.freeze_ratings(submitted, **options)
    assert not options["output_root"].exists()


def test_separate_submissions_preserve_raw_bytes_and_combined_output(submission_inputs):
    paths, options = submission_inputs
    originals = [path.read_bytes() for path in paths]
    manifest = freeze.freeze_ratings(paths, **options)
    assert manifest["frozen_ratings"]["n_annotators"] == 2
    assert manifest["frozen_ratings"]["n_rows"] == 4
    for original, entry in zip(originals, manifest["rating_inputs"]):
        assert (options["output_root"] / entry["archive_path"]).read_bytes() == original
        assert entry["sha256"] == hashlib.sha256(original).hexdigest()
    # The normalized output legitimately contains both annotators. Verify it
    # from retained raw inputs and also with optional external source copies.
    for external in (None, paths):
        receipt = verify.verify_frozen_snapshot(external, **_verify_options(options))
        assert receipt["n_rows"] == 4
        assert receipt["n_annotators"] == 2
        assert receipt["blinding_key_used"] is False


def test_canonically_equivalent_ids_cannot_supply_two_independent_raters(
    submission_inputs,
):
    paths, options = submission_inputs
    # These spellings are distinct Python strings and CSV byte sequences but
    # the same Unicode identity: precomposed e-acute versus e + combining acute.
    paths[0].write_bytes(_csv_bytes(["synthetic-é"]))
    paths[1].write_bytes(_csv_bytes(["synthetic-e\u0301"]))
    originals = [path.read_bytes() for path in paths]

    with pytest.raises(ValueError, match="canonically equivalent annotator_id"):
        freeze.freeze_ratings(paths, **options)

    assert originals == [path.read_bytes() for path in paths]
    assert not options["output_root"].exists()


def test_case_equivalent_ids_cannot_supply_two_independent_raters(
    submission_inputs,
):
    paths, options = submission_inputs
    paths[0].write_bytes(_csv_bytes(["synthetic-a"]))
    paths[1].write_bytes(_csv_bytes(["SYNTHETIC-A"]))
    write_valid_annotator_attestations(
        options["annotator_attestations_path"],
        ("synthetic-a", "SYNTHETIC-A"),
    )
    originals = [path.read_bytes() for path in paths]

    with pytest.raises(ValueError, match="canonically equivalent annotator_id"):
        freeze.freeze_ratings(paths, **options)

    assert originals == [path.read_bytes() for path in paths]
    assert not options["output_root"].exists()


@pytest.mark.parametrize(
    "hidden_character",
    ["\u200b", "\u202e", "\x00"],
    ids=["zero-width-space", "bidi-override", "nul-control"],
)
def test_annotator_id_rejects_hidden_unicode_characters_before_freeze(
    submission_inputs, hidden_character
):
    paths, options = submission_inputs
    paths[0].write_bytes(_csv_bytes([f"synthetic-{hidden_character}a"]))
    originals = [path.read_bytes() for path in paths]

    with pytest.raises(ValueError, match="annotator_id.*control or format"):
        freeze.freeze_ratings(paths, **options)

    assert originals == [path.read_bytes() for path in paths]
    assert not options["output_root"].exists()



@pytest.mark.parametrize(
    "hidden_character",
    ["\u034f", "\u180b", "\u180f", "\ufe0f", "\U000e0100"],
    ids=["combining-grapheme-joiner", "mongolian-selector-1",
         "mongolian-selector-4", "variation-selector-16", "variation-selector-17"],
)
def test_nonformat_invisible_pseudonym_marks_fail_closed_before_freeze(
    submission_inputs, hidden_character
):
    paths, options = submission_inputs
    disguised_id = f"synthetic-{hidden_character}a"
    # Matching self-reported coordinator attestations must not turn an
    # invisible spelling variant into evidence of an independent human rater.
    paths[0].write_bytes(_csv_bytes([disguised_id]))
    write_valid_annotator_attestations(
        options["annotator_attestations_path"],
        (disguised_id, "synthetic-b"),
    )
    originals = [path.read_bytes() for path in paths]

    with pytest.raises(ValueError, match="invisible Unicode identity mark"):
        freeze.freeze_ratings(paths, **options)

    assert originals == [path.read_bytes() for path in paths]
    assert not options["output_root"].exists()


@pytest.mark.parametrize(
    "hidden_character",
    ["\u034f", "\ufe0f"],
    ids=["combining-grapheme-joiner", "variation-selector-16"],
)
def test_nonformat_invisible_pseudonym_rejected_in_attestations(
    submission_inputs, hidden_character
):
    _paths, options = submission_inputs
    write_valid_annotator_attestations(
        options["annotator_attestations_path"],
        (f"synthetic-{hidden_character}a", "synthetic-b"),
    )
    with pytest.raises(ValueError, match="invisible Unicode identity mark"):
        freeze._load_annotator_attestations(options["annotator_attestations_path"])


def test_nonformat_invisible_pseudonym_cannot_count_as_second_rater():
    rows = [
        {
            "annotator_id": annotator_id,
            "blind_id": "H001",
            **{field: "3" for field in freeze.SCORE_FIELDS},
            "notes": "",
        }
        for annotator_id in ("synthetic-a", "synthetic-\u034fa")
    ]
    with pytest.raises(ValueError, match="invisible Unicode identity mark"):
        freeze._validate_assignment_coverage(rows, ["H001"])
    with pytest.raises(ValueError, match="invisible Unicode identity mark"):
        freeze.build_agreement(rows)


def test_annotator_id_rejects_control_character_before_whitespace_normalization(
    submission_inputs,
):
    paths, options = submission_inputs
    paths[0].write_bytes(_csv_bytes(["\tsynthetic-a"]))

    with pytest.raises(ValueError, match=r"annotator_id.*U\+0009"):
        freeze.freeze_ratings(paths, **options)

    assert not options["output_root"].exists()


def _canonical_collision_rows():
    return [
        {
            "annotator_id": annotator_id,
            "blind_id": "H001",
            **{field: "3" for field in freeze.SCORE_FIELDS},
            "notes": "",
        }
        for annotator_id in ("synthetic-é", "synthetic-e\u0301")
    ]


def test_coverage_helper_rejects_canonically_equivalent_rater_ids():
    with pytest.raises(ValueError, match="canonically equivalent annotator_id"):
        freeze._validate_assignment_coverage(_canonical_collision_rows(), ["H001"])


def test_agreement_helper_rejects_canonically_equivalent_rater_ids():
    with pytest.raises(ValueError, match="canonically equivalent annotator_id"):
        freeze.build_agreement(_canonical_collision_rows())


def test_hidden_character_cannot_create_a_second_rater_in_coverage_helper():
    rows = [
        {
            "annotator_id": annotator_id,
            "blind_id": "H001",
            **{field: "3" for field in freeze.SCORE_FIELDS},
            "notes": "",
        }
        for annotator_id in ("synthetic-a", "synthetic-\u200ba")
    ]

    with pytest.raises(ValueError, match="annotator_id.*control or format"):
        freeze._validate_assignment_coverage(rows, ["H001"])



@pytest.mark.parametrize(
    "compatible_id",
    ["ｓｙｎｔｈｅｔｉｃ－ａ", "synthetic-ａ"],
    ids=["fullwidth-id", "fullwidth-suffix"],
)
def test_compatibility_aliases_cannot_inflate_independent_rater_count(
    submission_inputs, compatible_id
):
    paths, options = submission_inputs
    paths[0].write_bytes(_csv_bytes(["synthetic-a"]))
    paths[1].write_bytes(_csv_bytes([compatible_id]))
    write_valid_annotator_attestations(
        options["annotator_attestations_path"],
        ("synthetic-a", compatible_id),
    )
    raw = [path.read_bytes() for path in paths]

    with pytest.raises(ValueError, match="canonically equivalent annotator_id"):
        freeze.freeze_ratings(paths, **options)

    assert [path.read_bytes() for path in paths] == raw
    assert not options["output_root"].exists()


def test_compatibility_aliases_cannot_appear_in_attestations(submission_inputs):
    _paths, options = submission_inputs
    write_valid_annotator_attestations(
        options["annotator_attestations_path"],
        ("annotator-IV", "annotator-Ⅳ"),
    )
    with pytest.raises(ValueError, match="canonically equivalent annotator attestations"):
        freeze._load_annotator_attestations(options["annotator_attestations_path"])


def test_compatibility_aliases_fail_coverage_and_agreement_checks():
    rows = [
        {
            "annotator_id": identity,
            "blind_id": "H001",
            **{field: "3" for field in freeze.SCORE_FIELDS},
            "notes": "",
        }
        for identity in ("synthetic-a", "ｓｙｎｔｈｅｔｉｃ－ａ")
    ]
    with pytest.raises(ValueError, match="canonically equivalent annotator_id"):
        freeze._validate_assignment_coverage(rows, ["H001"])
    with pytest.raises(ValueError, match="canonically equivalent annotator_id"):
        freeze.build_agreement(rows)


def test_single_compatibility_spelling_preserves_raw_bytes(submission_inputs):
    paths, options = submission_inputs
    compatible_id = "ｓｙｎｔｈｅｔｉｃ－ａ"
    paths[0].write_bytes(_csv_bytes([compatible_id]))
    write_valid_annotator_attestations(
        options["annotator_attestations_path"],
        (compatible_id, "synthetic-b"),
    )
    original = paths[0].read_bytes()

    manifest = freeze.freeze_ratings(paths, **options)

    assert (options["output_root"] / manifest["rating_inputs"][0]["archive_path"]).read_bytes() == original
    assert manifest["frozen_ratings"]["n_annotators"] == 2
    assert verify.verify_frozen_snapshot(
        None, **_verify_options(options)
    )["n_annotators"] == 2


def test_single_decomposed_id_preserves_submitted_spelling_and_bytes(
    submission_inputs,
):
    paths, options = submission_inputs
    decomposed = "synthetic-e\u0301"
    paths[0].write_bytes(_csv_bytes([decomposed]))
    write_valid_annotator_attestations(
        options["annotator_attestations_path"],
        (decomposed, "synthetic-b"),
    )
    original = paths[0].read_bytes()

    manifest = freeze.freeze_ratings(paths, **options)

    assert (options["output_root"] / manifest["rating_inputs"][0]["archive_path"]).read_bytes() == original
    with (options["output_root"] / "frozen_ratings.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        frozen_ids = {row["annotator_id"] for row in csv.DictReader(handle)}
    assert decomposed in frozen_ids
    assert "synthetic-é" not in frozen_ids


@pytest.mark.parametrize("source_kind", ["archive", "legacy"])
def test_verifier_rejects_rehashed_combined_raw_input(submission_inputs, source_kind):
    paths, options = submission_inputs
    manifest = freeze.freeze_ratings(paths, **options)
    root = options["output_root"]
    # Preserve every normalized score and agreement output, but collapse the
    # two archived submissions into one and recompute its local fingerprint.
    combined = _csv_bytes(["synthetic-a", "synthetic-b"])
    first, second = manifest["rating_inputs"]
    (root / first["archive_path"]).write_bytes(combined)
    (root / second["archive_path"]).unlink()
    first.update(bytes=len(combined), sha256=hashlib.sha256(combined).hexdigest())
    manifest["rating_inputs"] = [first]
    external = None
    if source_kind == "legacy":
        first.pop("archive_path")
        paths[0].write_bytes(combined)
        external = [paths[0]]
    (root / "freeze_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one annotator_id"):
        verify.verify_frozen_snapshot(external, **_verify_options(options))


def test_blank_annotator_id_remains_invalid(submission_inputs):
    paths, options = submission_inputs
    paths[0].write_bytes(_csv_bytes([" "]))
    with pytest.raises(ValueError, match="missing annotator_id"):
        freeze.freeze_ratings(paths, **options)
    assert not options["output_root"].exists()


def test_freeze_cli_rejects_combined_submission_before_publication(submission_inputs, monkeypatch):
    paths, options = submission_inputs
    paths[0].write_bytes(_csv_bytes(["synthetic-a", "synthetic-b"]))
    monkeypatch.setattr(sys, "argv", [
        "freeze_human_eval_ratings", str(paths[0]),
        "--packet", str(options["packet_path"]),
        "--protocol", str(options["protocol_path"]),
        "--assignment-plan", str(options["assignment_plan_path"]),
        "--annotator-attestations", str(options["annotator_attestations_path"]),
        "--output-root", str(options["output_root"]),
    ])
    with pytest.raises(SystemExit, match="exactly one annotator_id"):
        freeze.main()
    assert not options["output_root"].exists()


def test_verifier_applies_identity_gate_to_optional_external_copy(submission_inputs):
    paths, options = submission_inputs
    freeze.freeze_ratings(paths, **options)
    paths[0].write_bytes(_csv_bytes(["synthetic-a", "synthetic-b"]))
    with pytest.raises(ValueError, match="exactly one annotator_id"):
        verify.verify_frozen_snapshot([paths[0]], **_verify_options(options))


def _csv_for_cells(annotator, blind_ids):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(freeze.RATING_FIELDS)
    for blind_id in blind_ids:
        writer.writerow([annotator, blind_id, "2", "3", "4", "3", "2", ""])
    return stream.getvalue().encode("utf-8")


def _fragmented_submissions(tmp_path):
    specifications = (
        ("synthetic-a", ["H001"]),
        ("synthetic-b", ["H001"]),
        ("synthetic-c", ["H002"]),
        ("synthetic-d", ["H002"]),
    )
    paths = []
    for annotator, blind_ids in specifications:
        path = tmp_path / f"{annotator}.csv"
        path.write_bytes(_csv_for_cells(annotator, blind_ids))
        paths.append(path)
    return paths


def test_each_raw_submission_must_cover_the_complete_packet(submission_inputs):
    paths, options = submission_inputs
    fragmented = _fragmented_submissions(paths[0].parent)
    write_valid_annotator_attestations(
        options["annotator_attestations_path"],
        ("synthetic-a", "synthetic-b", "synthetic-c", "synthetic-d"),
    )
    originals = [path.read_bytes() for path in fragmented]

    # Aggregate coverage is two raters per item, but no annotator completed the
    # frozen packet. This must fail before a blinded freeze is published.
    with pytest.raises(ValueError, match="must cover every blinded report exactly once"):
        freeze.freeze_ratings(fragmented, **options)

    assert originals == [path.read_bytes() for path in fragmented]
    assert not options["output_root"].exists()


def test_shared_submission_coverage_gate_rejects_partial_packet_files(
    submission_inputs,
):
    paths, _options = submission_inputs
    fragmented = _fragmented_submissions(paths[0].parent)
    rows, _sources = freeze._load_ratings(
        fragmented,
        allowed_blind_ids={"H001", "H002"},
        require_single_annotator=True,
    )

    with pytest.raises(ValueError, match="must cover every blinded report exactly once"):
        freeze._validate_submission_coverage(rows, ["H001", "H002"])


def test_verifier_rejects_rehashed_fragmented_multi_annotator_archive(
    submission_inputs,
):
    paths, options = submission_inputs
    manifest = freeze.freeze_ratings(paths, **options)
    root = options["output_root"]
    archive_root = root / "raw_rating_inputs"
    for child in archive_root.iterdir():
        child.unlink()

    fragmented = _fragmented_submissions(paths[0].parent)
    attestation_path = root / freeze.ATTESTATION_ARCHIVE_PATH
    write_valid_annotator_attestations(
        attestation_path,
        ("synthetic-a", "synthetic-b", "synthetic-c", "synthetic-d"),
    )
    attestation_content = attestation_path.read_bytes()
    manifest["annotator_attestations"].update(
        bytes=len(attestation_content),
        sha256=hashlib.sha256(attestation_content).hexdigest(),
        n_annotators=4,
    )
    archived_paths = []
    rating_entries = []
    for index, source in enumerate(fragmented, start=1):
        content = source.read_bytes()
        archive_path = archive_root / f"{index:04d}.csv"
        archive_path.write_bytes(content)
        archived_paths.append(archive_path)
        rating_entries.append(
            {
                "input_index": index,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "archive_path": f"raw_rating_inputs/{index:04d}.csv",
            }
        )

    rows, _sources = freeze._load_ratings(
        archived_paths,
        allowed_blind_ids={"H001", "H002"},
        require_single_annotator=True,
    )
    frozen_path = root / "frozen_ratings.csv"
    freeze._write_csv(frozen_path, rows)
    agreement_path = root / "agreement.json"
    agreement_path.write_text(
        json.dumps(freeze.build_agreement(rows), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest["rating_inputs"] = rating_entries
    manifest["assignment_coverage"] = freeze._validate_assignment_coverage(
        rows, ["H001", "H002"]
    )
    manifest["frozen_ratings"].update(
        {
            "bytes": frozen_path.stat().st_size,
            "sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
            "n_rows": len(rows),
            "n_annotators": 4,
            "n_unique_blind_ids_rated": 2,
            "dimension_counts": {
                field: {"rated": len(rows), "missing": 0}
                for field in freeze.SCORE_FIELDS
            },
        }
    )
    manifest["agreement"].update(
        {
            "bytes": agreement_path.stat().st_size,
            "sha256": hashlib.sha256(agreement_path.read_bytes()).hexdigest(),
        }
    )
    (root / "freeze_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must cover every blinded report exactly once"):
        verify.verify_frozen_snapshot(**_verify_options(options))


@pytest.mark.parametrize("spelling", ["synthetic-a", " synthetic-a "])
def test_split_raw_submissions_from_same_annotator_are_rejected_before_freeze(
    submission_inputs, spelling
):
    paths, options = submission_inputs
    first = paths[0].parent / "a-part-1.csv"
    second = paths[0].parent / "a-part-2.csv"
    first.write_bytes(_csv_for_cells("synthetic-a", ["H001"]))
    second.write_bytes(_csv_for_cells(spelling, ["H002"]))
    originals = [source.read_bytes() for source in (first, second, paths[1])]
    with pytest.raises(ValueError, match="multiple submitted ratings CSV"):
        freeze.freeze_ratings([first, second, paths[1]], **options)
    assert not options["output_root"].exists()
    assert originals == [source.read_bytes() for source in (first, second, paths[1])]


def test_canonical_id_variants_cannot_split_one_annotator_across_files(
    submission_inputs,
):
    paths, options = submission_inputs
    first = paths[0].parent / "accented-part-1.csv"
    second = paths[0].parent / "accented-part-2.csv"
    independent = paths[0].parent / "independent.csv"
    first.write_bytes(_csv_for_cells("synthetic-é", ["H001"]))
    second.write_bytes(_csv_for_cells("synthetic-e\u0301", ["H002"]))
    independent.write_bytes(_csv_bytes(["synthetic-b"]))
    submitted = [first, second, independent]
    originals = [source.read_bytes() for source in submitted]

    with pytest.raises(ValueError, match="multiple submitted ratings CSV"):
        freeze.freeze_ratings(submitted, **options)

    assert originals == [source.read_bytes() for source in submitted]
    assert not options["output_root"].exists()


def test_verifier_rejects_rehashed_split_of_one_raw_annotator(submission_inputs):
    paths, options = submission_inputs
    manifest = freeze.freeze_ratings(paths, **options)
    root = options["output_root"]
    first, second = manifest["rating_inputs"]
    a_first = _csv_for_cells("synthetic-a", ["H001"])
    a_second = _csv_for_cells("synthetic-a", ["H002"])
    b_original = (root / second["archive_path"]).read_bytes()
    (root / "raw_rating_inputs" / "0001.csv").write_bytes(a_first)
    (root / "raw_rating_inputs" / "0002.csv").write_bytes(a_second)
    (root / "raw_rating_inputs" / "0003.csv").write_bytes(b_original)
    first.update(bytes=len(a_first), sha256=hashlib.sha256(a_first).hexdigest())
    manifest["rating_inputs"] = [
        first,
        {
            "input_index": 2,
            "bytes": len(a_second),
            "sha256": hashlib.sha256(a_second).hexdigest(),
            "archive_path": "raw_rating_inputs/0002.csv",
        },
        {**second, "input_index": 3, "archive_path": "raw_rating_inputs/0003.csv"},
    ]
    (root / "freeze_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="multiple submitted ratings CSV"):
        verify.verify_frozen_snapshot(**_verify_options(options))
