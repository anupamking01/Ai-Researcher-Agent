# Frozen-design concordance in retained canonical archive audits

The canonical-analysis ZIP is evidence from an earlier GitHub Actions run, not permission to revise the predeclared scientific design. Both read-only retained-evidence workflows compare the current research branch with the immutable, provenance-compatible analysis checkout `f333623380526fa05dcb14110e7ec1fb72d2d0e2` **before downloading an archive**.

The comparison now covers three frozen controls—`experiments/main_budget_tasks.json` (the 10-task main-study design), `experiments/openai_pricing_2026-09-08.json` (historical cost schedule), and `paper/ANALYSIS_PLAN.md` (predeclared primary inference)—as well as the six previously bound published analysis input/output files. Every file must be byte-for-byte identical to the frozen checkout. A change in the present branch is an explicit audit failure, not an accepted revision of earlier evidence.

Both workflows also include all nine files in their push path filters. This matters: a drifted input cannot evade the real retained-archive gate simply because only unit tests ran on that commit. `tests/test_canonical_frozen_design_workflow_guards.py` enforces the trigger and verify-before-download sequence without contacting a provider or generating results.

This is a **concordance gate** rather than a ban on future research. Legitimate changes to the analysis plan, tasks, or prices must be treated as a separately versioned protocol/analysis and cannot be silently substituted for the frozen main study. The audit does not treat an old GitHub artifact as authentic original treatment evidence, regenerate treatments, or perform human evaluation. The diagnostic pilot, frozen automated confirmatory analysis, exploratory studies, and pending blinded human ratings remain separate.

The historical treatment and evaluator-recovery artifacts are still unavailable through the original run listings. The verified canonical-analysis archive and its preservation package do **not** replace the original 40 trace/report pairs or independently retained historical fingerprints. Those custody and human-evaluation gates remain open.

## Audit trigger coverage for verifier dependencies

These two GitHub Actions audits invoke Python modules with **transitive** first-party
imports. Previously a modification to a shared verifier such as
\`scripts/preflight_recovered_artifact_zip.py\`,
\`scripts/verify_analysis_provenance.py\`, or
\`scripts/verify_canonical_archive_checkout.py\` did not itself trigger
either real archive audit: their push path filters mostly listed only their
direct entrypoints. Ordinary PR unit tests could pass without replaying the
actual retained artifact on the altered verification implementation.

Both workflows now watch their complete currently known static first-party
\`scripts/*.py\` import closures. The offline test
\`tests/test_canonical_archive_audit_trigger_coverage.py\` parses those
imports using Python AST, follows indirect dependencies, and requires the
workflow push path list to contain each reachable module plus the workflow
itself. A newly imported local verifier therefore creates a failing CI
contract until its path is added to the audit trigger. Only the existing
read-only verification workflows are scheduled; no model calls, treatment
reruns, evaluator recovery, or human ratings are produced by this change.

The check covers **static Python imports of flat scripts modules**, not dynamic
\`importlib\`, shell-sourced code, or external packages. Such new dependencies
require explicit reviewer inspection and corresponding trigger updates.
The audits still rely on expiring GitHub-hosted artifacts: a successful
trigger does not extend archival retention, establish independent custody
of the 40 original treatment reports, or complete human validation.
