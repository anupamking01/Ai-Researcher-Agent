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

## Counterbalanced handoff and pre-freeze evidence chain

The packet fast lane also executes three previously omitted synthetic suites:
`test_human_eval_counterbalanced_handoff.py`,
`test_human_eval_counterbalanced_submission_pair.py` and
`test_human_eval_counterbalanced_freeze_link.py`. Together they test the
source-bound two-order handoff, the two distinct blinded submissions and
preflight receipts, and the link from the pair receipt to the retained
pre-unblinding ratings freeze. The coverage includes tampering, duplicate
identities, swapped order, original-receipt byte identity, and changes between
serial verification stages. This is not another experiment or a new human
agreement analysis. CI now compiles the three standalone verifiers and the
three test modules, and path filters trigger the lane when their source or
synthetic support fixture changes. The workflow-contract regression enforces
those declared selections and triggers.

This regression evidence is **software-only** and **conditional**: a passing
synthetic test cannot authenticate the missing historical treatment reports,
prove annotator eligibility or independence, substitute for genuine ratings,
or license the frozen automated findings as prospectively confirmatory.
The five-task pilot remains diagnostic, the automated post-collection analysis
keeps its existing qualifications, and post-hoc sensitivity analyses remain
exploratory. The unverified original artifacts still block actual blinded
handoff and independent human evaluation.

## Automated-run lineage before human distribution

The packet lane also runs `tests/test_human_eval_automated_run_lineage.py` and
`tests/test_human_eval_automated_handoff.py`. This previously omitted, distinct
**automated-to-human source-linkage gate** checks that each blinded report's
run ID matches the frozen evaluator's run ID for the same treatment/task cell,
including mirrored claim counts, strict-support rates and evaluator cost.
The joint coordinator-only handoff tests then require independently pinned
research and packet manifest *file* hashes, the published frozen CSV aggregate,
the original treatment task-list bytes, and both counterbalanced bundles to
remain coherent across the verification window. It is possible for two
counterbalanced handoffs to agree with each other while still referring to
reports other than the ones measured by the frozen automated evaluator;
packet-only distribution tests cannot detect that discrepancy.

The two synthetic suites, their verification scripts, and transitive source
validators are included in compilation, firewalled execution and both push
and PR path triggers, all enforced by the workflow contract. A passing
exact-commit receipt attests these local regressions only; original historical
report/trace artifacts and independently retained manifest-file SHA-256 pins
are still required before any actual source-authenticated distribution.
Synthetic fixtures do not reconstruct the missing original evidence or
establish annotator eligibility, real human ratings, or agreement. The pilot
remains diagnostic, frozen designated-primary automated inference retains its
post-collection timing, fixed-order and evaluator comparability limitations,
retrospective sensitivities remain exploratory, and human validation is pending.
