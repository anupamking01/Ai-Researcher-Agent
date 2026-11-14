# Offline human-evaluation analysis and output-verification CI

The [human-eval-analysis-fast-ci workflow](../.github/workflows/human-eval-analysis-fast-ci.yml) independently
exercises human-analysis **pre-unblinding input snapshots**, synthetic paired
statistics, production/publication custody, and the standalone
output verifier. Its coverage is distinct from the blinded-packet construction
lane and the blinded-rating freeze lane. Previously, these human-analysis
regressions depended on the broad repository test workflow, whose recent
runs ended cancelled; packet/freeze checks cannot establish that downstream
analysis and independently recomputed output verification passed.

The selected lane runs ten human-analysis regression modules and its workflow
contract test. It checks frozen statistical configuration and paired-input
validation; direct rating helper domains; snapshot file and tree limits,
indirect ancestor swaps, link aliases and source-capture drift; producer
fingerprint capture; output size and source-bound publication; and independent
manifest/JSON/Markdown verification. The tests use **synthetic fixtures only**.

The workflow uses a credential-free checkout, exact-commit pinned Actions and
Python 3.11.17, constraint-pinned minimal test dependencies, and the repository
outbound-network firewall. It compiles every tested module and relevant source,
verifies checkout/runtime identity before and after the run, binds the passing
test transcript to the run, attempt and commit, independently replays that
receipt, and retains both log and receipt for 90 days. The path filter includes
all covered modules, upstream implementation, governing plans, and verification
infrastructure; the contract test checks those triggers. Failures block a
successful receipt. This gives reproducible **selected-suite** evidence, not a
claim that the full repository suite passed.

This lane does not ingest original evidence for historical treatments, produce
scores for real annotators, establish independent rating eligibility, rerun
treatments or evaluators, or publish human-validation conclusions. Independent
custody of original reports and traces from treatment run `34620917346` and
evaluator-recovery run `34783525480` remains unresolved. A green workflow
cannot authorize source-verified distribution or unblinding.

The earlier five-task pilot remains diagnostic; main-study designated-primary
automated findings retain their post-collection analysis-plan, fixed-order and
evaluator-comparability qualifications. Retrospective sensitivities remain
exploratory; genuine blinded human ratings and reconciliation are pending.
