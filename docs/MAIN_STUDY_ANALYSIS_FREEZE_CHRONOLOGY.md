# Main-study analysis-plan freeze: chronology and inference boundary

**Status:** Retrospective, source-linked audit of Git history and GitHub Actions metadata, 7 November 2026. This is not a new experiment, statistical analysis, preregistration, or human-validation result.

## What was frozen, and when?

An earlier [research protocol](../paper/RESEARCH_PROTOCOL.md) was committed on 8 September 2026 and updated on 9 September. It set out broad research questions, stage-wise hypotheses, budget principles, several planned contrasts, and human-validation aspirations. It did **not** contain the later exact three-test Holm family, paired bootstrap, sign-flip procedure, and full ten-task inference rules appearing in [the exact analysis plan](../paper/ANALYSIS_PLAN.md).

The following are separately observable milestones, **not** substitutes for independent evidence custody:

| Event | Git / Actions evidence | UTC date | Provenance meaning |
|---|---|---|---|
| Last pre-treatment protocol revision | [e390c0de](https://github.com/anupamking01/Ai-Researcher-Agent/commit/e390c0de7001011c171d0161a6eb1b96517a3583) | 2026-09-09 18:57 | Broad design existed before treatment execution. |
| Original 40-cell treatment execution | [Actions run 34620917346](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/34620917346), at commit c3c15e46 | 2026-09-11 16:15 | Collection began; workflow later failed during common evaluation. |
| Common-evaluator recovery | [Actions run 34783525480](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/34783525480), at commit 8733ce49 | 2026-09-13 21:20 | The evaluator-only recovery workflow had already run. |
| **Exact paired analysis plan added** | [commit 7352cae1](https://github.com/anupamking01/Ai-Researcher-Agent/commit/7352cae144e82e7862630db9501c00570adec640) | **2026-09-14 17:27** | The written exact inference plan is later than both earlier runs. |
| Analysis implementation | [commit 87938771](https://github.com/anupamking01/Ai-Researcher-Agent/commit/879387710fe5ad2db434754f5208b47dca2756b7) | 2026-09-14 17:28 | Analysis implementation followed the exact written plan. |
| Canonical automated analysis/publication | [Actions run 36070798723](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/36070798723); [Git publication 1ddc84c2](https://github.com/anupamking01/Ai-Researcher-Agent/commit/1ddc84c261bc4207206e9e1d8724743392585598) | 2026-09-24 23:03–23:04 | Canonical published inference postdates the written plan. |

The **Git ancestry** confirms the order e390c0de → c3c15e46 → 8733ce49 → 7352cae1 → 1ddc84c2. The exact written analysis-plan file has not changed on the current research branch. Git commit dates and workflow start times are public provenance metadata, not cryptographic proof of what any researcher did or knew at those times.

## Reporting rule

**Do not call the exact statistical plan prospectively preregistered before treatment collection or before automated evaluator recovery.** Unqualified earlier “preregistered” and “predeclared” wording must be read with this timeline. The defensible description is **a frozen, post-collection, pre-canonical-publication statistical analysis plan** with three *designated primary paired contrasts*, plus separately labeled secondary and exploratory diagnostics. The pre-treatment protocol is an earlier broad design; it must not be represented as freezing the later exact inferential procedure.

The sequence **does not prove** that outcomes were viewed before writing the plan: no independently verifiable outcome-access/blinding log has been recovered. Conversely, the evaluator-recovery workflow having run and the canonical publication taking place later **do not prove** that anyone remained blind to outcomes at plan freeze. Thus an unqualified claim of prospective statistical preregistration or demonstrated outcome-independent planning is not supported. Interpret the exact sign-flip calculations under their stated model assumptions, **not** as inference justified by historical randomized allocation: the original treatment order was fixed within task.

This limitation does not invalidate the saved arithmetic, change existing frozen estimates, justify rerunning treatments, or convert post-hoc exploratory analyses into confirmatory tests. The five-task pilot remains diagnostic; the ten-task automated analysis is frozen but its confirmatory/preregistration strength must be qualified; blinded human evaluation remains pending and cannot repair timing confounding.

## Independent offline lineage check

From a **full-history, non-shallow** research-branch checkout, run:

~~~bash
python -m scripts.audit_analysis_plan_freeze_chronology
~~~

The read-only command checks pinned Git commit objects and ancestry and compares the original analysis-plan bytes with the current HEAD and working copy. It fails closed if commits are unavailable, the plan changed, or the claimed ordering is contradicted. It does not download artifacts, inspect outcomes, generate evidence, or write files. Its JSON receipt explicitly reports that precollection statistical preregistration and pre-analysis outcome blinding are **not established**; Git ancestry alone cannot make those claims true.

The offline audit checks commit ancestry, while the **run-start dates above require separate inspection** of the linked GitHub Actions metadata. The associated regression tests use wholly synthetic Git histories. They do not recover any historical research materials. Original treatment traces/reports are still not independently authenticated; annotator ratings remain absent.
