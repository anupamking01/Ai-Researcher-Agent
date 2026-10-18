"""Build a deterministic blinded packet for human evaluation.

This module is intentionally offline. It reads completed experiment traces and
the Markdown reports already produced by those runs, then emits annotator-facing
artifacts that do not reveal experimental variant labels. The coordinator-only
blinding key is written separately. Published packet artifacts are create-only:
an existing packet/key/template/manifest is never overwritten in place.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import random
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

from markdown_it import MarkdownIt


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE_ROOT = REPO_ROOT / "outputs" / "experiment_traces"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "human_eval"
DEFAULT_TASK_MANIFEST = REPO_ROOT / "experiments" / "main_budget_tasks.json"
EXPECTED_VARIANTS = ("D3", "D6", "P6", "P6V")
DEFAULT_SEED = 20260915
PACKET_ARTIFACTS = ("packet.jsonl", "blinding_key.csv", "ratings_template.csv", "manifest.json")
MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "study_id",
        "task_set_id",
        "task_manifest",
        "blind_seed",
        "n_reports",
        "n_tasks",
        "variants",
        "artifacts",
        "source_artifacts",
        "packet",
        "ratings_template",
        "blinding_key",
        "blinding_note",
    }
)
ARTIFACT_KEYS = frozenset({"packet", "ratings_template", "blinding_key"})
BLINDING_NOTE = (
    "Annotators receive packet.jsonl and ratings_template.csv only. "
    "blinding_key.csv is coordinator-only until scoring is frozen."
)

RATING_FIELDS = (
    "annotator_id",
    "blind_id",
    "correctness_1_5",
    "completeness_1_5",
    "source_quality_1_5",
    "synthesis_reasoning_1_5",
    "clarity_1_5",
    "notes",
)

_TREATMENT_LABEL_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:P6V|P6|D6|D3)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_COORDINATOR_MARKER_RE = re.compile(
    r"(?:variant_id|run_id|trace_path|report_path|blinding_key\.csv|experiment_traces)",
    re.IGNORECASE,
)
_OPAQUE_DATA_URI_RE = re.compile(r"^\s*data:", re.IGNORECASE)
MARKDOWN_RENDERER_DISTRIBUTION = "markdown-it-py"
MARKDOWN_RENDERER_PRESET = "commonmark"
MARKDOWN_RENDERER_OPTIONS = {"html": True}
MAX_METADATA_DECODE_LAYERS = 64
_MARKDOWN_RENDERER = MarkdownIt(MARKDOWN_RENDERER_PRESET, MARKDOWN_RENDERER_OPTIONS)
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "dl",
        "dt",
        "dd",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)


class _RenderedTextParser(HTMLParser):
    """Collect browser-visible text while preserving inline adjacency."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.attribute_values: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        self.attribute_values.extend(
            (name, value)
            for name, value in attrs
            if isinstance(name, str) and isinstance(value, str) and value
        )
        if tag in _BLOCK_TAGS:
            self.parts.append(" ")
        if tag == "img":
            alt_text = next(
                (value for name, value in attrs if name == "alt"),
                "",
            )
            self.parts.append(alt_text or "")

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def content_validator_runtime_contract() -> dict:
    """Describe every runtime component that affects visible-text auditing."""
    return {
        "schema_version": 1,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "unicode_database_version": unicodedata.unidata_version,
        "markdown_it_py_version": importlib.metadata.version(
            MARKDOWN_RENDERER_DISTRIBUTION
        ),
        "mdurl_version": importlib.metadata.version("mdurl"),
        "markdown_preset": MARKDOWN_RENDERER_PRESET,
        "markdown_options": dict(MARKDOWN_RENDERER_OPTIONS),
    }


def _canonical_audit_text(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", text)
        if unicodedata.category(character) != "Cf"
    )


def _metadata_fields(value, *, field_name: str | None = None):
    if isinstance(value, str):
        if field_name is not None:
            yield field_name.lower(), value
    elif isinstance(value, dict):
        for name, child in value.items():
            yield from _metadata_fields(child, field_name=str(name))
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _metadata_fields(child, field_name=field_name)


