import pytest

from scripts.validate_main_study_inputs import (
    EXPECTED_CELLS,
    FROZEN_SOURCE_BUDGETS,
    read_csv_rows,
    validate_rows,
)


def _main_row(**overrides):
    row = {
        "successful_sources": "3",
        "total_tokens": "1200",
        "treatment_cost_usd": "0.04",
        "latency_seconds": "12.5",
        "model_calls": "2",
        "report_words": "500",
    }
    row.update(overrides)
    return row


def _support_row(**overrides):
    row = {
        "claims_checked": "4",
        "supported": "2",
        "partially_supported": "1",
        "unsupported": "1",
        "contradicted": "0",
    }
    row.update(overrides)
    return row


def test_preflight_accepts_well_formed_rows():
    validate_rows([_main_row()], [_support_row()])


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("variant_id,task_id,task_id\nD3,main-01,shadow\n", "duplicate CSV header"),
        ("variant_id,,task_id\nD3,ignored,main-01\n", "blank CSV header"),
        ("variant_id,task_id\nD3,main-01,extra\n", "too many fields"),
        ("variant_id,task_id\nD3\n", "too few fields"),
        ('variant_id,task_id\nD3,"unterminated\n', "malformed CSV"),
        ('variant_id,task_id\nD3,main-"01\n', "malformed CSV"),
        ("variant_id,task_id\nD3,main-01\n\nD6,main-02\n", "blank CSV record"),
    ],
)
def test_preflight_csv_reader_rejects_ambiguous_structure(tmp_path, contents, message):
    path = tmp_path / "study.csv"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        read_csv_rows(path)


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-1"])
def test_preflight_rejects_invalid_measurements(value):
    with pytest.raises(ValueError):
        validate_rows([_main_row(latency_seconds=value)], [_support_row()])


@pytest.mark.parametrize("field", ["successful_sources", "total_tokens", "model_calls", "report_words"])
def test_preflight_rejects_fractional_count_measurements(field):
    with pytest.raises(ValueError):
        validate_rows([_main_row(**{field: "3.6"})], [_support_row()])


@pytest.mark.parametrize("value", ["3.6", "nan", "inf", "-1"])
def test_preflight_rejects_malformed_scientific_counts(value):
    with pytest.raises(ValueError):
        validate_rows([_main_row()], [_support_row(supported=value)])


def test_preflight_rejects_nonconserving_evaluator_counts():
    with pytest.raises(ValueError, match="count mismatch"):
        validate_rows([_main_row()], [_support_row(supported="3")])


def test_preflight_requires_positive_claim_denominator():
    with pytest.raises(ValueError, match="must be positive"):
        validate_rows(
            [_main_row()],
            [_support_row(claims_checked="0", supported="0", partially_supported="0", unsupported="0")],
        )


def test_preflight_accepts_matching_cross_file_identities():
    validate_rows(
        [_main_row(variant_id="D3", task_id="main-01", completed="True")],
        [_support_row(variant_id="D3", task_id="main-01")],
    )


def test_preflight_rejects_duplicate_treatment_cells():
    rows = [
        _main_row(variant_id="D3", task_id="main-01", completed="True"),
        _main_row(variant_id="D3", task_id="main-01", completed="True"),
    ]
    with pytest.raises(ValueError, match="duplicate treatment treatment cell"):
        validate_rows(rows, [_support_row(variant_id="D3", task_id="main-01")])


def test_preflight_rejects_cross_file_cell_mismatch():
    with pytest.raises(ValueError, match="treatment/evaluator cell mismatch"):
        validate_rows(
            [_main_row(variant_id="D3", task_id="main-01", completed="True")],
            [_support_row(variant_id="D6", task_id="main-01")],
        )


def test_preflight_rejects_incomplete_treatment_before_inference():
    with pytest.raises(ValueError, match="not a completed treatment"):
        validate_rows(
            [_main_row(variant_id="D3", task_id="main-01", completed="False")],
            [_support_row(variant_id="D3", task_id="main-01")],
        )


