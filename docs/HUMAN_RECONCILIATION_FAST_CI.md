# Offline reconciliation-readiness and publication CI

The [reconciliation fast CI workflow](../.github/workflows/human-reconciliation-fast-ci.yml) separately
checks the final **automated–human reconciliation stage**, complementing
the existing human packet, rating-freeze and human-analysis fast lanes.
Those earlier lanes do not execute the reconciliation readiness gate,
descriptive producer or independent reconciliation output verifier.
Repeated cancellation of the broad offline test workflow meant that
this final verification family lacked reliable completed CI evidence.

The selected run compiles the reconciliation readiness, descriptive
producer and independent verifier implementations plus relevant upstream
verification code. Nine existing synthetic regression modules and a
workflow-contract module exercise: the immutable reconciliation
contract and analysis/provenance prerequisites; strict JSON decoding;
bounded and single-link source capture; file-generation consistency;
legacy source verification; task-paired descriptive categories and
missingness; create-only artifact size limits; and independent
recomputation of published JSON/Markdown/manifest provenance.
The test inputs are synthetic or previously preserved automated
receipts, **not newly collected human annotations**.

The job uses a credential-free exact-commit checkout, pinned GitHub
Actions and Python 3.11.17, only constraint-pinned minimal test
dependencies, and the repository's outbound-network firewall. It
checks source and runtime identity before and after tests, writes
and replays a run/attempt/commit-bound success receipt, and retains
the transcript and receipt for 90 days. A dedicated contract
asserts coverage, triggers, ordering, least permissions, and
receipt retention. A green lane establishes only the **selected
reconciliation regression-suite** result, not full-suite success.

**Research limits:** The five-task pilot remains diagnostic.
Frozen designated-primary automated results are a post-collection
analysis with fixed-order and evaluator-recovery comparability caveats,
not established prospectively preregistered confirmatory findings.
Retrospective sensitivities remain exploratory. The original
treatment and evaluator-recovery run artifacts are currently
unavailable for independent report/trace authentication.
Source-verified blinded handoff, two eligible independent annotators,
real ratings, agreement and reconciliation remain outstanding.
Neither this workflow nor its synthetic fixtures can certify human
validation or recover missing original evidence. No treatments,
evaluators, original results or human ratings are rerun or changed.
