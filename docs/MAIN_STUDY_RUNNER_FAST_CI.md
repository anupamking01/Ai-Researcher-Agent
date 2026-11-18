# Independent offline CI for the noncanonical main-study runner

The [dedicated runner-provenance workflow](../.github/workflows/main-study-runner-provenance-fast-ci.yml)
runs when the noncanonical budget runner, its execution settings, safety-test
modules, or relevant verification dependencies change on the research branch
or pull request. It is a **separate** check from the full sixteen-shard suite
and the optional local diagnostic verifier CI. Full-suite job cancellation
therefore need not prevent an independently retained result for the directly
affected runner safety regressions.

The lane selects all `tests/test_main_study_runner_*.py` modules, plus the
synthetic task-file, pricing-file, and trace-accounting regressions. Its own
structural test enforces discovery of newly added runner modules and exact
firewalled test selection. The tests exercise explicit noncanonical-run
acknowledgment, pre-execution environment validation, treatment evidence
completion and custody, budget accounting, source checkout, task provenance,
and immutable pricing snapshots. They run under IPv4/IPv6 egress firewall
isolation without provider credentials or experimental treatment calls.

The workflow uses pinned Python and dependency constraints, checks the
checkout before and after tests, replays both the early stdlib diagnostic
receipt and the exact-commit targeted pytest receipt, and retains their logs
and receipts for 90 days. A successful targeted lane is **not** equivalent
to a complete sixteen-shard replay or to an externally authenticated
historical treatment archive. It cannot establish correctness of inaccessible
original September 2026 reports/traces or authorize blinded distribution.

The five-task pilot remains diagnostic; frozen automated findings retain
post-collection planning, fixed treatment order and evaluator comparability
limitations. Retrospective sensitivities remain exploratory; prospective
confirmatory evidence and real human ratings remain absent. Neither this
workflow nor its tests rerun original treatments, recover missing evidence,
change frozen effect estimates, or create human-validation results.
