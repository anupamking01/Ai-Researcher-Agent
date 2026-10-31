# Reused-buffer direct agreement input custody

**Scope:** additive pre-unblinding, offline diagnostic input-integrity safeguard.
The frozen rubric, human-evaluation protocol, statistical formulae, study
treatments, human scoring requirements, and confirmatory analysis are unchanged.

## Failure mode

`build_agreement(rows)` accepts single-pass Python iterators. Some producers
reuse a mutable dictionary buffer and update it before each `yield`. Collecting
these outputs with `list(iterator)` retains *references*, not records. If the
producer rewrites that buffer, earlier yielded ratings can disappear before
schema validation, duplicate/identity checks, or pairwise aggregation.

That can cause spurious duplicate-rating errors or mask the original location
of invalid/unblinding content. Neither is an acceptable independent-analysis
representation of what the iterator yielded.

## Exact behavior

The direct helper now snapshots each dictionary **as it is yielded**, before
advancing the input iterator. `dict.copy(row)` deliberately calls the
built-in copy method, not an overridable dictionary subclass method.
The frozen direct-row validator subsequently requires precisely the fixed
`RATING_FIELDS` schema and string values; the copy is sufficient for this
flat, immutable-value format. Non-dictionary records still fail with their
existing explicit error.

Capture remains single-pass and stops after at most
`MAX_DIRECT_AGREEMENT_ROWS + 1` values, preserving the existing empty,
invalid, and oversize failure contracts. This is a diagnostic input-custody
control, **not** a new inclusion threshold for legitimate frozen ratings.
Aliased records that were already overwritten *before* invoking the helper
cannot be recovered.

The production CSV freeze captures independently verified original source
bytes and is not affected. No human identities, annotations, ratings,
treatment outputs, or experimental measurements are created or modified.

## Synthetic regression coverage

`tests/test_human_eval_agreement_mutable_row_capture.py` checks
reused-buffer results against independently allocated rows; invalid earlier
scores and treatment-column leakage not disappearing after reuse; caller
input immutability; pre-collapsed aliases still rejected; subclass
`copy()` override bypass; one-past-the-bound termination; and non-dict
rejection. All records are synthetic engineering fixtures.

This safeguard does not authenticate raters, prove independent collection,
or establish genuine human-validation evidence. Blinded annotation of all
40 reports by eligible independent humans, observed agreement, and
automated–human reconciliation remain pending gates.
