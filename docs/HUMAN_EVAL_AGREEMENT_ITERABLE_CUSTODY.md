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

## Pairwise output fanout guard (20 November 2026)

The 4,096-row intake guard alone does not bound the work or size of the
pairwise result: 4,096 distinct one-item raters could cause 8,386,560
pairwise comparisons, each with five dimension summaries, despite valid
input cardinality. Direct `build_agreement` now rejects more than **64
distinct annotators** before generating any pairwise combinations (64 is
accepted, yielding at most 2,016 unordered pairs). This check is independent
of the existing row cap; exceeding it is an explicit error, never an
implicit subsample. Synthetic boundary tests exercise 64-rater success and
65-rater rejection before pairwise enumeration.

This is a resource/receipt-integrity limit for exploratory direct-helper
usage. It does **not** alter the frozen protocol's two-independent-rater
expectation, define an eligible multi-rater study, validate participant
eligibility, or establish any inter-annotator reliability from real humans.
Human ratings and original report/trace provenance remain outstanding.

## Pairwise report coverage denominators (20 November 2026)

Direct agreement receipts now disclose **item-level** pairwise coverage as
`n_union_items`, `n_items_only_annotator_a`, and
`n_items_only_annotator_b`, alongside the existing `n_shared_items`.
These counts are derived solely from blinded opaque item IDs. They expose
when two annotators share only a subset of their submitted reports, whereas
the existing dimension-specific `n_annotator_*_only_rated` and
`n_neither_rated` counters measure missing scores **within the shared
reports only**. The union identity is always the sum of the shared and
the two exclusive counts. No missing report is imputed as a score, and
pairwise agreement estimators and existing denominator fields are unchanged.

Synthetic list and one-pass tests cover partially overlapping assignments,
dimension missingness on a shared item, complete overlap, and zero overlap.
These are additive diagnostic receipt fields, not a declaration of
human-evaluation readiness: only the verified blinded freeze and assignment
coverage gate can certify protocol-complete annotation. In particular,
no genuine human rating or report/trace provenance is supplied or inferred.

## Independently supplied blind-item reference for direct agreement (20 November 2026)

A direct notebook call with only submitted ratings can measure overlap of
**submitted** report IDs, but cannot detect a report absent from **both**
raters' submissions. That gap matters when a high observed agreement is
calculated on a small, incomplete portion of the intended blinded packet.

The optional `build_agreement(rows, expected_blind_ids=...)` reference now
accepts an independently obtained, one-pass collection of opaque `H001`–
`H999` IDs. It validates the manifest **before consuming any ratings**:
empty, scalar, malformed, duplicate, and over-999-item inputs fail closed.
An observed rating for an undeclared ID is rejected before pairwise
computation. When supplied, each pairwise receipt additionally reports
`n_expected_items` and `n_items_missing_from_both`. The latter is the
expected set minus the union of that pair's submitted IDs; it is not a
missing score or an imputation. Existing union/exclusive counters and
rubric/kappa estimators remain unchanged. Without the optional reference,
the legacy receipt shape is preserved and **absence from both is unknown**.

These are diagnostics for independently supplied IDs, **not** cryptographic
authentication of their source. Deriving the reference from submitted rows
would defeat the check. For authoritative human-evaluation readiness, use
the source-verified coordinator packet and canonical blinded freeze,
eligibility/assignment attestations, independent human ratings, and
pre-unblinding protocol gates; no such ratings or original artifact custody
are established here. The pilot remains diagnostic, designated-primary
automated results remain post-collection-plan with fixed-order and
evaluator-policy comparability limitations, and retrospective sensitivity
analysis remains exploratory rather than prospectively confirmatory.
