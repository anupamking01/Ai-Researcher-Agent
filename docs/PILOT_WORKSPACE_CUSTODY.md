# Diagnostic pilot output-workspace custody

The pilot runner formerly validated duplicates **within one invocation** but
still reused the global `outputs/` directory on the next invocation.
A second pilot in the same checkout could overwrite `pilot_manifest.json` and
`pilot_progress.json` while old report and trace artifacts remained. Even
without duplicate IDs in either plan, this could yield a mixed-collection
summary or erase the original execution's checkpoints.

`scripts/run_pilot.py` now refuses to begin when `outputs/` contains **any
entry** (including an unrelated file or empty trace directory). A nonexistent
or empty real directory is permitted; a symlink or non-directory output root is
not. The check runs after task-plan validation but **before** credential
validation, provider imports, manifest writes, or live calls. The preflight is
read-only. Furthermore, the pilot manifest is created exclusively (not
truncated), so competing pilot invocations cannot overwrite one another's
manifest even if they both observed an initially empty workspace.

Operators must retain previous reports, traces, summaries and checkpoints
unchanged, and use a separate clean checkout/output workspace for any new
diagnostic execution. A clean workspace does **not** authorize repeating a
treatment to improve its result, selecting a favorable retry, or presenting a
new run as part of the frozen historical pilot. The check is not a full
cross-process filesystem transaction or evidence-authentication mechanism;
external writers or filesystem tampering still require independent controls.

Offline reproduction (no browsing, models or historical data mutation):

```sh
python -m pytest -q tests/test_pilot_workspace_custody.py
```

This is a **forward-looking diagnostic pilot** safeguard. The original
five-task pilot remains diagnostic, the ten-task automated analysis remains
frozen with its preregistration/evaluator-recovery qualifications, retrospective
robustness analyses are exploratory, and genuine blinded human evaluation is
still pending. The new gate does not recover missing original experimental
reports or authenticate the historical evaluation archive.
