# Human-evaluation denominator lineage across the blinded boundary

This audit augments, rather than changes, the frozen human-analysis plan. No
new rating, treatment, hypothesis test, imputation rule or estimate is created.

## Gap

The result bundle independently displayed (a) pre-unblinding agreement
missingness, (b) post-unblinding original-rating coverage by task/contrast,
and (c) variant-level report and raw-score totals. Before this check, each
section could be internally well-formed yet contradict the others. For
example, 2/2 coverage for every task could coexist with a variant summary
claiming fewer original ratings, or agreement claiming absent observations.
Hash-bound independent recomputation is still required for source truth.

## Implemented preflight

The output verifier first checks each paired coverage partition and repeated
D6/P6 arm counts. It then reconstructs exactly one 0/1/2 original-rating count
per frozen task, treatment, and rubric dimension (without reading treatment
identity during the blinded agreement stage). For each treatment/dimension:

- total reports = number of frozen task IDs;
- reports scored = number of original-rating counts greater than zero;
- raw original scores = sum of 0/1/2 counts;
- score-distribution buckets 1 through 5 contain nonnegative integer counts
  summing exactly to that raw-score total.

For each dimension, the aggregate across all treatments must agree with the
already-frozen pre-unblinding pair:

- double-rated reports = number of post-unblinding counts equal to 2;
- neither-rated reports = number of counts equal to 0;
- A-only plus B-only reports = number of counts equal to 1;
- any recorded shared-item denominator equals the number of treatment/task cells.

This verifies count lineage, **not** identity of the specific annotator behind
a singleton (the 0/1/2 coverage representation cannot recover that information).
It does not equate the human 1–5 rubric with automated strict support.

## Boundaries and validation

All new test fixtures are synthetic and include deliberate denominator
contradictions, legitimate singly-rated and fully-missing rubric items, and
invalid raw-score distributions. The check runs in the offline output-identity
gate before accepting the deterministic manuscript rendering. Separate retained
frozen-rating recomputation is still necessary to prove correspondence to
source bytes and is not replaced by this count audit.

Human annotations remain uncollected; the automated confirmatory analysis is
frozen. Pilot, automated confirmatory, exploratory, and human validation
conclusions remain separate.
