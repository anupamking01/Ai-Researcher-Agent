# Automated–human reconciliation output verification

Status: procedure fixed before any real treatment-level human reconciliation is available.

This note defines the publication-integrity boundary for the frozen descriptive reconciliation. It does not change the automated confirmatory analysis, human-evaluation rubric, human-analysis plan, treatment outputs, or any measured result.

When reconciliation is eventually run, the canonical record must preserve the exact machine-readable reconciliation result, the Git commit SHA that produced it, the readiness gate's verified input fingerprints, and a SHA-256 plus byte count for the saved result. Any manuscript-facing table must be deterministically derived from that canonical result rather than edited as a second source of truth.

An independent offline check must be able to recompute the frozen reconciliation from the same verified automated and human analysis artifacts and obtain the same canonical structure. It must fail closed on source-fingerprint drift, contract drift, changed task identity, missing-pair imputation, removed frozen contrasts or dimensions, or any post-unblinding addition of hypothesis tests, multiplicity rules, correlations, composite scores, or treatment-validation thresholds.

Previously archived reconciliation results must not be overwritten. A legitimate source or implementation change requires a new versioned result while retaining the earlier bytes for auditability.

Verification is read-only: it must not rerun treatments, common evaluation, or human rating generation. Automated strict support and human report quality remain different constructs, and directional reconciliation remains descriptive only.

This mechanism does not create a human-evaluation result. Real blinded annotations, pre-unblinding agreement, frozen human analysis, and descriptive reconciliation remain pending scientific gates.

Current implementation note: the repository has the frozen readiness gate and deterministic reconciler; a create-only reconciliation publication bundle and independent saved-result verifier remain implementation work. This document fixes their provenance requirements before human outcomes exist so those mechanics cannot later be selected to fit the observed result.
