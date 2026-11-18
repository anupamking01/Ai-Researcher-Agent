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


## Bounded noncanonical task/pricing input capture

The acknowledged noncanonical study runner now reads the selected task JSON and
frozen pricing JSON through the same **8 MiB per-file**, no-follow,
nonblocking, single-link regular-file capture. It verifies the opened inode
and published pathname after a complete bounded read, then parses the exact
captured bytes and records their existing size/SHA-256 manifest snapshots.
This closes a pre-execution gap where unbounded `Path.read_bytes()` could
block on a substituted FIFO, follow a linked file or ingest an unexpectedly
large input before cost/task validity checks. Both gates run **before** any
model module is imported or new study manifest is written.

Synthetic offline cases exercise symlinks, hardlinks, FIFOs, oversized sparse
files, and same-byte parent-directory replacement for **both** task and
pricing inputs. They do not execute treatments or change the original frozen
task set/prices. This is an observed local integrity and resource safeguard,
not an atomic filesystem snapshot, a guarantee against hostile races in
ancestor directories, authentication of inaccessible historical source
artifacts, or evidence of experimental/human-evaluation results.
