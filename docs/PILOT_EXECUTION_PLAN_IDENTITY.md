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
