# Original-rater coverage of paired human report scores

Scope: **post-unblinding descriptive denominator audit only**. This addition does
not change the frozen human rubric, 40-report/two-annotator design, report
means, task-pair inclusion rule, bootstrap draws, confidence intervals, or the
automated study's confirmatory analysis.

## Why this exists

The frozen analysis explicitly averages **observed** original ratings per report.
A paired human contrast therefore includes a task when both treatments have at
least one observed report-level score. Its reported `n_pairs` does not itself
reveal whether each report mean uses one independent original rating or both.
Pre-unblinding agreement's A-only/B-only categories answer a different question
and intentionally cannot disclose treatment-group missingness.

For every frozen task, contrast, and one of the five predeclared rubric
dimensions, the analysis now records the number of observed original ratings
for the **left treatment report/right treatment report**. Counts range from
0 to 2 on each side. All nine exact cells (`0/0` through `2/2`) partition
the frozen task set, and the accompanying task-ID lists remain ordered by the
frozen task manifest. The canonical JSON and manuscript rendering preserve the
counts and IDs. `2/2` means both reports have two scores; `1/1`, `1/2`,
and `2/1` are **included** under the frozen observed-score rule but expose
partial annotation. A zero on either side is **excluded** with its task ID
retained under `missing_pair_tasks`.

The verifier rejects missing categories, inconsistent count/list lengths,
duplicate/omitted tasks, reordered IDs, and disagreement with the existing
paired denominator. Independent input-level recomputation remains available via
`scripts/verify_human_eval_analysis_outputs.py`; a SHA-256 manifest alone
does not certify the truth of scores or annotator identity.

## Scientific boundaries

All regression cases use synthetic integers and synthetic task IDs. No real
human ratings currently exist, so these new fields are **not measured outcomes**.
No low-coverage task is dropped or imputed to improve observed effects. The
automated confirmatory results remain frozen; pilot diagnostics and exploratory
observations remain separate. Human validation still requires genuine
independent blinded ratings, measured agreement, and support–human
reconciliation before paper conclusions.