def test_preflight_requires_identity_columns_on_both_inputs():
    with pytest.raises(ValueError, match="identity columns must be present in both"):
        validate_rows(
            [_main_row(variant_id="D3", task_id="main-01", completed="True")],
            [_support_row()],
        )


def _canonical_rows():
    main_rows = []
    support_rows = []
    for variant, task in sorted(EXPECTED_CELLS):
        main_rows.append(_main_row(
            variant_id=variant, task_id=task, completed="True",
            source_budget=str(FROZEN_SOURCE_BUDGETS[variant]), failed_sources="0",
            posthoc_claims_checked="4", posthoc_strict_support_rate="0.5",
            search_calls="1", posthoc_evaluator_cost_usd="0.0125",
            cost_status="estimated_from_frozen_uncached_rates",
        ))
        support_rows.append(_support_row(
            variant_id=variant, task_id=task, strict_support_rate="0.5",
            evidence_status="", total_tokens="200", estimated_cost_usd="0.0125",
            run_id=f"synthetic-run-{variant}-{task}",
        ))
    return main_rows, support_rows


def test_canonical_preflight_accepts_exact_frozen_4x10_matrix():
    main_rows, support_rows = _canonical_rows()
    validate_rows(main_rows, support_rows, require_canonical_matrix=True)


def test_canonical_preflight_rejects_missing_preregistered_cell():
    main_rows, support_rows = _canonical_rows()
    main_rows.pop()
    support_rows.pop()
    with pytest.raises(ValueError, match="frozen 4x10 main-study matrix"):
        validate_rows(main_rows, support_rows, require_canonical_matrix=True)


def test_canonical_preflight_rejects_unexpected_variant_even_when_files_match():
    main_rows, support_rows = _canonical_rows()
    main_rows[-1]["variant_id"] = "P12"
    support_rows[-1]["variant_id"] = "P12"
    with pytest.raises(ValueError, match="unexpected"):
        validate_rows(main_rows, support_rows, require_canonical_matrix=True)

def test_preflight_detects_large_count_conservation_error_without_float_rounding():
    # The previous float->int parser rounded 2**53 + 1 down to 2**53,
    # hiding this one-claim discrepancy as a falsely conserving row.
    with pytest.raises(ValueError, match="count mismatch"):
        validate_rows(
            [_main_row()],
            [_support_row(
                claims_checked="9007199254740993",
                supported="9007199254740992",
                partially_supported="0",
                unsupported="0",
                contradicted="0",
            )],
        )



def test_canonical_preflight_matches_mirrors_by_identity_not_csv_order():
    main, support = _canonical_rows()
    support.reverse()
    validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_rejects_conflicting_repeated_claim_count():
    main, support = _canonical_rows()
    main[0]["posthoc_claims_checked"] = "5"
    with pytest.raises(ValueError, match="post-hoc claim count differs"):
        validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_rejects_conflicting_repeated_support_rate():
    main, support = _canonical_rows()
    main[0]["posthoc_strict_support_rate"] = "0.75"
    with pytest.raises(ValueError, match="post-hoc strict support rate differs"):
        validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_rejects_shared_incorrect_support_rate():
    # Changing BOTH copies must not make a wrong scientific measurement valid.
    main, support = _canonical_rows()
    main[0]["posthoc_strict_support_rate"] = "0.75"
    support[0]["strict_support_rate"] = "0.75"
    with pytest.raises(ValueError, match="evaluator strict support rate contradicts counts"):
        validate_rows(main, support, require_canonical_matrix=True)


@pytest.mark.parametrize("missing", ["posthoc_claims_checked", "posthoc_strict_support_rate"])
def test_canonical_preflight_requires_mirrored_treatment_field(missing):
    main, support = _canonical_rows()
    del main[0][missing]
    with pytest.raises(ValueError, match=missing):
        validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_requires_evaluator_rate():
    main, support = _canonical_rows()
    del support[0]["strict_support_rate"]
    with pytest.raises(ValueError, match="strict_support_rate"):
        validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_rejects_rate_rounded_back_inside_unit_interval():
    main, support = _canonical_rows()
    main[0]["posthoc_strict_support_rate"] = "1.0000000000000001"
    with pytest.raises(ValueError, match="outside"):
        validate_rows(main, support, require_canonical_matrix=True)



