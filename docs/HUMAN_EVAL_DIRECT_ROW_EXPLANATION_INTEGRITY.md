# Direct human-rating aggregation: full-row and explanation integrity

This change extends the **direct-call** guard in `human_eval_analysis_core.report_scores`.
The ordinary human-analysis pipeline already loads a verified blinded ratings
freeze through the strict CSV importer; direct research-notebook callers could
previously bypass the importer's complete-row and notes rules.

## Failure and boundary

A mapping with a missing rubric dimension previously became an apparently
legitimate blank score because `_score` reads missing fields as `None`.
A direct row could also carry `variant_id` or untrimmed pseudonyms, or
supply an endpoint score or blank dimension without the required explanation.
Such rows should not silently contribute to treatment-level human summaries.

The direct aggregator now requires **exactly** the frozen
`freeze_human_eval_ratings.RATING_FIELDS` columns, all values as text,
trimmed rater and blind IDs, and the same 1–5/blank parser. It rejects
missing/extra columns; checks note text with the existing spreadsheet,
treatment-blinding and visible-explanation validators; and requires a
visible reason for **every row** containing an endpoint (1 or 5) or
unscored dimension. The rule remains row-wide, as specified by the frozen
rubric, not a new condition on numerical outcomes.

## Scope and reproducibility

The new checks apply only to direct aggregation inputs; verified and normalized
freeze rows already satisfy them. Legitimate intermediate ratings without
notes, independently explained endpoints, and explained missing dimensions
retain their frozen arithmetic-mean aggregation. No statistical method,
rubric, hypothesis family, frozen data, treatment outputs, or human scores
are changed. Synthetic tests cover missing dimensions, forbidden extra
columns, identifier whitespace, invalid notes, and valid explained
missingness. These tests **do not constitute human annotation evidence**.

The helper still does not establish eligible human identity, full 40-item
coverage, actual independence, consent, or input provenance. The full
pre-unblinding freeze and independent verification remain mandatory before
any actual treatment-level human analysis.

## Minimum rendered-language explanation check (prospective gate)

A rendered Unicode numeral or symbol is not, on its own, a written reason
for an endpoint (1/5) or missing rating. Previously the shared
`_note_has_visible_explanation` predicate accepted rendered Unicode
categories **L**, **N**, or **S**. That let bare entries such as `5/5`,
`12345`, or `★` satisfy the *explanation* requirement while adding no
linguistic rationale. The predicate now requires **at least one rendered
Unicode letter** (category L), including letters from non-Latin scripts;
numbers and symbols can still appear alongside actual words. It continues
to reject Markdown-only or invisible explanations without rewriting
annotator text. The change propagates to CSV freeze, direct blinded
agreement, and direct analysis through their shared validator. Synthetic
regressions test both rejection and multilingual acceptance.

This is a *minimum syntactic gate*, not an NLP assessment that notes are
factually correct, sufficiently specific, independently produced, or genuine
human testimony. It does not revise the frozen rubric/estimand, authenticate
original treatment reports, generate ratings, or authorize unblinding.
Human collection and the source-to-report custody gate remain pending.
