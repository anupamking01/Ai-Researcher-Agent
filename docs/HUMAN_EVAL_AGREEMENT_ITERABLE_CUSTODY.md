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

## Generated-ID compatibility of synthetic agreement regression fixtures (20 November 2026)

The direct agreement and independent missingness-oracle regressions now use the
producer's legal opaque `H001`–`H999` namespace. In particular, the
single-rater diagnostic starts at `H001` rather than the invalid `H000`,
and the four missingness cases use valid IDs without altering score or
missingness expectations. The exact 4,096-row input-boundary regression uses
multiple synthetic rater pseudonyms because two raters cannot supply 4,096
distinct (rater, item) observations with at most 999 legal item IDs. Its
expected pairwise overlap and multi-rater-only diagnostic flag are checked
explicitly; it is **not** treated as a two-rater human-validity result.

These fixture repairs restore independent coverage of two preexisting
safeguards without relaxing the newer opaque-ID gate or changing the
estimator, frozen automated measurements, rubric, treatment assignments,
or human-evaluation evidence. All observations in these tests are synthetic.
The main-study automated analysis retains its post-collection-plan,
fixed-order, and evaluator-comparability limitations; pilot results remain
diagnostic and retrospective sensitivity work remains exploratory.
