# Pilot execution-plan and trace-identity integrity

The diagnostic five-task pilot is a fixed live treatment/task design, not a
trial-selection procedure. A repeated variant or duplicated task ID at launch
would revisit the same cell and could overwrite its earlier report/trace.
A malformed postrun manifest could also hide repeated IDs because a Python
set collapses duplicates when computing the expected treatment/task matrix.

`scripts/run_pilot.py` now checks the *entire source task manifest* and the
selected run plan before writing any manifest, importing the agent, or making
paid/live calls. It rejects duplicate or unknown treatment IDs, repeated or
malformed task IDs, blank questions, repeated `--task-id` filters, and unknown
filters. A valid subset remains in the frozen task-file order; there is no
automatic retry, imputation, or outcome-based selection.

`scripts/validate_pilot_artifacts.py` independently rejects repeated or
malformed postrun manifest IDs and any mismatch between the manifest and
progress identifiers. Trace and experiment cell IDs must agree with one
another, the task-set manifest, and the containing variant directory. A
synthetic regression suite exercises both producer and validator failures and
includes a read-only check of the committed five-task source manifest.

Reproduce without provider calls:

```sh
python -m pytest -q tests/test_pilot_plan_identity.py
```

This guard is **prospective safety for diagnostic pilot tooling**. It does not
retrospectively authenticate original run files, prove live execution identity,
or revise the Git-preserved 15 selected pilot records. It does not alter the
frozen ten-task automated main-study estimates, postcollection statistical-plan
qualification, exploratory analyses, or pending blinded human validation.

## Live diagnostic dispatch authorization

The manual `.github/workflows/live-pilot.yml` entrypoint can incur live
provider charges and select task subsets. New pilot execution must **not** be
confused with September 2026's original diagnostic pilot or used to cherry-pick
outcomes. A nondefault manual input `pilot_ack=NONCANONICAL_LIVE_PILOT` is
required. An unconditional first-step guard rejects missing/incorrect
acknowledgement before checkout or credential access.

**An acknowledged dispatch no longer cancels other already-running pilot
jobs.** The previous `Cancel older live-pilot runs` step called the Actions
cancel API after acknowledgement; this could terminate a separately approved,
still-active paid run, discard its partial evidence, and waste provider budget.
It has been removed along with the now-unnecessary `actions: write` job
permission and `GH_TOKEN` access. The job requires only `contents: read`.
The existing `concurrency.cancel-in-progress: false` remains in force for
in-progress runs; GitHub Actions may still replace *pending* runs within a
shared concurrency group. This safeguard does not promise preservation of
queued dispatches or prevent an authorized actor cancelling a run elsewhere.

Any newly uploaded run bundle is named
`noncanonical-diagnostic-pilot-<run_id>`. Offline YAML regression tests
protect manual-only execution, the guard, non-bypassable live steps,
lack of workflow-initiated cancellation/API write access, and archive labelling.
This is prospective execution safety, not authentication of original
artifacts, a change to pilot diagnostic status, prospective precollection
preregistration, revision of frozen automated results, promotion of exploratory
analyses, or evidence of human validation.
