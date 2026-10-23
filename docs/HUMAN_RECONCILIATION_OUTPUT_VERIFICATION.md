# Automated–human reconciliation output verification

Status: implementation complete before any real treatment-level human reconciliation is available; real human reconciliation remains pending.

This note defines the publication-integrity boundary for the frozen descriptive reconciliation. It does not change the automated confirmatory analysis, human-evaluation rubric, human-analysis plan, treatment outputs, or any measured result.

## Implemented publication contract

`scripts/reconcile_human_automated.py` publishes a create-only reconciliation bundle containing:

- `reconciliation.json` — the canonical machine-readable descriptive reconciliation;
- `reconciliation.md` — a deterministic manuscript-facing rendering derived from the canonical JSON;
- `reconciliation_manifest.json` — provenance binding for the published bundle.

Publication preflights the canonical payload, readiness-verified input fingerprints, producer Git commit SHA, and implementation fingerprints before reserving the output destination. The canonical payload is serialized as strict JSON: non-finite numeric values (NaN, Infinity, or negative Infinity) are rejected before publication, while genuine missing measurements remain JSON null. The destination is then created exclusively; an existing published bundle is never overwritten.

The manifest binds, by exact path, SHA-256, and byte count:

- the canonical reconciliation JSON;
- the deterministic Markdown rendering;
- the exact reconciler implementation;
- the exact reconciliation-readiness implementation;
- the exact reconciliation output verifier and all repository-local
  implementation modules transitively invoked by the readiness gate, including
  retained-freeze submission preflights;
- the pinned application requirements, CI requirements, Python version file,
  and actual analysis runtime;
- the readiness gate's verified upstream input fingerprints;
- the full producing Git commit SHA.

This makes the published result auditable without treating manuscript text as a second source of truth.

Before opening any human-analysis artifact, the readiness gate requires
`paper/HUMAN_RECONCILIATION_FREEZE.md` to match its preregistered repository
SHA-256 anchor exactly. The contract's runtime fingerprint is still retained
among the verified inputs, but a newly substituted document cannot become the
governing contract merely by being fingerprinted alongside the results.

## Independent verification

`scripts/verify_human_reconciliation_outputs.py` performs a read-only, offline verification of a saved bundle. It:

1. rejects a non-regular expected artifact by metadata before any read-open, then opens the canonical JSON, Markdown, and manifest through retained non-symlink, nonblocking descriptors with post-open type and identity checks; this keeps an already-substituted FIFO/device out of the read-open path, while the descriptor checks fail closed on open-time replacement races. It also rejects duplicate JSON members recursively (including Unicode-escape-equivalent names) and non-finite numbers (including overflowed JSON exponents such as 1e400) when loading either JSON artifact;
2. validates the frozen study identity, outcome, contrasts, dimensions, missingness rule, direction categories, and descriptive-only inference contract;
3. verifies artifact byte counts and SHA-256 fingerprints;
4. deterministically regenerates the manuscript Markdown from the canonical JSON and requires byte-for-byte equality;
5. captures the reconciler, readiness gate, reconciliation verifier, the complete
   16-module repository-local implementation closure used by readiness, and pinned
   environment files through retained non-symlink descriptors before trusting
   their fingerprints, then revalidates the same inodes, bytes, and pathname
   bindings after recomputation;
6. verifies every recorded direct and transitive implementation fingerprint against those captured source bytes and the producing commit;
7. checks that the canonical payload and manifest bind the same readiness-verified upstream fingerprints;
8. independently recomputes the frozen descriptive reconciliation from the verified automated and human analysis artifacts and requires exact canonical equality.

Verification fails closed on hand-edited manuscript results, source-fingerprint drift, implementation drift, contract drift, changed task identity, missing-pair imputation, removed frozen contrasts or dimensions, or post-unblinding additions that change the frozen result structure.

## Preserved legacy automated-provenance compatibility

One historically preserved automated-analysis receipt lacks the newer
`verified_execution` field. The readiness gate admits that legacy path **only**
when the entire receipt matches the frozen legacy SHA-256 anchor; current or
modified receipts cannot opt into this compatibility mode.

That path must adapt the historical source-code fingerprints for the
provenance builder, provenance verifier, and output-consistency verifier to
their exact current bytes before invoking the historical verification calls.
All three sources are now captured via retained regular-file descriptors,
opened without following symlinks and nonblocking for special-file races.
The capture window rechecks bytes, inode and directory/path bindings after
both verification calls. A same-byte source replacement or parent-directory
swap fails closed instead of silently rebinding the adapted provenance hash.
This is a verifier-input integrity safeguard, not a new experiment, human
rating, or claim about automated or human outcomes.

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