@pytest.mark.parametrize("location", ["treatment", "evaluator", "both"])
def test_canonical_preflight_rejects_rate_rounding_equivalence(location):
    # float('0.50000000000000001') equals 0.5, but the persisted
    # measurement is not the canonical numerator / denominator result.
    main, support = _canonical_rows()
    if location in {"treatment", "both"}:
        main[0]["posthoc_strict_support_rate"] = "0.50000000000000001"
    if location in {"evaluator", "both"}:
        support[0]["strict_support_rate"] = "0.50000000000000001"
    with pytest.raises(ValueError, match="rate differs|rate contradicts"):
        validate_rows(main, support, require_canonical_matrix=True)


def _canonical_cell(rows, variant="P6V", task="main-10"):
    return next(row for row in rows if row["variant_id"] == variant and row["task_id"] == task)


@pytest.mark.parametrize(
    ("variant", "wrong_budget"),
    [("D3", "6"), ("D6", "3"), ("P6", "3"), ("P6V", "3")],
)
def test_canonical_preflight_rejects_treatment_assignment_budget_drift(
    variant, wrong_budget
):
    main, support = _canonical_rows()
    _canonical_cell(main, variant)["source_budget"] = wrong_budget
    with pytest.raises(ValueError, match="frozen source_budget mismatch"):
        validate_rows(main, support, require_canonical_matrix=True)


@pytest.mark.parametrize("field", ["source_budget", "failed_sources"])
def test_canonical_preflight_requires_source_exposure_fields(field):
    main, support = _canonical_rows()
    del _canonical_cell(main)[field]
    with pytest.raises(ValueError, match=field):
        validate_rows(main, support, require_canonical_matrix=True)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("source_budget", "6.0000000000000001"),
        ("failed_sources", "0.0000000000000001"),
        ("failed_sources", "-1"),
    ],
)
def test_canonical_preflight_does_not_round_source_exposure(field, invalid):
    main, support = _canonical_rows()
    _canonical_cell(main)[field] = invalid
    with pytest.raises(ValueError, match=f"{field}|negative"):
        validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_rejects_source_counts_over_scheduled_budget():
    main, support = _canonical_rows()
    _canonical_cell(main)["successful_sources"] = "5"
    _canonical_cell(main)["failed_sources"] = "2"
    with pytest.raises(ValueError, match="source counts exceed frozen source_budget"):
        validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_allows_completed_run_with_unused_browse_slots():
    main, support = _canonical_rows()
    # An interrupted/superseded browse schedule can use fewer than six slots
    # without implying an incomplete treatment or a stronger result.
    _canonical_cell(main)["successful_sources"] = "1"
    _canonical_cell(main)["failed_sources"] = "3"
    _canonical_cell(support)["evidence_status"] = "retrieved_evidence"
    validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_allows_zero_source_sentinel_with_matching_counts():
    main, support = _canonical_rows()
    _canonical_cell(main)["successful_sources"] = "0"
    _canonical_cell(main)["failed_sources"] = "4"
    _canonical_cell(main)["posthoc_strict_support_rate"] = "0"
    evaluator = _canonical_cell(support)
    evaluator.update(
        evidence_status="zero_successful_sources",
        strict_support_rate="0",
        supported="0",
        partially_supported="0",
        unsupported="4",
    )
    validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_rejects_missing_zero_source_sentinel():
    main, support = _canonical_rows()
    _canonical_cell(main)["successful_sources"] = "0"
    with pytest.raises(ValueError, match="evidence_status contradicts zero successful"):
        validate_rows(main, support, require_canonical_matrix=True)


