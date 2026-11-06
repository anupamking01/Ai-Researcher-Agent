# Exploratory checked-claim denominator sensitivity

## Motivation and scientific scope

The frozen automated primary outcome is strict support among the claims
selected by the common post-hoc evaluator, capped at twelve claims per report.
A 1/1 rate and a 12/12 rate both contribute one report to the preregistered
task-macro mean. A report with fewer selected claims may be much less complete,
but the support rate alone cannot establish that. Differences in checked-claim
denominators across arms could affect interpretation of the automated quality
metric even when all recorded support fractions are arithmetically valid.

The standalone read-only command below reports denominator distributions for
all forty frozen task/treatment cells and the three predeclared task pairs.
This is a **post-hoc descriptive sensitivity**, not another statistical
hypothesis test or an alternative confirmatory outcome.

    python -m scripts.analyze_main_study_claim_denominators

## Exact computations

For each arm (D3, D6, P6, P6V), the diagnostic reports the complete 1–12
checked-claims histogram, task-level counts, total checked/supported claims,
mean/minimum/maximum counts and number of reports at the evaluator cap.

It also distinguishes two different descriptive weightings:

- **Equal-report macro strict support:** arithmetic mean of each of the ten
  task/report support fractions. This is the weighting used by the original,
  frozen confirmatory task-paired analysis.
- **Claim-pooled micro strict support:** total supported claims divided by
  total checked claims in that arm. This weights reports with more checked
  claims more heavily and has **no preregistered inferential standing**.

For each of the three frozen contrasts, it reports *every* paired task's
right-minus-left checked-claim count plus the complete direction counts and
mean difference. No tasks or arms are chosen based on observed direction.
There are no new p-values, confidence intervals, or human ratings.

The command first runs the independent published-CSV integrity auditor on both
retained summary files, checking original task identity, 40-cell completeness,
source budgets, evaluator counts, mirrored measures and exact published input
SHA-256 fingerprints. It then captures the evaluator CSV once more and verifies
its independently pinned original digest before calculating the diagnostic.
Synthetic regression fixtures can call the pure computation function without
presenting themselves as published findings.

## Limitations and claim boundaries

These counts describe *selected evaluator claims*, not every factual claim
made in a report, claim importance, task completeness, source reliability,
retrieval quality, or independent human quality. The twelve-claim selection
cap means a maximum denominator is censored by design. A micro rate may be
higher or lower than the frozen macro rate without proving any variant better.
Report-level task pairing, and the original Holm-adjusted confirmatory family,
must not be replaced by pooled-claim arithmetic or post-hoc selection.

Inputs are historically Git-retained published **summary CSV bytes**. Local
fingerprint validation does not recover or independently authenticate the
unavailable original treatment traces/reports or evaluator execution.
Human-validation readiness is still blocked on the documented archive-custody
and two-independent-annotator gates. Diagnostic pilot findings, frozen
automated confirmatory analysis, this exploratory denominator sensitivity,
and prospective human validation remain separate. This command performs no
treatment/evaluator reruns, no model calls and no artifact writes.
