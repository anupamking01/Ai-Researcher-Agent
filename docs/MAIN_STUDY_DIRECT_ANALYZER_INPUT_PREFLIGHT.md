# Frozen main-study analyzer: validated local diagnostic entrypoint

The historical analyzer `scripts/analyze_main_study.py` is **byte-pinned**
in the published canonical analysis provenance receipt. Editing it would break
independent verification of preserved results, so the original implementation
is intentionally retained byte-for-byte.

## Previously uncovered local misuse path

The historical command-line analyzer can also be invoked directly, outside
`scripts/run_verified_main_study_analysis.py`. In that unguarded mode its
permissive CSV parser and float-rounded claim counts can accept coherently
relabeled but scientifically invalid exports (for example, altered frozen task
IDs or browse budgets). That would yield numbers which look like preregistered
inference even though the canonical scientific contract was not satisfied.

## Optional local diagnostic command

```bash
python -m scripts.analyze_main_study_with_preflight
# Or, from the repository root:
python scripts/analyze_main_study_with_preflight.py
```

This **new** wrapper uses the existing strict canonical CSV reader and
`validate_rows(..., require_canonical_matrix=True)` on the exact in-memory
records that the byte-identical historical analyzer subsequently consumes.
It rejects malformed CSV structure, inconsistent evaluator mirrors, invalid
counts or resource measures, altered task identities, frozen budgets, claim
caps, pricing-source relabeling, and cost/accounting contradictions before
analysis output publication. No treatment, bootstrap rule, contrast, seed,
canonical result, or original pinned analyzer byte is changed.

A synthetic 40-cell control reproduces successful local inference; negative
regressions cover representative scientific contract violations and require
fail-closed behavior before result files appear.

## Critical provenance and research boundaries

This convenience command is **not** a manifest-pinned proof of canonical
artifact origin. It cannot authenticate the original input CSVs or protect
against every concurrent source-file edit while reading. It uses a temporary
module-level reader binding and should not be invoked concurrently from a
shared notebook/kernel. For manuscript-facing canonical inference **always
use the existing independently SHA-256-pinned verified runner**, which
snapshots and verifies the source artifacts and outputs.

The diagnostic pilot, frozen confirmatory study, post-hoc exploratory
analyses, and pending blinded human validation are separate. Synthetic tests
do not constitute experiments or human ratings.
