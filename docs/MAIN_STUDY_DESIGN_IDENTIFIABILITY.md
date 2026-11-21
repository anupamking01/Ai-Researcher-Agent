# VERA fixed-order design: exact treatment/position alias audit

**Status (7 November 2026): retrospective structural design diagnostic; no new
measurements, reruns, statistical tests, treatment conclusions or human ratings.**

## Source and question

The original treatment runner at Git commit
[c3c15e46a8eec3a8bbc24c968eedc0548172a897](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/scripts/run_budget_main_study.py)
has a nested task-then-variant loop and defines the within-task order
**D3, D6, P6, P6V**. For every one of the ten frozen tasks, the arm also
determines its within-task run position (1, 2, 3 or 4). This is a property
of the historical runner's planned schedule, **not proof that actual treatment
clocks, external web conditions, or original report custody were authenticated**.
See [the execution-order validity audit](MAIN_STUDY_EXECUTION_ORDER_VALIDITY.md)
for the separate recovered-progress-log evidence gate.

A tempting post-hoc proposal is to regress the 40 published outcomes against
both treatment identity and within-task execution position, alongside task
fixed effects, as a way to *adjust away* the historical temporal confounder.
This adjustment is **not identifiable in the frozen fixed-order design**.

## Exact design-matrix rank calculation

Run without any access to experimental outcomes or model APIs:

    python -m scripts.audit_main_study_design_identifiability

The standalone audit constructs an exactly balanced **40-row design matrix**
from the source-linked expected sequence, using ten task intercepts, three
nonreference treatment indicators (D3 reference), and three nonreference
within-task position indicators (position 1 reference). It performs exact
rational Gaussian elimination, not floating-point thresholding.

| Design columns | Number of columns | Exact rank |
| --- | ---: | ---: |
| Task intercepts | 10 | 10 |
| Task + treatment (D6, P6, P6V) | 13 | 13 |
| Task + position (2, 3, 4) | 13 | 13 |
| Task + treatment + position | 16 | **13** |

Adding position effects **after** task and treatment increases rank by
**zero**. Adding treatment effects **after** task and position also increases
rank by **zero**. Treatment and order-position indicators are identical for
all ten tasks, so there are infinitely many treatment/position coefficient
decompositions that fit the same observed cells.

This proves a *design-level nonidentifiability*: a post-hoc model with both
fixed treatment and fixed within-task position effects cannot uniquely
separate the two. It **does not** prove provider drift occurred, quantify its
effect, or invalidate the arithmetic of the frozen paired contrasts. A
regression library may silently drop redundant columns, but the surviving
coefficients should not be represented as position-adjusted causal effects.

Synthetic regression tests contrast the historical fixed order with an
unexecuted, task-varying schedule where the combined rank becomes 16. This is
a code-path discrimination test, **not a replication, randomization proof, or
evidence that an alternate schedule achieved stable web conditions**.

## Evidence and reporting limits

The original 40 reports/traces are not independently authenticated because the
September 11 treatment and September 13 recovery workflow artifacts are absent.
Consequently, the audit describes the source-linked historical *design*, not
verified realized timestamps. Do not infer actual web drift, source stability,
clock offsets, or participant independence from these ranks.

The five-task pilot remains **diagnostic**. The ten-task automated main-study
results remain **frozen**, with the [post-collection statistical-plan timing
qualification](../paper/MAIN_STUDY_REPORTING_COVER.md): prospective precollection
preregistration and outcome blinding at freeze are not established. Existing
post-hoc exploratory diagnostics remain **exploratory**, including this design
audit. Human ratings, agreement and automated-to-human reconciliation remain
**pending**. Nothing here changes the original estimates, confidence intervals,
sign-flip calculations, Holm correction, or any research measurement.

For a *future, separately authorized* study, plan assignment before observing
outcomes and use the [prospective counterbalancing design](PROSPECTIVE_TREATMENT_ORDER_COUNTERBALANCING.md)
with independent, pre-execution custody. Even a full-rank schedule alone does
not prove randomized assignment, stable conditions, or causal identification.