@pytest.mark.parametrize("invalid_status", ["zero_successful_sources", "invented_evidence"])
def test_canonical_preflight_rejects_false_evidence_status_on_positive_sources(invalid_status):
    main, support = _canonical_rows()
    _canonical_cell(support)["evidence_status"] = invalid_status
    with pytest.raises(ValueError, match="evidence_status contradicts successful"):
        validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_requires_evidence_status_field():
    main, support = _canonical_rows()
    del _canonical_cell(support)["evidence_status"]
    with pytest.raises(ValueError, match="missing evaluator evidence_status"):
        validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_accepts_exact_measurement_overhead_after_row_shuffle():
    main, support = _canonical_rows()
    support.reverse()
    _canonical_cell(main)["posthoc_evaluator_cost_usd"] = "0.0"
    _canonical_cell(support)["estimated_cost_usd"] = "0"
    validate_rows(main, support, require_canonical_matrix=True)


@pytest.mark.parametrize(
    ("side", "field"),
    [
        ("main", "completed"),
        ("main", "search_calls"),
        ("main", "posthoc_evaluator_cost_usd"),
        ("support", "total_tokens"),
        ("support", "estimated_cost_usd"),
    ],
)
def test_canonical_preflight_requires_evaluator_accounting_fields(side, field):
    main, support = _canonical_rows()
    row = _canonical_cell(main if side == "main" else support)
    del row[field]
    with pytest.raises(ValueError, match=field if field != "completed" else "completion flag"):
        validate_rows(main, support, require_canonical_matrix=True)


@pytest.mark.parametrize(
    ("side", "field", "value"),
    [
        ("main", "search_calls", "-1"),
        ("main", "search_calls", "1.0000000000000001"),
        ("support", "total_tokens", "-1"),
        ("support", "total_tokens", "200.00000000000001"),
        ("main", "posthoc_evaluator_cost_usd", "-0.01"),
        ("main", "posthoc_evaluator_cost_usd", "nan"),
        ("support", "estimated_cost_usd", "-0.01"),
        ("support", "estimated_cost_usd", "inf"),
    ],
)
def test_canonical_preflight_rejects_invalid_evaluator_overhead(side, field, value):
    main, support = _canonical_rows()
    _canonical_cell(main if side == "main" else support)[field] = value
    with pytest.raises(ValueError, match=field):
        validate_rows(main, support, require_canonical_matrix=True)


@pytest.mark.parametrize("side", ["main", "support"])
def test_canonical_preflight_rejects_evaluator_cost_disagreement(side):
    main, support = _canonical_rows()
    if side == "main":
        _canonical_cell(main)["posthoc_evaluator_cost_usd"] = "0.013"
    else:
        _canonical_cell(support)["estimated_cost_usd"] = "0.013"
    with pytest.raises(ValueError, match="post-hoc evaluator cost differs"):
        validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_rejects_float_roundable_cost_mirror_drift():
    main, support = _canonical_rows()
    _canonical_cell(main)["posthoc_evaluator_cost_usd"] = "0.012500000000000001"
    with pytest.raises(ValueError, match="post-hoc evaluator cost differs"):
        validate_rows(main, support, require_canonical_matrix=True)



def test_canonical_preflight_accepts_frozen_posthoc_claim_cap_boundary():
    # An exactly 12-claim measurement is allowed by the frozen evaluator.
    main, support = _canonical_rows()
    main[0].update(
        posthoc_claims_checked="12",
        posthoc_strict_support_rate="1.0",
    )
    support[0].update(
        claims_checked="12",
        supported="12",
        partially_supported="0",
        unsupported="0",
        contradicted="0",
        strict_support_rate="1.0",
    )
    validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_rejects_agreeing_mirrors_above_frozen_claim_cap():
    # Both exports conserve 13 classifications and agree on the support rate.
    # No cross-file mismatch catches this violation without an independent cap.
    main, support = _canonical_rows()
    main[0].update(
        posthoc_claims_checked="13",
        posthoc_strict_support_rate="1.0",
    )
    support[0].update(
        claims_checked="13",
        supported="13",
        partially_supported="0",
        unsupported="0",
        contradicted="0",
        strict_support_rate="1.0",
    )
    with pytest.raises(ValueError, match="frozen claim cap"):
        validate_rows(main, support, require_canonical_matrix=True)



