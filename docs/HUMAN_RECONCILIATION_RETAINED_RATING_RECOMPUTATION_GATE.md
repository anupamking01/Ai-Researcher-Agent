# Require positive retained-rating recomputation before reconciliation

The frozen VERA human/automated reconciliation is **descriptive** and must
recompute the human analysis independently from the retained, blinded rating
archive before it can emit a readiness receipt. This is separate from the
frozen automated confirmatory analysis.

## Previously possible inconsistent claim

`verify_human_reconciliation_readiness.verify_readiness` called the upstream
human-analysis verifier, then unconditionally stamped
`human_analysis_bundle_verified: true`, while forwarding
`human_analysis_independently_recomputed: false` if that verifier returned its
ordinary metadata-only receipt. The downstream reconciler and publisher did
not use that negative flag as a blocking condition. A future refactor or
partial upstream verification could thus label a published reconciliation
`verified` without positive independent human recomputation evidence.

## Fail-closed contract

Before constructing any readiness receipt, require the upstream verification
result to be a dictionary with **literal JSON/Python `True`** for all three:

- `independent_recomputation_verified`: canonical human analysis agrees with
  the independently recomputed result;
- `recomputed_from_retained_ratings`: recomputation uses the retained frozen
  blinded archive rather than external, newly supplied ratings;
- `outputs_stable_during_independent_recomputation`: output snapshot custody
  was observed through recomputation.

Missing fields, `False`, `None`, truthy integers (including `1`), and
non-mapping upstream receipts all reject **before** the readiness result can
flow into `reconcile_verified`. The established input/manifest fingerprint
checks and output custody checks remain in force. Accepted readiness receipts
now expose all three positive attestations without changing paired effects,
reconciliation categories, sample eligibility, or inferential rules.

Synthetic offline regressions are in
`tests/test_human_reconciliation_readiness.py`. They test positive control,
missing/negative/type-coerced assertions, and non-mapping receipts. These are
contract tests, not human-evaluation outcomes or evidence that annotators have
submitted ratings.

This is a fail-closed *control-flow* check, not cryptographic authentication of
an annotator's identity or a guarantee against a compromised verifier; source
and frozen archive authenticity continue to require independent provenance
verification. No treatments, automated evaluator, pilot or confirmatory
outputs, or human ratings are generated or modified by this change.