def _rendered_markdown_parts(
    text: str,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    environment = {}
    parser = _RenderedTextParser()
    parser.feed(_MARKDOWN_RENDERER.render(text, environment))
    parser.close()
    metadata = (*parser.attribute_values, *_metadata_fields(environment))
    return "".join(parser.parts), metadata


def _decoded_attribute_forms(value: str):
    """Yield canonical URL/metadata text through every percent-decoding layer."""
    current = _canonical_audit_text(value)
    for layer in range(MAX_METADATA_DECODE_LAYERS + 1):
        yield current
        decoded = _canonical_audit_text(unquote(current))
        if decoded == current:
            return
        if layer == MAX_METADATA_DECODE_LAYERS:
            raise ValueError(
                "annotator-facing metadata percent-encoding depth exceeds "
                f"the {MAX_METADATA_DECODE_LAYERS}-layer audit limit"
            )
        current = decoded


def _contains_raw_html(text: str) -> bool:
    for token in _MARKDOWN_RENDERER.parse(text):
        if token.type in {"html_block", "html_inline"}:
            return True
        if any(
            child.type in {"html_block", "html_inline"}
            for child in (token.children or ())
        ):
            return True
    return False


def _contains_markdown_image(text: str) -> bool:
    for token in _MARKDOWN_RENDERER.parse(text):
        if token.type == "image":
            return True
        if any(child.type == "image" for child in (token.children or ())):
            return True
    return False


def validate_annotator_facing_content(rows: list[dict], *, label: str) -> None:
    """Reject treatment/coordinator markers embedded in annotator-visible text."""
    for index, row in enumerate(rows, start=1):
        blind_id = str(row.get("blind_id") or f"row {index}").strip()
        for field in ("question", "report_markdown"):
            text = row.get(field)
            if not isinstance(text, str):
                continue
            if _contains_raw_html(text):
                raise ValueError(
                    "annotator-facing treatment leakage risk in "
                    f"{label} {blind_id} {field}: raw HTML is not permitted"
                )
            if _contains_markdown_image(text):
                raise ValueError(
                    "annotator-facing treatment leakage risk in "
                    f"{label} {blind_id} {field}: Markdown images are not permitted"
                )
            rendered_text, attribute_values = _rendered_markdown_parts(text)
            audit_texts = (
                _canonical_audit_text(text),
                _canonical_audit_text(rendered_text),
            )
            for audit_text in audit_texts:
                match = _COORDINATOR_MARKER_RE.search(
                    audit_text
                ) or _TREATMENT_LABEL_RE.search(audit_text)
                if match:
                    raise ValueError(
                        "annotator-facing treatment leakage in "
                        f"{label} {blind_id} {field}: "
                        f"forbidden marker {match.group(0)!r}"
                    )
            for attribute_name, value in attribute_values:
                for audit_text in _decoded_attribute_forms(value):
                    if (
                        attribute_name in {"href", "src"}
                        and _OPAQUE_DATA_URI_RE.search(audit_text)
                    ):
                        raise ValueError(
                            "annotator-facing treatment leakage risk in "
                            f"{label} {blind_id} {field}: opaque data URI is not permitted"
                        )
                    match = _COORDINATOR_MARKER_RE.search(
                        audit_text
                    ) or _TREATMENT_LABEL_RE.search(audit_text)
                    if match:
                        raise ValueError(
                            "annotator-facing treatment leakage in "
                            f"{label} {blind_id} {field}: "
                            f"forbidden marker {match.group(0)!r}"
                        )


def _load_json_object(content: bytes, *, label: str) -> dict:
    """Decode one UTF-8 JSON object while rejecting ambiguous duplicate keys."""
    def unique_object_pairs(pairs):
        value = {}
        for key, child in pairs:
            if key in value:
                raise ValueError(f"{label} contains duplicate JSON key {key!r}")
            value[key] = child
        return value

    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=unique_object_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _byte_fingerprint(content: bytes) -> dict:
    return {
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _resolve_report_markdown(trace_root: Path, report_path: str, *, run_id: str) -> Path:
    """Require the report to belong to the same run as its experiment trace."""
    if not run_id or run_id in (".", "..") or "/" in run_id or "\\" in run_id:
        raise ValueError(f"Invalid experiment trace run_id: {run_id!r}")
    if not report_path:
        raise FileNotFoundError("Missing Markdown report: trace has no report_path")

    decoded = Path(unquote(str(report_path)))
    if decoded.suffix.lower() == ".pdf":
        decoded = decoded.with_suffix(".md")

    # Recorded reports are ./outputs/<run_id>/research_report.pdf; human
    # annotation consumes the sibling Markdown report of that exact run.
    repo_root = trace_root.parent.parent
    expected = repo_root / "outputs" / run_id / "research_report.md"
    candidate = decoded if decoded.is_absolute() else repo_root / decoded
    if candidate != expected:
        raise ValueError(
            f"Report source is not bound to trace run_id {run_id!r}: {report_path!r}"
        )
    if candidate.is_symlink() or candidate.parent.is_symlink() or (repo_root / "outputs").is_symlink():
        raise ValueError(f"Report source must not be a symbolic link: {candidate}")
    if not candidate.is_file():
        raise FileNotFoundError(f"Missing Markdown report: {candidate}")
    return candidate


def _consistent_trace_identity(
    experiment: dict, trace: dict, field: str, *, trace_path: Path
) -> str:
    """Reject conflicting treatment/task identities in the same persisted trace.

    Older traces can omit an identity in one section; retain the original
    fallback in that case, but never silently prefer one conflicting value.
    """
    trace_value = str(trace.get(field) or "").strip()
    experiment_value = str(experiment.get(field) or "").strip()
    if trace_value and experiment_value and trace_value != experiment_value:
        raise ValueError(
            f"Conflicting {field} between trace and experiment in {trace_path}: "
            f"{trace_value!r} != {experiment_value!r}"
        )
    return trace_value or experiment_value


def _validated_trace_sections(payload: dict, *, trace_path: Path) -> tuple[dict, dict]:
    """Require the canonical treatment-trace envelope used by this study."""
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 2:
        raise ValueError(
            f"Experiment trace {trace_path} schema_version must equal integer 2"
        )
    experiment = payload.get("experiment")
    trace = payload.get("trace")
    if not isinstance(experiment, dict) or not isinstance(trace, dict):
        raise ValueError(
            f"Experiment trace {trace_path} experiment and trace must be objects"
        )
    return experiment, trace


def _load_task_manifest(task_manifest_path: Path) -> dict:
    """Load and validate the frozen task set used by the human-eval packet."""
    task_manifest_path = Path(task_manifest_path)
    if not task_manifest_path.is_file():
        raise FileNotFoundError(f"Frozen task manifest does not exist: {task_manifest_path}")
    content = task_manifest_path.read_bytes()
    payload = _load_json_object(content, label=f"Frozen task manifest {task_manifest_path}")
    if payload.get("frozen_before_execution") is not True:
        raise ValueError("Human evaluation requires a task manifest frozen before execution")
    task_set_id = str(payload.get("task_set_id") or "").strip()
    task_rows = payload.get("tasks")
    if not task_set_id:
        raise ValueError("Frozen task manifest is missing task_set_id")
    if not isinstance(task_rows, list) or not task_rows:
        raise ValueError("Frozen task manifest contains no tasks")
    tasks: dict[str, str] = {}
    for index, row in enumerate(task_rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Frozen task manifest task {index} must be an object")
        task_id = str(row.get("id") or "").strip()
        question = str(row.get("question") or "").strip()
        if not task_id or not question:
            raise ValueError(f"Frozen task manifest task {index} is missing id/question")
        if task_id in tasks:
            raise ValueError(f"Duplicate task ID in frozen task manifest: {task_id}")
        tasks[task_id] = question
    return {
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "task_set_id": task_set_id,
        "tasks": tasks,
    }


def _load_records(trace_root: Path, *, task_manifest: dict) -> list[dict]:
    if trace_root.is_symlink():
        raise ValueError(f"Experiment trace root must not be a symbolic link: {trace_root}")
    if not trace_root.is_dir():
        raise FileNotFoundError(f"Trace root does not exist: {trace_root}")

    records: list[dict] = []
    seen_cells: set[tuple[str, str]] = set()

    for trace_path in sorted(trace_root.glob("*/*.json")):
        if trace_path.is_symlink() or trace_path.parent.is_symlink():
            raise ValueError(
                f"Experiment trace source must not traverse a symbolic link: {trace_path}"
            )
        trace_content = trace_path.read_bytes()
        payload = _load_json_object(trace_content, label=f"Experiment trace {trace_path}")
        experiment, trace = _validated_trace_sections(payload, trace_path=trace_path)

        variant_id = _consistent_trace_identity(
            experiment, trace, "variant_id", trace_path=trace_path
        )
        task_id = _consistent_trace_identity(
            experiment, trace, "task_id", trace_path=trace_path
        )
        run_id = str(trace.get("run_id") or trace_path.stem).strip()
        if trace_path.parent.name != variant_id or trace_path.stem != run_id or trace_path.is_symlink():
            raise ValueError(f"Trace file identity does not match variant/run: {trace_path}")
        question = str(trace.get("question") or "").strip()
        trace_task_set_id = _consistent_trace_identity(
            experiment,
            trace,
            "task_set_id",
            trace_path=trace_path,
        )

        if not variant_id or not task_id:
            raise ValueError(f"Trace missing variant/task identity: {trace_path}")
        if variant_id not in EXPECTED_VARIANTS:
            raise ValueError(f"Unexpected variant {variant_id!r} in {trace_path}")
        if trace.get("completed") is not True:
            raise ValueError(f"Incomplete run cannot enter human evaluation: {variant_id}/{task_id}")
        if not question:
            raise ValueError(f"Trace missing research question: {variant_id}/{task_id}")
        if trace_task_set_id != task_manifest["task_set_id"]:
            raise ValueError(
                f"Trace task_set_id mismatch for {variant_id}/{task_id}: "
                f"{trace_task_set_id!r} != {task_manifest['task_set_id']!r}"
            )
        expected_question = task_manifest["tasks"].get(task_id)
        if expected_question is None:
            raise ValueError(f"Unexpected task {task_id!r}; not present in frozen task manifest")
        if question != expected_question:
            raise ValueError(
                f"Trace question does not match frozen task manifest for {variant_id}/{task_id}"
            )

        cell = (variant_id, task_id)
        if cell in seen_cells:
            raise ValueError(f"Duplicate variant/task cell: {variant_id}/{task_id}")
        seen_cells.add(cell)

        report_md = _resolve_report_markdown(
            trace_root, str(trace.get("report_path") or ""), run_id=run_id
        )
        report_content = report_md.read_bytes()
        report_text = report_content.decode("utf-8").strip()
        if not report_text:
            raise ValueError(f"Empty Markdown report: {report_md}")

        repo_root = trace_root.parent.parent
        records.append(
            {
                "variant_id": variant_id,
                "task_id": task_id,
                "run_id": run_id,
                "question": question,
                "report_markdown": report_text,
                "trace_path": trace_path.relative_to(repo_root).as_posix(),
                "report_path": report_md.relative_to(repo_root).as_posix(),
                "trace_fingerprint": _byte_fingerprint(trace_content),
                "report_fingerprint": _byte_fingerprint(report_content),
            }
        )

    if not records:
        raise ValueError(f"No experiment traces found under {trace_root}")

    observed_task_ids = {record["task_id"] for record in records}
    expected_task_ids = set(task_manifest["tasks"])
    if observed_task_ids != expected_task_ids:
        missing = sorted(expected_task_ids - observed_task_ids)
        unexpected = sorted(observed_task_ids - expected_task_ids)
        raise ValueError(
            "Human-evaluation task coverage must exactly match the frozen task manifest; "
            f"missing={missing}, unexpected={unexpected}"
        )

    task_variants: dict[str, set[str]] = {}
    for record in records:
        task_variants.setdefault(record["task_id"], set()).add(record["variant_id"])
    expected = set(EXPECTED_VARIANTS)
    for task_id, variants in sorted(task_variants.items()):
        if variants != expected:
            raise ValueError(
                f"Expected variants {list(EXPECTED_VARIANTS)} for task {task_id}; "
                f"got {sorted(variants)}"
            )

    return records


def _refuse_overwrite(path: Path) -> ValueError:
    return ValueError(
        "refusing to overwrite existing human-evaluation packet artifact: "
        f"{path}; preserve the published bundle or choose a new output root"
    )


def _write_text_exclusive(path: Path, content: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise _refuse_overwrite(path) from exc


def _write_csv(path: Path, fieldnames: tuple[str, ...] | list[str], rows: list[dict]) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except FileExistsError as exc:
        raise _refuse_overwrite(path) from exc


def _artifact_fingerprint(path: Path) -> dict:
    content = path.read_bytes()
    return {"path": path.name, **_byte_fingerprint(content)}


def build_packet(
    trace_root: Path,
    output_root: Path,
    *,
    seed: int = DEFAULT_SEED,
    task_manifest_path: Path = DEFAULT_TASK_MANIFEST,
) -> dict:
    """Build deterministic blinded evaluation artifacts from completed traces."""
    if type(seed) is not int:
        raise TypeError("seed must be an integer")

    trace_root = Path(trace_root)
    output_root = Path(output_root)
    task_manifest_path = Path(task_manifest_path)
    task_manifest = _load_task_manifest(task_manifest_path)
    records = _load_records(trace_root, task_manifest=task_manifest)

    # Sort first so filesystem traversal order can never affect randomization.
    shuffled = sorted(records, key=lambda row: (row["task_id"], row["variant_id"], row["run_id"]))
    random.Random(seed).shuffle(shuffled)

    packet_rows: list[dict] = []
    key_rows: list[dict] = []
    ratings_rows: list[dict] = []
    source_artifacts: list[dict] = []

    for index, record in enumerate(shuffled, start=1):
        blind_id = f"H{index:03d}"
        packet_rows.append(
            {
                "blind_id": blind_id,
                "task_id": record["task_id"],
                "question": record["question"],
                "report_markdown": record["report_markdown"],
            }
        )
        key_rows.append(
            {
                "blind_id": blind_id,
                "variant_id": record["variant_id"],
                "task_id": record["task_id"],
                "run_id": record["run_id"],
                "trace_path": record["trace_path"],
                "report_path": record["report_path"],
            }
        )
        ratings_rows.append(
            {
                "annotator_id": "",
                "blind_id": blind_id,
                "correctness_1_5": "",
                "completeness_1_5": "",
                "source_quality_1_5": "",
                "synthesis_reasoning_1_5": "",
                "clarity_1_5": "",
                "notes": "",
            }
        )
        source_artifacts.append(
            {
                "blind_id": blind_id,
                "trace": record["trace_fingerprint"],
                "report": record["report_fingerprint"],
            }
        )

    validate_annotator_facing_content(packet_rows, label="packet")

    if output_root.is_symlink():
        raise ValueError(f"human-evaluation output root must not be a symbolic link: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    existing = [
        output_root / name
        for name in PACKET_ARTIFACTS
        if (output_root / name).exists() or (output_root / name).is_symlink()
    ]
    if existing:
        raise ValueError(
            "refusing to overwrite existing human-evaluation packet artifacts: "
            + ", ".join(path.name for path in existing)
            + "; preserve the published bundle or choose a new output root"
        )

    packet_path = output_root / "packet.jsonl"
    key_path = output_root / "blinding_key.csv"
    ratings_template_path = output_root / "ratings_template.csv"
    # packet.jsonl is the reservation point. Exclusive creation is the decisive
    # guard against two builders passing the preflight check concurrently.
    _write_text_exclusive(
        packet_path,
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in packet_rows)
        + "\n",
    )

    _write_csv(
        key_path,
        ["blind_id", "variant_id", "task_id", "run_id", "trace_path", "report_path"],
        key_rows,
    )
    _write_csv(ratings_template_path, list(RATING_FIELDS), ratings_rows)

    manifest = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "task_set_id": task_manifest["task_set_id"],
        "task_manifest": {
            "name": task_manifest_path.name,
            "bytes": task_manifest["bytes"],
            "sha256": task_manifest["sha256"],
            "n_tasks": len(task_manifest["tasks"]),
        },
        "blind_seed": seed,
        "n_reports": len(packet_rows),
        "n_tasks": len({row["task_id"] for row in packet_rows}),
        "variants": list(EXPECTED_VARIANTS),
        "artifacts": {
            "packet": _artifact_fingerprint(packet_path),
            "ratings_template": _artifact_fingerprint(ratings_template_path),
            "blinding_key": _artifact_fingerprint(key_path),
        },
        "source_artifacts": source_artifacts,
        "packet": "packet.jsonl",
        "ratings_template": "ratings_template.csv",
        "blinding_key": "blinding_key.csv",
        "blinding_note": BLINDING_NOTE,
    }
    _write_text_exclusive(
        output_root / "manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-root", type=Path, default=DEFAULT_TRACE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--task-manifest", type=Path, default=DEFAULT_TASK_MANIFEST)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    try:
        manifest = build_packet(
            args.trace_root,
            args.output_root,
            seed=args.seed,
            task_manifest_path=args.task_manifest,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL PACKET BUILD: FAIL: {exc}") from exc
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