@pytest.mark.parametrize(
    "invalid_cost_status",
    [
        None,
        "",
        "provider_billed",
        "estimated_from_frozen_cached_rates",
        "estimated_from_frozen_uncached_rates ",
        "Estimated_from_frozen_uncached_rates",
    ],
)
def test_canonical_preflight_rejects_unsupported_cost_provenance(invalid_cost_status):
    # A newly fingerprinted CSV can retain identical numeric treatment costs
    # while removing or changing the methodological basis for cost comparisons.
    main, support = _canonical_rows()
    row = _canonical_cell(main)
    if invalid_cost_status is None:
        del row["cost_status"]
    else:
        row["cost_status"] = invalid_cost_status
    with pytest.raises(ValueError, match="treatment cost_status diverges"):
        validate_rows(main, support, require_canonical_matrix=True)


def test_noncanonical_small_fixture_remains_independent_of_frozen_cost_label():
    # Unit fixtures outside the preregistered 40-cell matrix remain reusable.
    validate_rows([_main_row()], [_support_row()])


@pytest.mark.parametrize(
    "field",
    ("model_calls", "total_tokens", "report_words", "treatment_cost_usd", "latency_seconds"),
)
def test_canonical_preflight_rejects_zero_completed_treatment_resources(field):
    # Completed frozen live runs cannot contribute cost/quality data with
    # missing usage, empty reports, zero duration, or zero frozen-rate cost.
    main, support = _canonical_rows()
    _canonical_cell(main)[field] = "0"
    with pytest.raises(ValueError, match=f"canonical completed treatment {field} must be positive"):
        validate_rows(main, support, require_canonical_matrix=True)


def test_canonical_preflight_rejects_zero_token_posthoc_measurement():
    main, support = _canonical_rows()
    _canonical_cell(support)["total_tokens"] = "0"
    with pytest.raises(ValueError, match="canonical post-hoc evaluator total_tokens must be positive"):
        validate_rows(main, support, require_canonical_matrix=True)


def test_small_noncanonical_zero_usage_control_remains_valid():
    # Do not turn a frozen-study assumption into a universal pricing policy.
    validate_rows(
        [_main_row(
            total_tokens="0", model_calls="0", report_words="0",
            treatment_cost_usd="0", latency_seconds="0",
        )],
        [_support_row(total_tokens="0", estimated_cost_usd="0")],
    )



def test_canonical_preflight_rejects_shared_evaluator_report_reference():
    # Distinct treatment/task cells must not reuse one evaluated report.
    main, support = _canonical_rows()
    support[1]["run_id"] = support[0]["run_id"]
    with pytest.raises(ValueError, match="duplicate evaluator run_id"):
        validate_rows(main, support, require_canonical_matrix=True)


@pytest.mark.parametrize("bad_id", [None, "", "  ", " leading", "trailing "])
def test_canonical_preflight_rejects_invalid_evaluator_report_reference(bad_id):
    main, support = _canonical_rows()
    if bad_id is None:
        del support[0]["run_id"]
    else:
        support[0]["run_id"] = bad_id
    with pytest.raises(ValueError, match="invalid evaluator run_id"):
        validate_rows(main, support, require_canonical_matrix=True)


@pytest.mark.parametrize("false_label", ["supported", "partially_supported", "contradicted"])
def test_canonical_preflight_rejects_positive_evidence_labels_from_zero_sources(false_label):
    # Both aggregate CSVs may be coherently updated, fingerprinted and still
    # claim evidence support in a run where no evidence was retrieved.
    main, support = _canonical_rows()
    treatment = _canonical_cell(main)
    evaluation = _canonical_cell(support)
    treatment["successful_sources"] = "0"
    evaluation.update(
        evidence_status="zero_successful_sources",
        supported="0",
        partially_supported="0",
        unsupported="3",
        contradicted="0",
        strict_support_rate="0",
    )
    evaluation[false_label] = "1"
    if false_label == "supported":
        treatment["posthoc_strict_support_rate"] = "0.25"
        evaluation["strict_support_rate"] = "0.25"

    with pytest.raises(ValueError, match="zero-source evaluator must classify all claims unsupported"):
        validate_rows(main, support, require_canonical_matrix=True)
