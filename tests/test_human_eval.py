import csv
import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import build_human_eval_packet as packet_builder
from scripts.build_human_eval_packet import build_packet


VARIANTS = ("D3", "D6", "P6", "P6V")


def _write_trace(
    tmp_path: Path,
    *,
    variant: str,
    task_id: str,
    run_id: str,
    completed: bool = True,
    create_report: bool = True,
) -> Path:
    outputs = tmp_path / "outputs"
    report_dir = outputs / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report_md = report_dir / "research_report.md"
    if create_report:
        report_md.write_text(
            f"# Report for {task_id}\n\nEvidence-backed synthetic report body.\n",
            encoding="utf-8",
        )

    trace_dir = outputs / "experiment_traces" / variant
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"{run_id}.json"
    payload = {
        "schema_version": 2,
        "experiment": {
            "variant_id": variant,
            "task_id": task_id,
            "task_set_id": "main-budget-v1-test",
        },
        "trace": {
            "run_id": run_id,
            "variant_id": variant,
            "task_id": task_id,
            "question": f"Research question for {task_id}?",
            "completed": completed,
            "report_path": f"./outputs/{run_id}/research_report.pdf",
        },
    }
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    return trace_path


def _write_complete_matrix(tmp_path: Path) -> Path:
    for task_index in range(1, 3):
        task_id = f"main-{task_index:02d}"
        for variant in VARIANTS:
            _write_trace(
                tmp_path,
                variant=variant,
                task_id=task_id,
                run_id=f"{variant.lower()}-{task_id}",
            )
    return tmp_path / "outputs" / "experiment_traces"


