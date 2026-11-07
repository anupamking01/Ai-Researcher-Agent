# Exhaustive task influence: an exploratory robustness diagnostic

**Study:** `budget-main-v1` · **Status:** post-hoc exploratory, not preregistered confirmatory inference.

## Why this exists

The frozen ten-task main study reports paired mean strict-support differences under three predefined contrasts. With only ten paired observations, a single task can have a notable effect on a sample mean. This diagnostic exposes that sensitivity **without selecting tasks based on observed outcomes**, modifying a treatment, changing the frozen dataset, or rerunning a model.

The diagnostic enumerates **all 10 possible single-task omissions for each of all 3 preregistered contrasts**. Every row reports the mean of the remaining nine original paired differences and its change from the untouched ten-task mean. The complete-study mean stays the point estimate of record. No p-values, intervals, post-hoc hypothesis tests, adjusted significance decisions, or new primary endpoints are produced.

## Use (offline, read-only)

```bash
python -m scripts.analyze_main_study_task_influence > /tmp/vera-task-influence.json
python -m pytest -q tests/test_main_study_task_influence.py
```

The CLI prints deterministic JSON to stdout; it does not publish a new canonical result or overwrite any research output. The output file in the example is a **caller-selected local diagnostic**, not a committed result. The CLI requires an execution-bound provenance receipt and invokes the existing verified-execution gate (including receipt provenance), the independent offline frozen-analysis recomputation, and the exact manuscript-output verifier before calculating the diagnostic. A legacy receipt without verified execution is deliberately not sufficient for this newer exploratory diagnostic. It records SHA-256 identifiers of the two verified canonical inputs and rechecks their bytes after verification. No treatment/evaluator or human-rating collection occurs.

## Definitions and interpretation

For original frozen task differences `d[1] ... d[10]` (right minus left), the full mean is `mean(d)` and each omission mean is `mean(d[j] for j != i)`. The reported change is `omission_mean - full_mean`. The minimum and maximum over the ten omission means summarize the observed one-task influence *on this original sample only*. All ten omission IDs appear in canonical frozen task order, with no pruning, replacement, or ranking of treatments.

**Claims allowed:** these diagnostics describe how each fixed original-sample paired mean responds to excluding one task, and are useful for assessing task concentration and small-sample sensitivity.

**Claims not allowed:** calling a nine-task omission a new primary estimate, reporting significance from selected omissions, replacing the Holm-adjusted confirmatory analyses, treating the ten original tasks as a population-representative benchmark, or using the results to choose a favorable rerun/variant. Cross-contrast comparisons remain descriptive. The diagnostic also cannot adjudicate claim-level truth, model-evaluator bias, web drift, or whether humans agree with the automated support judge.

## Evidentiary separation

| Layer | Source | Status and use |
|---|---|---|
| Diagnostic pilot | `paper/PILOT_RESULTS.md` | Diagnostic only; cannot supply omitted main-study pairs. |
| Frozen confirmatory automated inference | `paper/ANALYSIS_PLAN.md`, `outputs/main_study_inference.json`, `paper/MAIN_STUDY_INFERENCE.md` | Original ten-task, three-contrast results remain unchanged. |
| Task-influence diagnostic | `scripts/analyze_main_study_task_influence.py` | Exhaustive *post-hoc exploratory* sensitivity only; no added inference. |
| Blinded human evaluation | `paper/HUMAN_EVAL_PROTOCOL.md` | Pending genuine independent blinded annotations; this script supplies none. |

## Verification boundary

The upstream provenance verifier independently recomputes the frozen automated inference using retained evidence; the Markdown verifier checks the published rendering. The exploratory CLI now captures each canonical inference/provenance input through a directory-bound, non-symlink, nonblocking regular-file descriptor, checks its inode/size/timestamps before and after bounded reads, and rejects a replaced parent or input path. This prevents a symlink/FIFO swap between an initial file check and opening a source, and prevents observed same-byte inode replacement from passing the local custody check. It does not authenticate source data or lock the filesystem. The before/after read is an additional point-in-time custody check, not a filesystem lock or cryptographic proof of real-world authenticity. A SHA-256 records byte identity, not measurement validity. If source verification fails or the frozen cardinality, mean, or strict-support range conflicts, the diagnostic fails closed. The original experimental tasks and main-study outcomes are never rewritten.

**Scope discipline:** This script exists as a transparent diagnostic after automated results were available. It is not a preregistered test or a reason to redefine the hypotheses or stop human validation.

## Retained canonical CI artifact (post-hoc only)

The existing `.github/workflows/exploratory-pareto-stability.yml` workflow
also runs this **distinct paired-mean task-influence diagnostic**, reusing its
isolated, receipt-era implementation worktree. That checkout first replays the
execution-bound provenance verifier against retained canonical evidence.
It neither calls an LLM nor resumes the common evaluator.

The workflow separately uploads `vera-task-influence-<run-id>`, containing
`vera-task-influence.json` and
`vera-task-influence-receipt.json`. The standalone, stdlib-only
`scripts/verify_main_study_task_influence_artifact.py` independently
recomputes **all 30** nine-task paired means and their changes directly
from the original ten-task canonical differences. It refuses missing,
reordered, duplicated, numerically inconsistent or extra claimed results,
and binds the artifact to the exact canonical inference and execution-bound
provenance bytes using SHA-256. The receipt identifies both the current
checkout and the historical analysis implementation commit. The workflow
fails before publication if either the producer or independent verifier
fails. The artifact is retained for 90 days unless deliberately preserved
elsewhere with its checksums.

This is verification of an exploratory calculation on the original ten
tasks, **not** a revised confirmatory estimate, an independent human
assessment, or a basis to remove any task from the manuscript analysis.
