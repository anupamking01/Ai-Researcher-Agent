# Direct pre-unblinding agreement: one-pass evidence capture

Status: synthetic engineering safeguard; no real human ratings collected.

The canonical VERA pipeline reads verified normalized ratings from a blinded
freeze before computing agreement. Researchers may also call
`freeze_human_eval_ratings.build_agreement(rows)` in an offline notebook.

## Integrity gap

Previously the helper traversed `rows` for schema validation and identity
validation before a third traversal for aggregation. A generator is exhausted
by the first traversal, so valid submitted rows could silently yield
`n_annotators: 0` and an empty `pairwise` array. This is a direct
**pre-unblinding agreement** risk, distinct from the previously protected
post-unblinding `report_scores` helper.

## Contract

The helper now acquires an iterator once and captures at most 4,097 records:
- Empty/noniterable input fails closed, rather than appearing as zero agreement.
- More than 4,096 records fails before unbounded materialization or processing.
- Exactly 4,096 records remains valid as a resource-bound input, subject to
  existing schema, pseudonym, score, duplicate, and note checks.
- One-shot generators, lists, and iterators produce identical diagnostics.
- With more than two annotators, existing pairwise figures remain **diagnostic**
  and require a separately predeclared ordinal multi-rater statistic before
  treatment-level analysis.

The 4,096-record ceiling is a direct-helper resource guard, **not** a change
to the 40-report study matrix, frozen assignment, eligibility requirements,
sample-size estimand, or multi-rater policy. The canonical CSV importer and
freeze remain authoritative. A successful helper return does **not** establish
that the 40 reports were rated independently, that raters are real or eligible,
that ratings are frozen, or that unblinding is permitted.

No treatments, post-hoc evaluation, paired confirmatory analysis, rubric, or
historical observations are changed by this engineering safeguard.