def _write_task_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "main_budget_tasks.json"
    payload = {
        "task_set_id": "main-budget-v1-test",
        "frozen_before_execution": True,
        "tasks": [
            {
                "id": f"main-{task_index:02d}",
                "question": f"Research question for main-{task_index:02d}?",
            }
            for task_index in range(1, 3)
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _build_packet(trace_root: Path, output_root: Path, tmp_path: Path, *, seed=20260915):
    return build_packet(
        trace_root,
        output_root,
        seed=seed,
        task_manifest_path=_write_task_manifest(tmp_path),
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_build_packet_is_deterministic_and_blinds_variant_labels(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)

    first = _build_packet(trace_root, tmp_path / "packet-a", tmp_path, seed=20260915)
    second = _build_packet(trace_root, tmp_path / "packet-b", tmp_path, seed=20260915)

    assert first["n_reports"] == 8
    assert first["n_tasks"] == 2
    assert first["blind_seed"] == 20260915
    assert first["task_set_id"] == "main-budget-v1-test"
    task_manifest = _write_task_manifest(tmp_path)
    assert first["task_manifest"]["n_tasks"] == 2
    assert first["task_manifest"]["bytes"] == task_manifest.stat().st_size
    assert first["task_manifest"]["sha256"] == hashlib.sha256(task_manifest.read_bytes()).hexdigest()
    assert first == second

    packet_a = _read_jsonl(tmp_path / "packet-a" / "packet.jsonl")
    packet_b = _read_jsonl(tmp_path / "packet-b" / "packet.jsonl")
    assert packet_a == packet_b
    assert len({row["blind_id"] for row in packet_a}) == 8
    assert all("variant_id" not in row for row in packet_a)
    assert all("run_id" not in row for row in packet_a)
    assert all(row["report_markdown"].startswith("# Report") for row in packet_a)

    with (tmp_path / "packet-a" / "blinding_key.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        key_rows = list(csv.DictReader(handle))
    assert {row["variant_id"] for row in key_rows} == set(VARIANTS)
    assert len(key_rows) == 8

    with (tmp_path / "packet-a" / "ratings_template.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        ratings_rows = list(csv.DictReader(handle))
        fieldnames = handle.seek(0) or None
    assert len(ratings_rows) == 8
    assert all("variant_id" not in row for row in ratings_rows)
    assert set(ratings_rows[0]) == {
        "annotator_id",
        "blind_id",
        "correctness_1_5",
        "completeness_1_5",
        "source_quality_1_5",
        "synthesis_reasoning_1_5",
        "clarity_1_5",
        "notes",
    }


def test_build_packet_rejects_treatment_leakage_before_publication(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    leaked_report = tmp_path / "outputs" / "d3-main-01" / "research_report.md"
    leaked_report.write_text(
        "# Synthetic report\n\nInternal variant_id P6V must not reach annotators.\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "packet"

    with pytest.raises(ValueError, match="annotator-facing treatment leakage"):
        _build_packet(trace_root, output_root, tmp_path)

    assert not output_root.exists()


@pytest.mark.parametrize(
    "leaked_text",
    [
        "Internal treatment _P6V_ must remain hidden.",
        "Internal treatment Ｐ６Ｖ must remain hidden.",
        "Internal treatment P\u200b6V must remain hidden.",
        "Internal treatment P**6**V must remain hidden.",
        "Internal treatment D&#51; must remain hidden.",
        "Internal treatment P[6](https://example.test)V must remain hidden.",
        "[source](https://example.test/%50%36%56)",
        "[source](https://example.test/%2550%2536%2556)",
        "[unused]: https://example.test/%2550%2536%2556",
        (
            "[shadowed]: https://safe.example/\n"
            "[shadowed]: https://example.test/%2550%2536%2556"
        ),
        "Internal treatment <span>P</span>6V must remain hidden.",
        "Internal treatment ![P](missing.png)6V must remain hidden.",
        '<input type="button" value="P&#54;V">',
        '<abbr title="P&#54;V">Treatment</abbr>',
        "P<span hidden>x</span>6V",
        'P<span style="display:none">x</span>6V',
        "P<script>0</script>6V",
    ],
    ids=[
        "markdown-underscores",
        "fullwidth",
        "zero-width",
        "markdown-emphasis",
        "html-entity",
        "markdown-link",
        "percent-encoded-link-destination",
        "nested-percent-encoded-link-destination",
        "unused-reference-destination",
        "shadowed-reference-destination",
        "inline-html",
        "image-alt-text",
        "input-value",
        "title-tooltip",
        "hidden-html",
        "css-hidden-html",
        "active-html",
    ],
)
def test_blinding_audit_rejects_rendered_treatment_label_variants(leaked_text):
    with pytest.raises(ValueError, match="annotator-facing treatment leakage"):
        packet_builder.validate_annotator_facing_content(
            [
                {
                    "blind_id": "H001",
                    "question": "Synthetic question?",
                    "report_markdown": leaked_text,
                }
            ],
            label="synthetic packet",
        )


@pytest.mark.parametrize("field", ["question", "report_markdown"])
@pytest.mark.parametrize(
    "leaked_text",
    [
        "Internal treatment P\u034f6V must remain hidden.",
        "Internal treatment D\ufe003 must remain hidden.",
        "Internal treatment D\U000e01003 must remain hidden.",
        "Internal treatment P\u180d6V must remain hidden.",
        "[source](https://example.test/%44%CD%8F%33)",
    ],
    ids=[
        "combining-grapheme-joiner",
        "basic-variation-selector",
        "supplementary-variation-selector",
        "mongolian-variation-selector",
        "percent-encoded-invisible-link-marker",
    ],
)
def test_blinding_audit_rejects_invisible_combining_mark_leakage(field, leaked_text):
    # These markers evade the previous NFKC + Cf-only audit, yet can visually
    # disclose D3/P6V before ratings are frozen.
    row = {
        "blind_id": "H001",
        "question": "Synthetic question?",
        "report_markdown": "Synthetic report.",
    }
    row[field] = leaked_text
    with pytest.raises(ValueError, match="annotator-facing treatment leakage"):
        packet_builder.validate_annotator_facing_content(
            [row], label="synthetic packet"
        )


def test_blinding_audit_preserves_meaningful_combining_diacritics():
    # Do not delete every Mn character: ordinary user-facing accents remain.
    assert packet_builder._canonical_audit_text("Cafe\u0301") == "Café"
    packet_builder.validate_annotator_facing_content(
        [{
            "blind_id": "H001",
            "question": "Review Cafe\u0301 source credibility?",
            "report_markdown": "Cafe\u0301 results are discussed in detail.",
        }],
        label="synthetic packet",
    )


def test_blinding_audit_fails_closed_on_excessive_percent_encoding_depth():
    destination = "https://example.test/%41"
    for _ in range(packet_builder.MAX_METADATA_DECODE_LAYERS + 1):
        destination = destination.replace("%", "%25")

    with pytest.raises(ValueError, match="percent-encoding depth exceeds"):
        packet_builder.validate_annotator_facing_content(
            [
                {
                    "blind_id": "H001",
                    "question": "Synthetic question?",
                    "report_markdown": f"[unused]: {destination}",
                }
            ],
            label="synthetic packet",
        )


def test_blinding_audit_rejects_opaque_inline_image_payload():
    # Valid PNG whose pixels spell the otherwise absent treatment label P6V.
    payload = (
        "iVBORw0KGgoAAAANSUhEUgAAADAAAAAUCAIAAABEXSnwAAABc0lEQVR42u2VP8tB"
        "YRjGb6/JSSg+gZJFMZzyJx2Pk0yE1DGdr8BmON/AYDSyWk6UMhqcSSnFiJhNBhY5"
        "uQxPySDT8ebtPdf0dHcNv67rvnscAOib9ENfJhvobwMJgsAYy2az6XR6Pp/fbrd6"
        "vZ5MJiVJ2u12RNRsNrvd7sOfz+eXy6XFRHiS1+vlj9VqJYpip9PRNA3AYDCoVCoA"
        "ptNptVrlntPpFA6HYbVeAwHw+/2pVGqz2QC4XC6tVguAaZrBYPB6vQIYDoeNRsNy"
        "oNc7NJlMYrHYer0ejUaMsVqtpigKETmdzkQiMZvNiGg8HpdKJeuX6JnO5XJlMhlJ"
        "korF4n6/93g8uq4D0HVdlmXu6ff7vMdIJMKj+qXKAIRCIdM0eVOBQIAPj8djPB5f"
        "LBaqquIDenf2siwbhkFEhmFEo1E+9Pl8giD0er1yufyRu3+T0OFwKBQKjLFcLrfdbh"
        "/zdrvtdrvP5/MnEnLYn6sNZAP9N6A7cIOuqKjm/7IAAAAASUVORK5CYII="
    )
    with pytest.raises(ValueError, match="Markdown images are not permitted"):
        packet_builder.validate_annotator_facing_content(
            [
                {
                    "blind_id": "H001",
                    "question": "Synthetic question?",
                    "report_markdown": f"![figure](data:image/png;base64,{payload})",
                }
            ],
            label="synthetic packet",
        )


@pytest.mark.parametrize(
    "markdown",
    [
        "![comparison figure](https://example.test/comparison.png)",
        "![comparison figure][figure]\n\n[figure]: https://example.test/comparison.png",
    ],
    ids=["inline-image", "reference-image"],
)
def test_blinding_audit_rejects_markdown_images(markdown):
    with pytest.raises(ValueError, match="Markdown images are not permitted"):
        packet_builder.validate_annotator_facing_content(
            [
                {
                    "blind_id": "H001",
                    "question": "Synthetic question?",
                    "report_markdown": markdown,
                }
            ],
            label="synthetic packet",
        )


@pytest.mark.parametrize(
    "markdown",
    [
        '[results](https://example.test/report "Data: quarterly results")',
        "[Data: quarterly results](https://example.test/report)",
    ],
    ids=["link-title", "link-text"],
)
def test_blinding_audit_allows_data_prefix_in_non_destination_metadata(markdown):
    packet_builder.validate_annotator_facing_content(
        [
            {
                "blind_id": "H001",
                "question": "Synthetic question?",
                "report_markdown": markdown,
            }
        ],
        label="synthetic packet",
    )


def test_blinding_audit_preserves_markdown_block_boundaries():
    packet_builder.validate_annotator_facing_content(
        [
            {
                "blind_id": "H001",
                "question": "Synthetic question?",
                "report_markdown": "A paragraph ending in P\n\n6V starts another paragraph.",
            }
        ],
        label="synthetic packet",
    )


def test_blinding_audit_rejects_raw_html_even_across_table_cells():
    with pytest.raises(ValueError, match="raw HTML is not permitted"):
        packet_builder.validate_annotator_facing_content(
            [
                {
                    "blind_id": "H001",
                    "question": "Synthetic question?",
                    "report_markdown": (
                        "<table><tr><td>P</td><td>6V</td></tr></table>"
                    ),
                }
            ],
            label="synthetic packet",
        )


@pytest.mark.parametrize(
    "invalid_seed",
    [True, False, 1.5, "20260915"],
    ids=["true", "false", "float", "numeric-string"],
)
def test_build_packet_rejects_non_integer_blinding_seed(tmp_path, invalid_seed):
    trace_root = _write_complete_matrix(tmp_path)
    output_root = tmp_path / "human-eval"

    with pytest.raises(TypeError, match="seed must be an integer"):
        _build_packet(trace_root, output_root, tmp_path, seed=invalid_seed)

    assert not output_root.exists()


def test_build_packet_rejects_duplicate_variant_task_cells(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    _write_trace(
        tmp_path,
        variant="D3",
        task_id="main-01",
        run_id="duplicate-d3-main-01",
    )

    with pytest.raises(ValueError, match="Duplicate variant/task cell"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_missing_markdown_report(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    missing = tmp_path / "outputs" / "d3-main-01" / "research_report.md"
    missing.unlink()

    with pytest.raises(FileNotFoundError, match="Missing Markdown report"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_incomplete_run(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["completed"] = False
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Incomplete run"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_incomplete_task_matrix(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    (trace_root / "P6V" / "p6v-main-02.json").unlink()

    with pytest.raises(ValueError, match="Expected variants"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_when_an_entire_frozen_task_is_missing(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    for variant in VARIANTS:
        (trace_root / variant / f"{variant.lower()}-main-02.json").unlink()
    output_root = tmp_path / "human-eval"

    with pytest.raises(ValueError, match="task coverage.*missing=.*main-02"):
        _build_packet(trace_root, output_root, tmp_path)

    assert not output_root.exists()


def test_build_packet_rejects_question_drift_from_frozen_task_manifest(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["question"] = "A changed research question?"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="question does not match frozen task manifest"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_task_set_identity_drift(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["experiment"]["task_set_id"] = "other-task-set"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="task_set_id mismatch"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_conflicting_task_set_identity(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["task_set_id"] = "other-task-set"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    output_root = tmp_path / "human-eval"

    with pytest.raises(ValueError, match="Conflicting task_set_id"):
        _build_packet(trace_root, output_root, tmp_path)

    assert not output_root.exists()


@pytest.mark.parametrize("invalid_version", [None, True, 1, 3, "2"])
def test_build_packet_rejects_noncanonical_trace_schema_version(
    tmp_path, invalid_version
):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    if invalid_version is None:
        payload.pop("schema_version")
    else:
        payload["schema_version"] = invalid_version
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    output_root = tmp_path / "human-eval"

    with pytest.raises(ValueError, match="schema_version must equal integer 2"):
        _build_packet(trace_root, output_root, tmp_path)

    assert not output_root.exists()


@pytest.mark.parametrize("section", ["experiment", "trace"])
def test_build_packet_rejects_nonobject_trace_sections(tmp_path, section):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload[section] = []
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    output_root = tmp_path / "human-eval"

    with pytest.raises(ValueError, match="experiment and trace must be objects"):
        _build_packet(trace_root, output_root, tmp_path)

    assert not output_root.exists()


def test_build_packet_rejects_unfrozen_task_manifest(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    task_manifest = _write_task_manifest(tmp_path)
    payload = json.loads(task_manifest.read_text(encoding="utf-8"))
    payload["frozen_before_execution"] = False
    task_manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="frozen before execution"):
        build_packet(
            trace_root,
            tmp_path / "human-eval",
            task_manifest_path=task_manifest,
        )


def _packet_output_snapshot(output_root: Path) -> dict[str, bytes]:
    return {
        name: (output_root / name).read_bytes()
        for name in packet_builder.PACKET_ARTIFACTS
        if (output_root / name).is_file()
    }


def test_build_packet_refuses_to_reblind_or_overwrite_published_bundle(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    output_root = tmp_path / "human-eval"
    _build_packet(trace_root, output_root, tmp_path, seed=20260915)
    before = _packet_output_snapshot(output_root)

    with pytest.raises(ValueError, match="refusing to overwrite"):
        _build_packet(trace_root, output_root, tmp_path, seed=7)

    assert _packet_output_snapshot(output_root) == before


@pytest.mark.parametrize("artifact_name", packet_builder.PACKET_ARTIFACTS)
def test_build_packet_rejects_any_existing_packet_artifact_before_writes(
    tmp_path, artifact_name
):
    trace_root = _write_complete_matrix(tmp_path)
    output_root = tmp_path / "human-eval"
    output_root.mkdir()
    existing = output_root / artifact_name
    existing.write_text("unrelated existing content\n", encoding="utf-8")
    before = existing.read_bytes()

    with pytest.raises(ValueError, match="refusing to overwrite"):
        _build_packet(trace_root, output_root, tmp_path)

    assert existing.read_bytes() == before
    for name in packet_builder.PACKET_ARTIFACTS:
        if name != artifact_name:
            assert not (output_root / name).exists()


def test_competing_packet_creation_after_preflight_cannot_be_overwritten(
    tmp_path, monkeypatch
):
    trace_root = _write_complete_matrix(tmp_path)
    output_root = tmp_path / "human-eval"
    original = packet_builder._write_text_exclusive
    raced = []

    def create_competing_packet(path, content):
        if path.name == "packet.jsonl" and not raced:
            path.write_text("competing packet\n", encoding="utf-8")
            raced.append(True)
        return original(path, content)

    monkeypatch.setattr(packet_builder, "_write_text_exclusive", create_competing_packet)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        _build_packet(trace_root, output_root, tmp_path)

    assert raced == [True]
    assert (output_root / "packet.jsonl").read_text(encoding="utf-8") == "competing packet\n"
    assert not (output_root / "blinding_key.csv").exists()
    assert not (output_root / "ratings_template.csv").exists()
    assert not (output_root / "manifest.json").exists()


def test_interrupted_packet_build_is_preserved_and_never_reused(tmp_path, monkeypatch):
    trace_root = _write_complete_matrix(tmp_path)
    output_root = tmp_path / "human-eval"

    with monkeypatch.context() as context:
        def fail_csv(*args, **kwargs):
            raise OSError("synthetic packet write failure")

        context.setattr(packet_builder, "_write_csv", fail_csv)
        with pytest.raises(OSError, match="synthetic packet write failure"):
            _build_packet(trace_root, output_root, tmp_path)

    packet_before = (output_root / "packet.jsonl").read_bytes()
    assert packet_before
    assert not (output_root / "manifest.json").exists()

    with pytest.raises(ValueError, match="refusing to overwrite"):
        _build_packet(trace_root, output_root, tmp_path)
    assert (output_root / "packet.jsonl").read_bytes() == packet_before
    assert not (output_root / "manifest.json").exists()


def test_build_packet_rejects_validator_source_drift_during_construction(
    tmp_path, monkeypatch
):
    trace_root = _write_complete_matrix(tmp_path)
    output_root = tmp_path / "human-eval"
    loaded = packet_builder.content_validator_source_contract()
    changed = {**loaded, "sha256": "0" * 64}
    observed = iter((loaded, changed))
    monkeypatch.setattr(
        packet_builder,
        "_content_validator_source_contract_now",
        lambda: next(observed),
        raising=False,
    )

    with pytest.raises(ValueError, match="changed during packet construction"):
        _build_packet(trace_root, output_root, tmp_path)

    assert not output_root.exists()


def test_nonpacket_children_do_not_block_first_packet_publication(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    output_root = tmp_path / "human-eval"
    (output_root / "frozen-v0").mkdir(parents=True)
    (output_root / "frozen-v0" / "README.txt").write_text(
        "unrelated child directory\n", encoding="utf-8"
    )

    manifest = _build_packet(trace_root, output_root, tmp_path)

    assert manifest["n_reports"] == 8
    assert (output_root / "manifest.json").is_file()
    assert (output_root / "frozen-v0" / "README.txt").read_text(encoding="utf-8") == (
        "unrelated child directory\n"
    )


def test_build_packet_rejects_cross_run_report_substitution(tmp_path):
    """Completed traces may not borrow another treatment's report."""
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["report_path"] = "./outputs/d6-main-01/research_report.pdf"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    output_root = tmp_path / "packet-cross-run"
    with pytest.raises(ValueError, match="Report source is not bound to trace run_id"):
        _build_packet(trace_root, output_root, tmp_path)
    assert not output_root.exists()



@pytest.mark.parametrize(
    ("target_variant", "target_task"),
    [("D6", "main-01"), ("P6", "main-02")],
)
def test_build_packet_rejects_duplicate_run_id_across_distinct_cells(
    tmp_path, target_variant, target_task
):
    """One report/run must not be repackaged as two independent treatment cells."""
    trace_root = _write_complete_matrix(tmp_path)
    original_path = (
        trace_root / target_variant / f"{target_variant.lower()}-{target_task}.json"
    )
    payload = json.loads(original_path.read_text(encoding="utf-8"))
    shared_run_id = "d3-main-01"
    payload["trace"]["run_id"] = shared_run_id
    payload["trace"]["report_path"] = (
        f"./outputs/{shared_run_id}/research_report.pdf"
    )
    duplicate_path = trace_root / target_variant / f"{shared_run_id}.json"
    original_path.unlink()
    duplicate_path.write_text(json.dumps(payload), encoding="utf-8")

    output_root = tmp_path / "packet-shared-treatment-run"
    with pytest.raises(ValueError, match="Duplicate experiment run_id"):
        _build_packet(trace_root, output_root, tmp_path)
    assert not output_root.exists()


def test_build_packet_rejects_encoded_report_directory_traversal(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["report_path"] = (
        "./outputs/d3-main-01/%2e%2e/d6-main-01/research_report.pdf"
    )
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Report source is not bound to trace run_id"):
        _build_packet(trace_root, tmp_path / "packet-traversal", tmp_path)


def test_build_packet_rejects_trace_filename_identity_mismatch(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["run_id"] = "d6-main-01"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Trace file identity"):
        _build_packet(trace_root, tmp_path / "packet-run-mismatch", tmp_path)


@pytest.mark.parametrize(
    ("field", "conflicting_value"),
    [("variant_id", "P6V"), ("task_id", "main-02")],
)
def test_build_packet_rejects_conflicting_trace_and_experiment_identity(
    tmp_path: Path, field: str, conflicting_value: str
):
    """A treatment/task cannot be inferred from one of two disagreeing identities."""
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["experiment"][field] = conflicting_value
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    output_root = tmp_path / "packet-conflicting-identity"

    with pytest.raises(ValueError, match=f"Conflicting {field}"):
        _build_packet(trace_root, output_root, tmp_path)
    assert not output_root.exists()


def test_build_packet_accepts_experiment_only_identity_for_legacy_traces(tmp_path: Path):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"].pop("variant_id")
    payload["trace"].pop("task_id")
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    manifest = _build_packet(trace_root, tmp_path / "packet-legacy-identity", tmp_path)
    assert manifest["n_reports"] == 8


@pytest.mark.parametrize("invalid_completed", ["false", "true", 1, {"done": True}])
def test_build_packet_rejects_truthy_non_boolean_completion(tmp_path, invalid_completed):
    """Malformed completion values must not authorize blinded packet publication."""
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["completed"] = invalid_completed
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    destination = tmp_path / "packet-invalid-completion"

    with pytest.raises(ValueError, match="Incomplete run"):
        _build_packet(trace_root, destination, tmp_path)
    assert not destination.exists()

def test_build_packet_rejects_symlinked_trace_file_before_publication(tmp_path):
    """Trace provenance must be a direct file, not a link to a copied record."""
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    backing = trace_path.with_suffix(".backing")
    trace_path.rename(backing)
    trace_path.symlink_to(backing.name)
    destination = tmp_path / "packet-linked-source"

    with pytest.raises(ValueError, match="symbolic link"):
        _build_packet(trace_root, destination, tmp_path)
    assert not destination.exists()


def test_build_packet_rejects_trace_path_replacement_during_capture(
    tmp_path, monkeypatch
):
    """A pathname swap must not become the packet's newly trusted source."""
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    destination = tmp_path / "packet-replaced-source"
    original_os_read = os.read
    replaced = False

    def replace_during_read(fd, size):
        nonlocal replaced
        content = original_os_read(fd, size)
        if not replaced and content.startswith(b'{"schema_version": 2'):
            trace_path.unlink()
            trace_path.write_bytes(content + b"\n")
            replaced = True
        return content

    monkeypatch.setattr(os, "read", replace_during_read)

    with pytest.raises(ValueError, match="replaced during capture"):
        _build_packet(trace_root, destination, tmp_path)
    assert replaced is True
    assert not destination.exists()


def test_build_packet_rejects_symlinked_trace_root(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    shortcut = tmp_path / "linked-traces"
    shortcut.symlink_to(trace_root, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic link"):
        _build_packet(shortcut, tmp_path / "packet-linked-root", tmp_path)
    assert not (tmp_path / "packet-linked-root").exists()
