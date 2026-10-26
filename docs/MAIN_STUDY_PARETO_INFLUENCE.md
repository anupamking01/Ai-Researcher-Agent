# Frozen cost–quality Pareto frontier: exhaustive task-omission audit

**Study:** `budget-main-v1`  
**Status:** Post-hoc **exploratory** robustness diagnostic, not a new confirmatory analysis. Human validation remains pending.

## Why this is a separate diagnostic

The frozen automated main-study inference identifies a **descriptive** treatment-cost/strict-support Pareto frontier across four treatments. With only ten paired tasks, that frontier could depend on a single task. The existing `MAIN_STUDY_TASK_INFLUENCE.md` diagnostic measures influence on **three paired quality means**, but does not examine **joint cost–quality frontier membership**. This separate audit enumerates all ten possible single-task omissions, recalculating both variant-level mean treatment cost and mean strict support for the remaining nine tasks, then applying the **unchanged frozen** `analyze_main_study._pareto_frontier` rule.

The full ten-task frontier is never replaced or redefined. No task is selected for removal, no inference method is changed, and no treatment, evaluator, or human rating is generated.

## Offline use

```bash
python -m scripts.analyze_main_study_pareto_influence > /tmp/vera-pareto-influence.json
python -m pytest -q tests/test_main_study_pareto_influence.py
```

The command writes **only stdout**; the shown shell redirect chooses a disposable local file. It never updates canonical output files.

The CLI first invokes the existing execution-bound provenance, independent offline recomputation, and manuscript-output verification chain. It also reads the retained 40-cell treatment and common-evaluator CSVs with bounded regular-file custody checks; requires their SHA-256 values to match the verified input manifest; and rechecks both source-byte sequences after upstream verification. A result is refused if CSV task/variant coverage, evaluator claim counts, treated/evaluated strict-support rates, published variant means, frozen paired task differences, or the original full-sample frontier disagree. These checks do not independently certify real-world evidence or create an atomic filesystem snapshot.

## Computation

For every task ID in frozen canonical order:

1. Retain the original other nine **paired** tasks for **all four variants**.
2. Recalculate each retained variant's arithmetic mean strict support from the fixed common-evaluator `supported / claims_checked` cells, **not** a pooled claim-weighted rate.
3. Recalculate arithmetic mean **treatment** cost from the preserved treatment CSV; evaluator measurement cost remains excluded under the frozen definition.
4. Run the unchanged Pareto rule: another variant dominates when its mean support is at least as high and its mean treatment cost no higher, with one inequality strict.
5. Report the entire frontier, all dominance relationships, all variant means, and whether frontier membership differs from the original ten-task sample.

The output also counts how many of the ten omitted-task analyses include each variant on the frontier. Those counts are **sample sensitivity descriptions**, not selection probabilities or estimates of the distribution of future outcomes.

## Claim boundaries

**Allowed:** “The observed full-sample Pareto ordering is/is not stable across every one-task omission in this frozen task set,” with all ten cases displayed.

**Not allowed:** dropping an inconvenient task from the primary dataset; treating one omitted-task frontier as the preferred treatment; claiming a population Pareto probability; adding p-values or CIs; using this diagnostic as independent replication; or inferring human report quality from common-evaluator strict support.

This is **distinct** from the existing paired-mean task-influence diagnostic. Pilot results remain diagnostic. The preregistered automated paired primary contrasts and Holm correction remain unchanged; this frontier audit is post-hoc exploratory only. Human ratings, inter-annotator agreement, and automated–human reconciliation remain outstanding.

## Tests and provenance boundaries

Synthetic tests cover complete enumeration, a deliberately constructed frontier change, unchanged inputs, duplicate/missing cells, contradictory evaluator counts, non-finite evidence, invalid treatment completion, published-result divergence, unbound input hashes, and observable changes during upstream verification. They are engineering controls and not real research findings.

The audit's SHA-256 fields identify retained bytes, not legal authenticity, ground truth, external generalizability, or the validity of automated support judgments. It makes no model or network calls.
