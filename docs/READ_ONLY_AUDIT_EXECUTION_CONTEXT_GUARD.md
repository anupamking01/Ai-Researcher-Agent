# Read-only archive audit: delegated executable-input guard

The retained-canonical-archive and preserved-canonical-package workflows must
**verify existing evidence**, not run experimental treatments or the evaluator.
Their trigger path filters deliberately watch the experiment runner so source
drift is detected. A source filename in a trigger filter is not an invocation.

The shared test helper in scripts/audit_workflow_read_only.py used to inspect
only each step's run and uses text. A later edit could therefore delegate a
research command through a workflow-level, job-level, or step-level environment
variable (for example, run: $AUDIT_COMMAND), or through an action's with inputs,
while those two fields remained free of the experiment command's name.

The helper now checks all three environment scopes and action input mappings
in addition to run and uses. It explicitly leaves the on.push.paths
source-change filters untouched. Non-mapping environment/action-input
declarations fail closed. Synthetic, provider-free tests cover all three
forbidden experiment/evaluator entry points across four delegated-input scopes,
malformed input mappings, valid trigger filters, and both real audit workflows.

**Limitations:** This is a static, lexical safety gate for explicit script
identifiers, not a sandbox or a complete shell/interpreter dataflow analysis.
It cannot prove the behavior of third-party actions or detect commands built
without the forbidden literal identifiers. The immutable original evidence
and lack of independent report/trace custody are not changed by CI checks.

The five-task pilot remains diagnostic. Published automated comparisons retain
post-collection analysis-plan timing, fixed treatment order, and evaluator-policy
comparability qualifications. Retrospective analyses remain exploratory,
not prospectively confirmatory, and genuine human evaluation remains pending.
No treatment, evaluator, frozen outcome, or human rating is rerun or changed.


## Custom-shell execution boundary (23 November 2026)

GitHub Actions can execute a supplied shell template **before** or **around**
the step's harmless-looking run body. In particular, defaults.run.shell
at workflow or job level and a step's shell are execution-bearing fields.
Checking only run, uses, environment and action inputs does not catch a custom
shell such as bash -c "python -m scripts.run_budget_main_study; bash {0}".

The read-only guard now inspects all three shell scopes for the same forbidden
treatment/evaluator entry points. It rejects malformed shell values and
workflow/job default mappings rather than silently skipping them. Fifteen
synthetic, provider-free test cases cover three forbidden entry points across
three execution scopes, malformed mapping/shell declarations and legitimate
standard-shell plus source-watch configurations. The two actual audit
workflows remain checked by the existing tests.

This is a static lexical prohibition, not a guarantee against dynamically
constructed commands, compromised third-party actions, or malicious container
images. It does not certify historical report/trace custody or constitute
automated, confirmatory, exploratory, pilot or human-evaluation evidence.
No research treatment, evaluator or human rating is executed by these tests.
