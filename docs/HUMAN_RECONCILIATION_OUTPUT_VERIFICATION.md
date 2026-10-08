# Automated–human reconciliation output verification

Status: implementation complete before any real treatment-level human reconciliation is available; real human reconciliation remains pending.

This note defines the publication-integrity boundary for the frozen descriptive reconciliation. It does not change the automated confirmatory analysis, human-evaluation rubric, human-analysis plan, treatment outputs, or any measured result.

## Implemented publication contract

`scripts/reconcile_human_automated.py` publishes a create-only reconciliation bundle containing:

- `reconciliation.json` — the canonical machine-readable descriptive reconciliation;
- `reconciliation.md` — a deterministic manuscript-facing rendering derived from the canonical JSON;
- `reconciliation_manifest.json` — provenance binding for the published bundle.

Publication preflights the canonical payload, readiness-verified input fingerprints, producer Git commit SHA, and implementation fingerprints before reserving the output destination. The destination is then created exclusively; an existing published bundle is never overwritten.

The manifest binds, by exact path, SHA-256, and byte count:

- the canonical reconciliation JSON;
- the deterministic Markdown rendering;
- the exact reconciler implementation;
- the exact reconciliation-readiness implementation;
- the readiness gate's verified upstream input fingerprints;
- the full producing Git commit SHA.

This makes the published result auditable without treating manuscript text as a second source of truth.

## Independent verification

`scripts/verify_human_reconciliation_outputs.py` performs a read-only, offline verification of a saved bundle. It:

1. requires the expected canonical JSON, Markdown, and manifest to be regular files;
2. validates the frozen study identity, outcome, contrasts, dimensions, missingness rule, direction categories, and descriptive-only inference contract;
3. verifies artifact byte counts and SHA-256 fingerprints;
4. deterministically regenerates the manuscript Markdown from the canonical JSON and requires byte-for-byte equality;
5. verifies the recorded reconciler and readiness-gate implementation fingerprints against the current source;
6. checks that the canonical payload and manifest bind the same readiness-verified upstream fingerprints;
7. independently recomputes the frozen descriptive reconciliation from the verified automated and human analysis artifacts and requires exact canonical equality.

Verification fails closed on hand-edited manuscript results, source-fingerprint drift, implementation drift, contract drift, changed task identity, missing-pair imputation, removed frozen contrasts or dimensions, or post-unblinding additions that change the frozen result structure.

## Frozen scientific boundary

The reconciliation remains descriptive. It does not add reconciliation p-values, multiplicity procedures, correlations, composite scores, or treatment-validation thresholds. Automated strict support and human report quality remain different constructs, and pilot, automated-confirmatory, exploratory, and human-validation claims remain separate.

Missing human pairs remain missing; they are not imputed to improve coverage or directional concordance.

Previously archived reconciliation bundles must not be overwritten. A legitimate source, contract, or implementation change requires a new versioned result while retaining the earlier bytes for auditability.

## Verification command

After a legitimate reconciliation bundle exists, verify it offline with:

```bash
python scripts/verify_human_reconciliation_outputs.py \
  --output-root outputs/human_eval/reconciliation-v1
```

The verifier does not rerun treatments, common evaluation, or human rating generation.

## Current research gate

This implementation does **not** create a human-evaluation result. Real blinded annotations, pre-unblinding agreement, the frozen human analysis, and the resulting descriptive automated–human reconciliation remain pending scientific gates. No human-validation claim should be made until those measured artifacts exist and pass their respective verification gates.
