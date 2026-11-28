# Historical design identifiability: pinned original-runner source audit

**Scope: retrospective, outcome-free methodological provenance.** This checks
the original runner's planned treatment order, not actual execution times or
authenticated original treatment traces and reports.

The first exact-rational design audit
(`scripts/audit_main_study_design_identifiability.py`) calculates a
rank-13 combined task+treatment+within-task-position matrix from a manually
declared 40-cell schedule. That arithmetic is useful, but the prior script
alone did not verify that the declared schedule corresponded to immutable
historical source code. A future source/order mismatch could leave the ranks
correct for the **wrong** planned schedule.

Run from the full Git-history repository root:

```bash
python -m scripts.audit_historical_design_source
```

The new read-only verifier refuses shallow history and requires the original
commit `c3c15e46a8eec3a8bbc24c968eedc0548172a897` to be an ancestor of
HEAD. It uses **Git's original commit blob**, not the current working-tree
runner, and requires the original
`scripts/run_budget_main_study.py` blob identity to equal
`1e509f8e2abbd2cf7601eafa06f4e20588bf7ff5`.
Without importing or executing that runner, it parses a restricted Python AST:
the literal four-variant tuple must match the audit, the outer async main
must loop directly through tasks then through variants, and its single
`run_agent` treatment call must be awaited inside those loops. It then
recomputes the historical fixed-order matrix rank with exact fractions.
An altered Git checkout, missing ancestry, unexpected original source blob,
unsupported source-loop structure, or altered rank fails closed.

`.github/workflows/historical-design-source-audit.yml` runs this full-history
check offline and retains a JSON receipt with original Git identities, source
SHA-256, expected order, exact rank, and explicit scientific non-claims.
Synthetic regression tests exercise valid and invalid AST shapes and source
identity/ancestry failures.

The resulting **planned-design** finding is: each treatment maps to exactly
one within-task position in the source-linked fixed-order schedule, so a
regression with both treatment and within-task-position fixed effects
cannot separate those effects in the historical planned matrix. This does
not authenticate observed event order, original 40 trace/report files,
original experimental workflow custody, actual changing web conditions,
clock accuracy, causal effects, or human evaluation. The independently
missing original treatment/recovery artifacts must still be recovered and
validated before blinded human distribution.

The five-task pilot remains diagnostic; the frozen automated main-study
inference retains its **post-collection analysis-plan timing qualification**;
this source-linked structural audit is retrospective and exploratory.
All existing exploratory measurements remain exploratory and all human
validation remains pending. No treatments, automated evaluators, reports,
inference outputs, or ratings were regenerated or changed.
