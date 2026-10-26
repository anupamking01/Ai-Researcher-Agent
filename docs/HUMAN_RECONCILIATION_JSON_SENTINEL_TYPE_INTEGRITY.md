# Exact JSON metadata types at the automated–human readiness boundary

Scope: scripts/verify_human_reconciliation_readiness.py; supplementary
identity/provenance validation only. This does not change the frozen study,
rubrics, comparisons, missingness, statistical analysis, or human ratings.

## Validity issue

The gate validates that the canonical automated and human analyses identify
the same frozen study and declare that no ratings were generated and no
treatment outputs were rerun. Python considers True == 1 and False == 0.
Previously, a JSON true could satisfy the integer schema_version: 1
check, and JSON 0 or 0.0 could satisfy a frozen boolean false
provenance declaration. A numeric substitute is not the same representation
as the required explicit declaration, even when equality happens to succeed.

## Change

Reject a non-integer (including boolean) automated schema version and require
the exact JSON value and type for every frozen human identity/provenance
sentinel. In particular, human_ratings_generated and
treatment_outputs_rerun must be literal JSON false; the human schema
version must be an integer 1, not true or 1.0.

Ordinary canonical payloads remain accepted. This is defensive redundancy
behind the independently verified input bundles; it prevents the final
cross-analysis readiness check from silently widening its contract if upstream
validators evolve.

## Offline regressions

Synthetic-only tests exercise boolean and numeric aliases at the direct
identity check and at the readiness entry point with deliberately stubbed
upstream evidence checks. A passing mocked upstream verifier is not evidence
of any human annotation. No treatments, common evaluator, scoring model, or
human collection were executed as part of these tests.

## Remaining research gates

Real blinded ratings for all 40 frozen reports, independent annotator
agreement, automated–human reconciliation and evidence-proportional final
conclusions remain pending. Pilot observations, frozen automated confirmatory
results, exploratory work and human validation are separate.
