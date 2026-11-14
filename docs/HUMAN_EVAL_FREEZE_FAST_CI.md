# Dedicated offline blinded-rating freeze verification CI

The [human-eval-freeze-fast-ci workflow](../.github/workflows/human-eval-freeze-fast-ci.yml)
is a separate, narrowly scoped regression lane for the **pre-unblinding
human-rating freeze producer** and the **independent freeze verifier**.
The existing blinded-packet fast lane tests packet construction and packet
source custody; it does not run the complete freeze-specific test family.
Repeated cancelled full-suite workflows do not establish completed validation
for the distinct freeze-production and freeze-verification paths.

The new lane executes ten synthetic freeze test modules (plus its workflow
contract test) under the existing outbound-network firewall. These cover
rating-row validation, exclusive archive publication, independent pre-unblinding
verification, hash-versus-parsed-byte consistency, bounded captured input,
freeze-tree inventory and resource limits, external hardlink aliases, and
JSON numeric and nesting validity. Every selected module is compiled and
included in the exact pytest invocation; the workflow contract checks that
changing these modules, their implementation, governing documents, and the
test/receipt infrastructure triggers this CI lane.

It uses the repository's pinned Python version and dependency constraints
with a minimal package installation, GitHub Actions pinned by exact commit,
and a credential-free checkout. A success receipt is produced only after
the selected firewalled pytest command completes successfully; an independent
replay checks the receipt against the run/attempt/commit identity and original
log before retaining both for 90 days. This is a bounded **selected-suite**
validation, not evidence that the full repository suite ran or passed.

The workflow only runs **synthetic tests**. It does not create real human
ratings, execute treatment arms or the common evaluator, modify any frozen
automated outcomes, unblind treatment labels, or recover historical source
artifacts. A green check is local regression evidence, not source attestation
or confirmation of annotator eligibility, independent ratings, adjudication,
inter-rater reliability, or a human-validated treatment effect. Independent
custody for the original 40 reports/traces from runs `34620917346` and
`34783525480` remains unresolved; source-verified blinded distribution
is blocked until the existing provenance and handoff gates are satisfied.

The five-task pilot remains diagnostic. Main-study designated-primary
automated contrasts are post-collection analyses with analysis-plan timing,
fixed-order and evaluator-comparability qualifications; retrospective
sensitivity analyses are exploratory, not confirmatory. This workflow does
not change those classifications.
