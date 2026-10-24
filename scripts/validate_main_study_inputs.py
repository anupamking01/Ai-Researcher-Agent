"""Fail-closed preflight validation for canonical main-study CSV inputs.

Run this before inferential analysis to detect malformed scientific measurements,
mismatched treatment/evaluator identities, or drift from the preregistered study
matrix without modifying or repairing preserved experiment artifacts.
"""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from scripts.validate_numeric_inputs import (
    require_nonnegative,
    require_nonnegative_integer,
    require_unit_interval,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_CSV = REPO_ROOT / "outputs" / "main_study_runs.csv"
SUPPORT_CSV = REPO_ROOT / "outputs" / "posthoc_support_runs.csv"

COUNT_FIELDS = ("claims_checked", "supported", "partially_supported", "unsupported", "contradicted")
INTEGER_MEASUREMENT_FIELDS = ("successful_sources", "total_tokens", "model_calls", "report_words")
CONTINUOUS_MEASUREMENT_FIELDS = ("treatment_cost_usd", "latency_seconds")
IDENTITY_FIELDS = ("variant_id", "task_id")
EXPECTED_VARIANTS = frozenset({"D3", "D6", "P6", "P6V"})
EXPECTED_TASKS = frozenset(f"main-{index:02d}" for index in range(1, 11))
EXPECTED_CELLS = frozenset((variant, task) for variant in EXPECTED_VARIANTS for task in EXPECTED_TASKS)
# Independently freeze assigned retrieval exposure for the confirmatory treatment
# CSV. Do not derive this from mutable input rows or later runner configuration.
FROZEN_SOURCE_BUDGETS = {"D3": 3, "D6": 6, "P6": 6, "P6V": 6}
# The common post-hoc evaluator was frozen to at most 12 claims per report.
# Pin this independently of the producer: correctly hashed aggregate CSVs can
# still contradict that measurement contract when supplied to offline analysis.
FROZEN_POSTHOC_CLAIM_CAP = 12
# A frozen cost-quality comparison must never silently treat a cost of unknown
# provenance as a comparable treatment estimate. This is the exact methodology
# label emitted by the preserved 40-cell study summarizer; it is NOT a claim of
# provider billing accuracy or independent pricing-source authentication.
FROZEN_TREATMENT_COST_STATUS = "estimated_from_frozen_uncached_rates"
FROZEN_PRICING_FILE = "experiments/openai_pricing_2026-09-08.json"
FROZEN_PRICING_FILE_BYTES = 1090
FROZEN_PRICING_FILE_SHA256 = "35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace"
FROZEN_PRICING_UNIT = "per_1m_text_tokens"


def _validate_csv_record(record: str, *, path: Path, line_number: int) -> None:
    """Reject lexically ambiguous CSV before ``csv`` can normalize it.

    Canonical study inputs deliberately use one record per physical line.  The
    standard-library reader is permissive about quotes inside unquoted fields
    and silently skips blank records, so validate those two cases explicitly.
    """
    if record.endswith("\r\n"):
        record = record[:-2]
    elif record.endswith(("\r", "\n")):
        record = record[:-1]
    if not record:
        raise ValueError(f"blank CSV record at line {line_number} in {path}")

    in_quotes = False
    at_field_start = True
    just_closed_quote = False
    index = 0
    while index < len(record):
        character = record[index]
        if in_quotes:
            if character == '"':
                if index + 1 < len(record) and record[index + 1] == '"':
                    index += 2
                    continue
                in_quotes = False
                just_closed_quote = True
            index += 1
            continue

        if just_closed_quote:
            if character != ",":
                raise ValueError(
                    f"malformed CSV in {path} at line {line_number}: "
                    "characters follow a closing quote"
                )
            just_closed_quote = False
            at_field_start = True
            index += 1
            continue

        if character == '"':
            if not at_field_start:
                raise ValueError(
                    f"malformed CSV in {path} at line {line_number}: "
                    "quote inside an unquoted field"
                )
            in_quotes = True
            at_field_start = False
        elif character == ",":
            at_field_start = True
        else:
            at_field_start = False
        index += 1

    if in_quotes:
        raise ValueError(
            f"malformed CSV in {path} at line {line_number}: unterminated quote"
        )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read one study CSV only when its table structure is unambiguous."""
    if not path.is_file():
        raise ValueError(f"missing required CSV: {path}")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line_number, record in enumerate(handle, start=1):
                _validate_csv_record(record, path=path, line_number=line_number)
            handle.seek(0)
            reader = csv.DictReader(handle, strict=True)
            headers = reader.fieldnames
            if not headers:
                raise ValueError(f"missing CSV header: {path}")
            if any(not str(header).strip() for header in headers):
                raise ValueError(f"blank CSV header in {path}")
            duplicates = sorted(
                {header for header in headers if headers.count(header) > 1}
            )
            if duplicates:
                raise ValueError(f"duplicate CSV header in {path}: {duplicates}")

            rows = []
            for row in reader:
                if None in row:
                    raise ValueError(
                        f"CSV row {reader.line_num} has too many fields in {path}"
                    )
                missing = sorted(header for header, value in row.items() if value is None)
                if missing:
                    raise ValueError(
                        f"CSV row {reader.line_num} has too few fields in {path}: {missing}"
                    )
                rows.append(row)
            return rows
    except csv.Error as exc:
        raise ValueError(f"malformed CSV in {path}: {exc}") from exc


def _rows(path: Path) -> list[dict[str, str]]:
    return read_csv_rows(path)


def _identity_keys(rows: list[dict[str, str]], *, label: str) -> set[tuple[str, str]] | None:
    """Return unique (variant, task) identities when the CSV exposes them.

    Small unit-level fixtures may intentionally omit identity columns. Canonical
    study CSVs contain both columns; if either is present, both become mandatory
    and every row must identify exactly one treatment cell.
    """
    if not rows:
        raise ValueError(f"{label} input contains no rows")
    has_identity = any(any(field in row for field in IDENTITY_FIELDS) for row in rows)
    if not has_identity:
        return None

    keys: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, start=2):
        variant = str(row.get("variant_id") or "").strip()
        task = str(row.get("task_id") or "").strip()
        if not variant or not task:
            raise ValueError(f"{label} row {index} has incomplete variant/task identity")
        key = (variant, task)
        if key in keys:
            raise ValueError(f"duplicate {label} treatment cell: {variant}/{task}")
        keys.add(key)
    return keys


def _validate_canonical_matrix(keys: set[tuple[str, str]], *, label: str) -> None:
    """Require exactly the preregistered 4 x 10 confirmatory study matrix."""
    if keys != EXPECTED_CELLS:
        missing = sorted(EXPECTED_CELLS - keys)
        unexpected = sorted(keys - EXPECTED_CELLS)
        raise ValueError(
            f"{label} does not match frozen 4x10 main-study matrix: "
            f"missing={missing}, unexpected={unexpected}"
        )



def _validate_canonical_evaluator_run_identity(
    support_rows: list[dict[str, str]],
) -> None:
    """Reject missing or shared report references in the frozen evaluator matrix.

    The common evaluator's run_id links a CSV cell to its treatment trace and
    report. Distinct (variant_id, task_id) values alone cannot detect two cells
    referring to the same run. This checks internal export consistency, not
    authenticity of the referenced traces or reports.
    """
    seen: dict[str, str] = {}
    for row in support_rows:
        cell = f"{row['variant_id']}/{row['task_id']}"
        run_id = row.get("run_id")
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or run_id != run_id.strip()
        ):
            raise ValueError(f"invalid evaluator run_id for {cell}: {run_id!r}")
        previous = seen.get(run_id)
        if previous is not None:
            raise ValueError(
                f"duplicate evaluator run_id {run_id!r} for {cell}; "
                f"already used by {previous}"
            )
        seen[run_id] = cell


def _validate_canonical_source_exposure(
    main_rows: list[dict[str, str]],
    support_rows: list[dict[str, str]],
) -> None:
    """Check that exported treatment exposure respects the frozen assignment.

    A completed run can legitimately stop before filling every retrieval slot,
    so attempted sources must not exceed the budget; equality is *not* required.
    The evidence-status cross-check prevents a zero-source report from being
    mislabeled as supported by retrieved evidence (or vice versa). Legacy
    recovered evaluator rows can have a blank positive-source status.
    These are consistency checks, not authentication of upstream traces.
    """
    support_by_cell = {
        (row["variant_id"], row["task_id"]): row for row in support_rows
    }
    for main in main_rows:
        variant, task = main["variant_id"], main["task_id"]
        label = f"{variant}/{task}"
        budget = require_nonnegative_integer(
            main.get("source_budget"), f"main {label} source_budget"
        )
        if budget != FROZEN_SOURCE_BUDGETS[variant]:
            raise ValueError(
                f"frozen source_budget mismatch for {label}: "
                f"expected {FROZEN_SOURCE_BUDGETS[variant]}, got {budget}"
            )
        successful = require_nonnegative_integer(
            main.get("successful_sources"), f"main {label} successful_sources"
        )
        failed = require_nonnegative_integer(
            main.get("failed_sources"), f"main {label} failed_sources"
        )
        if successful + failed > budget:
            raise ValueError(
                f"source counts exceed frozen source_budget for {label}: "
                f"successful={successful}, failed={failed}, budget={budget}"
            )
        support = support_by_cell[(variant, task)]
        if "evidence_status" not in support:
            raise ValueError(f"missing evaluator evidence_status for {label}")
        status = str(support["evidence_status"]).strip()
        if successful == 0:
            if status != "zero_successful_sources":
                raise ValueError(
                    f"evaluator evidence_status contradicts zero successful sources for {label}"
                )
            # The evaluator is restricted to evidence retrieved by this run.
            # Conservation was checked above: all claims must therefore be
            # unsupported; a zero-source sentinel supplies no evidence with
            # which to support, partially support, or contradict a claim.
            claims = require_nonnegative_integer(
                support.get("claims_checked"), f"support {label} claims_checked"
            )
            unsupported = require_nonnegative_integer(
                support.get("unsupported"), f"support {label} unsupported"
            )
            if unsupported != claims:
                raise ValueError(
                    f"zero-source evaluator must classify all claims unsupported for {label}"
                )
        elif status not in {"", "retrieved_evidence"}:
            raise ValueError(
                f"evaluator evidence_status contradicts successful sources for {label}: "
                f"{status!r}"
            )


def _validate_canonical_posthoc_mirrors(
    main_rows: list[dict[str, str]],
    support_rows: list[dict[str, str]],
) -> None:
    """Require both canonical exports to agree on the common evaluator's result.

    The treatment summary repeats the post-hoc claim count and strict-support
    rate. Merely checking equal treatment/task keys allows these two scientific
    records to contradict each other while preflight still reports success.
    Match by frozen cell identity, never CSV row position, and independently
    check the evaluator's claimed rate against its integer numerator and
    denominator. This does not authenticate either input's provenance.
    """
    main_by_cell = {
        (row["variant_id"], row["task_id"]): row for row in main_rows
    }
    support_by_cell = {
        (row["variant_id"], row["task_id"]): row for row in support_rows
    }
    for variant, task in sorted(EXPECTED_CELLS):
        label = f"{variant}/{task}"
        main = main_by_cell[(variant, task)]
        support = support_by_cell[(variant, task)]
        main_claims = require_nonnegative_integer(
            main.get("posthoc_claims_checked"),
            f"main {label} posthoc_claims_checked",
        )
        evaluator_claims = require_nonnegative_integer(
            support.get("claims_checked"),
            f"support {label} claims_checked",
        )
        if evaluator_claims > FROZEN_POSTHOC_CLAIM_CAP:
            raise ValueError(
                f"post-hoc claims exceed frozen claim cap for {label}: "
                f"claims_checked={evaluator_claims}, "
                f"max_claims={FROZEN_POSTHOC_CLAIM_CAP}"
            )
        if main_claims != evaluator_claims:
            raise ValueError(
                f"post-hoc claim count differs across canonical inputs for {label}"
            )

        require_unit_interval(
            support.get("strict_support_rate"),
            f"support {label} strict_support_rate",
        )
        require_unit_interval(
            main.get("posthoc_strict_support_rate"),
            f"main {label} posthoc_strict_support_rate",
        )
        supported = require_nonnegative_integer(
            support.get("supported"), f"support {label} supported"
        )
        # Rates are stored as decimal text. Check exact numeric identity
        # before any floating-point rounding can conceal discrepancies.
        evaluator_rate = Decimal(str(support["strict_support_rate"]).strip())
        main_rate = Decimal(str(main["posthoc_strict_support_rate"]).strip())
        # The canonical evaluator stores Python's floating-point numerator /
        # denominator result as repr text; bind to that exact encoded value.
        expected_rate = Decimal(str(supported / evaluator_claims))
        if evaluator_rate != expected_rate:
            raise ValueError(
                f"evaluator strict support rate contradicts counts for {label}"
            )
        if main_rate != evaluator_rate:
            raise ValueError(
                f"post-hoc strict support rate differs across canonical inputs for {label}"
            )



def _validate_canonical_completed_resource_evidence(
    main_rows: list[dict[str, str]],
    support_rows: list[dict[str, str]],
) -> None:
    """Reject zero-usage, zero-cost, or empty-report canonical measurements.

    Every preserved main-study treatment is a completed live model-generated
    report under a strictly positive frozen uncached pricing schedule. Every
    retained post-hoc cell contains actual evaluator classifications. A zero
    resource/elapsed/cost value in this *specific* 40-cell export would imply
    missing or incorrectly defaulted accounting and could distort the
    descriptive cost-quality frontier. Do not apply this constraint to generic
    fixtures, free-tier studies, or legitimately failed/empty executions.
    It checks export plausibility, not provider billing or source authenticity.
    """
    for row in main_rows:
        label = f"{row['variant_id']}/{row['task_id']}"
        for field in ("model_calls", "total_tokens", "report_words"):
            value = require_nonnegative_integer(
                row.get(field), f"main {label} {field}"
            )
            if value == 0:
                raise ValueError(
                    f"canonical completed treatment {field} must be positive for {label}"
                )
        for field in ("treatment_cost_usd", "latency_seconds"):
            value = require_nonnegative(row.get(field), f"main {label} {field}")
            if value == 0:
                raise ValueError(
                    f"canonical completed treatment {field} must be positive for {label}"
                )

    for row in support_rows:
        label = f"{row['variant_id']}/{row['task_id']}"
        tokens = require_nonnegative_integer(
            row.get("total_tokens"), f"support {label} total_tokens"
        )
        if tokens == 0:
            raise ValueError(
                f"canonical post-hoc evaluator total_tokens must be positive for {label}"
            )


def _validate_canonical_pricing_snapshot(main_rows: list[dict[str, str]]) -> None:
    """Bind exported treatment costs to the actual frozen pricing-file bytes.

    A manifest of rehashed canonical CSVs alone cannot tell whether their
    pricing-file identity was silently removed or relabeled. The fixed path,
    byte count, digest, and units come from the preserved dated study pricing
    artifact, independently of the input rows. This is source-byte identity,
    not independent authentication of rates or provider billing.
    """
    frozen_fields = {
        "pricing_file": FROZEN_PRICING_FILE,
        "pricing_file_sha256": FROZEN_PRICING_FILE_SHA256,
        "pricing_unit": FROZEN_PRICING_UNIT,
    }
    for row in main_rows:
        label = f"{row['variant_id']}/{row['task_id']}"
        for field, expected in frozen_fields.items():
            if row.get(field) != expected:
                raise ValueError(
                    f"frozen {field} mismatch for {label}: "
                    f"expected {expected!r}, got {row.get(field)!r}"
                )
        size = require_nonnegative_integer(
            row.get("pricing_file_size_bytes"),
            f"main {label} pricing_file_size_bytes",
        )
        if size != FROZEN_PRICING_FILE_BYTES:
            raise ValueError(
                f"frozen pricing_file_size_bytes mismatch for {label}: "
                f"expected {FROZEN_PRICING_FILE_BYTES}, got {size}"
            )


def _validate_canonical_treatment_cost_provenance(
    main_rows: list[dict[str, str]],
) -> None:
    """Require the frozen cost-estimation method before cost-quality inference.

    The producer records treatment cost estimates using frozen uncached prices.
    A valid CSV hash cannot justify treating missing or relabeled costs as
    comparable, even when the numeric amount remains unchanged. This checks
    the research export contract, not the underlying pricing or provider bill.
    """
    for row in main_rows:
        label = f"{row['variant_id']}/{row['task_id']}"
        status = row.get("cost_status")
        if status != FROZEN_TREATMENT_COST_STATUS:
            raise ValueError(
                f"treatment cost_status diverges from frozen pricing methodology "
                f"for {label}: expected {FROZEN_TREATMENT_COST_STATUS!r}, "
                f"got {status!r}"
            )


def _validate_canonical_evaluator_accounting(
    main_rows: list[dict[str, str]],
    support_rows: list[dict[str, str]],
) -> None:
    """Reconcile the common evaluator's measurement overhead across exports.

    Evaluator cost is research overhead, not treatment cost. Both canonical CSVs
    record this cost for each cell, but downstream analysis does not consume both
    copies. Verify exact decimal agreement and reject invalid evaluator token
    counts before these exports can support a manuscript-facing analysis. This
    guards export consistency, not correctness of the underlying pricing rates.
    """
    support_by_cell = {
        (row["variant_id"], row["task_id"]): row for row in support_rows
    }
    for main in main_rows:
        variant, task = main["variant_id"], main["task_id"]
        label = f"{variant}/{task}"
        if "completed" not in main:
            raise ValueError(f"missing canonical treatment completion flag for {label}")
        require_nonnegative_integer(
            main.get("search_calls"), f"main {label} search_calls"
        )
        support = support_by_cell[(variant, task)]
        require_nonnegative_integer(
            support.get("total_tokens"), f"support {label} total_tokens"
        )
        require_nonnegative(
            main.get("posthoc_evaluator_cost_usd"),
            f"main {label} posthoc_evaluator_cost_usd",
        )
        require_nonnegative(
            support.get("estimated_cost_usd"),
            f"support {label} estimated_cost_usd",
        )
        main_cost = Decimal(str(main["posthoc_evaluator_cost_usd"]).strip())
        support_cost = Decimal(str(support["estimated_cost_usd"]).strip())
        if main_cost != support_cost:
            raise ValueError(
                f"post-hoc evaluator cost differs across canonical inputs for {label}"
            )


def validate_rows(
    main_rows: list[dict[str, str]],
    support_rows: list[dict[str, str]],
    *,
    require_canonical_matrix: bool = False,
) -> None:
    """Validate scientific domains, identities, and evaluator conservation.

    ``require_canonical_matrix`` is enabled by the command-line preflight used for
    the real study. Tests and small reusable fixtures can leave it disabled while
    still exercising row-level invariants.
    """
    main_keys = _identity_keys(main_rows, label="treatment")
    support_keys = _identity_keys(support_rows, label="evaluator")
    if (main_keys is None) != (support_keys is None):
        raise ValueError("treatment/evaluator identity columns must be present in both inputs")
    if main_keys is not None and support_keys is not None:
        if main_keys != support_keys:
            missing_eval = sorted(main_keys - support_keys)
            orphan_eval = sorted(support_keys - main_keys)
            raise ValueError(
                "treatment/evaluator cell mismatch: "
                f"missing_evaluator={missing_eval}, orphan_evaluator={orphan_eval}"
            )
        if require_canonical_matrix:
            _validate_canonical_matrix(main_keys, label="treatment/evaluator inputs")
    elif require_canonical_matrix:
        raise ValueError("canonical main-study inputs must expose variant_id and task_id")

    for index, row in enumerate(main_rows, start=2):
        completed = row.get("completed")
        if completed is not None and str(completed).strip().lower() not in {"true", "1", "yes"}:
            raise ValueError(f"main row {index} is not a completed treatment")
        for field in INTEGER_MEASUREMENT_FIELDS:
            require_nonnegative_integer(row.get(field), f"main row {index} {field}")
        for field in CONTINUOUS_MEASUREMENT_FIELDS:
            require_nonnegative(row.get(field), f"main row {index} {field}")

    for index, row in enumerate(support_rows, start=2):
        counts = {
            field: require_nonnegative_integer(row.get(field), f"support row {index} {field}")
            for field in COUNT_FIELDS
        }
        if counts["claims_checked"] <= 0:
            raise ValueError(f"support row {index} claims_checked must be positive")
        classified = sum(counts[field] for field in COUNT_FIELDS if field != "claims_checked")
        if classified != counts["claims_checked"]:
            raise ValueError(
                f"support row {index} count mismatch: classified={classified}, "
                f"claims_checked={counts['claims_checked']}"
            )

    # Canonical study inputs redundantly publish evaluator measurements in
    # both CSVs; fail closed on inconsistencies instead of silently choosing
    # whichever file an analysis happens to read.
    if require_canonical_matrix:
        _validate_canonical_evaluator_run_identity(support_rows)
        _validate_canonical_completed_resource_evidence(main_rows, support_rows)
        _validate_canonical_source_exposure(main_rows, support_rows)
        _validate_canonical_posthoc_mirrors(main_rows, support_rows)
        _validate_canonical_pricing_snapshot(main_rows)
        _validate_canonical_treatment_cost_provenance(main_rows)
        _validate_canonical_evaluator_accounting(main_rows, support_rows)


def main() -> int:
    validate_rows(_rows(MAIN_CSV), _rows(SUPPORT_CSV), require_canonical_matrix=True)
    print("main-study identity/numeric/matrix preflight: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
