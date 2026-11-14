# Offline blinded-packet regression CI

The `.github/workflows/human-eval-packet-fast-ci.yml` workflow independently
exercises `tests/test_human_eval.py`, the full synthetic packet-verification
regressions, bounded source-capture checks, physical-record and JSON-numeric
integrity cases, whole-verification-window custody checks, and its workflow
contract tests
after changes to the packet builder, packet verifier, cross-stage packet
readers, selected regression modules, source-evidence verifier or pinned
dependencies. The workflow contract test asserts all selected modules are both
compiled and exercised, and that their implementation paths trigger CI on
pushes and pull requests. Unlike the large full-suite workflow, this narrow
**blinded-packet source-custody** lane can produce a specific pass/fail result
for symlink-ancestor, hardlink-alias, verification-window, duplicate/invalid
physical records, malformed JSON numbers, task-matrix and blinding regressions
without waiting for unrelated offline tests. This closes the gap where the
previous fast lane checked packet construction but did not execute the
independent packet-verifier regression module.

The job uses a pinned Python version and the repository's two dependency locks
as constraints, installs only the minimal pinned test/Markdown packages, checks
the exact checkout around firewalled pytest, and independently replays the
source-bound success receipt before retaining log and receipt for 90 days.
The receipt is emitted only after a successful, complete **selected test scope**;
it does **not** attest full-suite completion, independent runner integrity,
research artifact provenance, or any human validation. A cancelled or failed
job is **not a pass**, even if some selected tests previously passed.

This improvement responds to repeated full-suite cancellation and the
lack of fast-lane execution for the independent packet verifier. It neither
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

## Annotator-distribution verification coverage

The fast lane now additionally compiles and runs all three synthetic
annotator-distribution suites: export, capture/resource bounds, and the
standalone bundle contract. This closes a previously untested handoff between
verified coordinator packets and the four-file treatment-blind distribution.
The standalone distribution verifier also pins every ancestor directory with
no-follow descriptors for its entire read/recheck window; it rejects an indirect
symlink at entry and a redirect observed after the final byte replay, even
when the source bytes are unchanged. The expanded workflow contract enforces
test selection and push/PR path triggers for these modules.

Passing this selected synthetic lane verifies local software behavior only.
It does not establish the provenance of historical reports, authorize
distribution, or supply real human ratings.
