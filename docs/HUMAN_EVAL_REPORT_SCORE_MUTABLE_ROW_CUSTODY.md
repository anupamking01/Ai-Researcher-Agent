# Mutable streaming row custody for human report-level analysis

**Scope:** additive integrity hardening of direct/offline human report-score
aggregation. The frozen human rubric, assignments, analysis plan, statistics,
reliability measures, and measured main-study outcomes do not change.

## Distinct risk and impact

The pre-unblinding `build_agreement()` helper already snapshots generator
records. Its separate post-unblinding analysis counterpart,
`human_eval_analysis_core.report_scores(rows)`, previously collected
single-pass inputs using `list(islice(iterator, ...))`. A streaming producer
that reuses and mutates the same dictionary between yields would leave a list
of aliases pointing at the **final** submitted row. Earlier blind IDs, scores,
mandatory missingness explanations, or treatment-identifying columns could
therefore disappear before direct helper validation and aggregation.

The result could be a misleading duplicate error or, in otherwise aliased
input arrangements, loss of the original independent scoring evidence. Human
report-level means are inputs to complementary paired contrasts and must
reflect the records received from an iterator, not its final buffer state.

## Contract

The helper now shallow-snapshots each dictionary **immediately on yield**,
before advancing the single-pass iterator. It uses `dict.copy(row)`, bypassing
custom subclass `copy()` hooks. The strict frozen row validator still
requires only flat, immutable string-valued fields, so shallow capture is
sufficient. Non-dictionary inputs retain explicit rejection. Empty inputs,
identities, duplicate independent ratings, the 1–5 rubric, notes, and the
frozen 80-row maximum remain enforced exactly as before. The iterator is
consumed no further than the first excess record.

Already-corrupted lists of aliases, changes made before the helper receives
a record, and deliberately false source information cannot be repaired.

## Synthetic regression coverage

The accompanying test module compares independent rows with reused mutable
buffers; verifies distinct report IDs, earlier invalid scores, earlier
treatment-identity fields, and missing-score explanations survive; checks
caller input integrity and dictionary-subclass copy behavior; and preserves
the duplicate, non-dictionary, and resource-bound failure contracts.

These are engineering fixtures only. Production analysis independently
verifies the captured blinded freeze before it reads the coordinator mapping.
This change neither authenticates human raters nor produces annotations.

## Research-claim boundary

The canonical automated confirmatory results are frozen. Pilot findings remain
diagnostic; exploratory results and future complementary human validation must
be labeled separately. Genuine blinded annotations for all 40 reports,
inter-annotator agreement, and measured automated–human reconciliation are
still outstanding. No treatments, evaluator outputs, or human ratings were
regenerated or modified by this safeguard.
