# Offline pilot source-to-summary integrity CI

The dedicated [pilot-integrity-fast-ci](../.github/workflows/pilot-integrity-fast-ci.yml)
workflow closes a practical validation gap: the broad offline test workflow has
repeatedly completed as **cancelled** during ongoing research updates, while
existing specialist PR checks prioritize automated main-study or blinded-human
provenance. A green PR badge from those specialists does not independently
execute diagnostic-pilot trace, ledger, and summary regressions.

This lane executes all 19 selected offline test modules (including its workflow
contract) on a pinned Python interpreter and dependency-constrained pytest. Its
regressions exercise synthetic pilot source inventory and factor identity,
malformed/duplicate JSON, bounded trace capture, model usage and cost missingness,
frozen pricing continuity, source-to-exported CSV field reconciliation,
paired operational deltas and denominators, publication source continuity,
create-only outputs, progress accounting, and URL/source metrics.

It checks out the precise event commit without persisted credentials, rejects
outbound network access through the existing firewalled pytest runner, verifies
checkout integrity before and after testing, and retains an independently
replayed test-transcript receipt for 90 days. The source and every selected
test path are covered by PR and research-branch triggers; a workflow contract
test verifies the selected suite matches the CI invocation and compilation.

**Scientific scope:** These are synthetic regression tests and, where a test
explicitly loads preserved files, read-only source checks. Passing does not
authenticate unavailable original main-study reports/traces, repeat or alter a
pilot or any main-study treatment, supply a new effect estimate, prove
precollection preregistration or outcome blinding, establish unbiased
treatment order, or substitute for two genuine independent annotators. The
five-task diagnostic pilot remains diagnostic; frozen automated
designated-primary results retain their analysis-plan timing and evaluator
comparability qualifications, while retrospective sensitivities remain
exploratory and human validation remains pending.

A cancelled broad workflow remains **cancelled**, not silently converted to
passing by this narrower lane. Failures in this lane must be investigated,
rather than filtered or cherry-picked for improved outcomes.
