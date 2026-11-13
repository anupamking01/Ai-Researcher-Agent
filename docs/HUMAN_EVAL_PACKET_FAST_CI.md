# Offline blinded-packet regression CI

The `.github/workflows/human-eval-packet-fast-ci.yml` workflow independently
exercises `tests/test_human_eval.py` and its own workflow contract tests
after changes to the packet builder, test suite, source-evidence verifier or
pinned dependencies. Unlike the large full-suite workflow, this narrow
**blinded-packet source-custody** lane can produce a specific pass/fail result
for symlink-ancestor, hardlink-alias, source-window, task-matrix and blinding
regressions without waiting for unrelated offline tests.

The job uses a pinned Python version and the repository's two dependency locks
as constraints, installs only the minimal pinned test/Markdown packages, checks
the exact checkout around firewalled pytest, and independently replays the
source-bound success receipt before retaining log and receipt for 90 days.
The receipt is emitted only after a successful, complete **selected test scope**;
it does **not** attest full-suite completion, independent runner integrity,
research artifact provenance, or any human validation. A cancelled or failed
job is **not a pass**, even if some selected tests previously passed.

This improvement responds to repeated full-suite cancellation and the
unverified status of newly introduced human-packet regressions. It neither
recovers nor independently authenticates original treatment reports/traces
from Actions runs `34620917346` and `34783525480`. Distribution of a
source-verified blinded packet is still blocked until unchanged original
sources and independent archival evidence are recovered, two eligible
annotators are selected and all documented handoff gates pass.

The five-task pilot is diagnostic. The frozen automated main study is
post-collection analysis with its existing chronology, order and evaluator
comparability limitations; retrospective sensitivities remain exploratory.
No treatment, evaluator, frozen estimate or human rating is rerun or changed
by this CI-only improvement.
