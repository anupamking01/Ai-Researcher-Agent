# Exploratory realized retrieval exposure (original frozen study)

**Scope:** post-hoc descriptive audit of recorded retrieval/resource exposure, not a new inferential model, causal estimate, or treatment rerun.

The preregistered retrieval-depth contrast D6–D3 changes *scheduled* browse slots from three to six. Scheduled slots do not necessarily mean successfully retrieved sources; a failed source result does not supply supporting evidence, and a slot not accounted for in the retained summary cannot be classified as an executed attempt. Planning and verification arms also differ in search/model calls and token usage, so budget comparisons are not equal-total-compute comparisons.

Run from the research checkout, without network access or provider credentials:

    python -m scripts.analyze_main_study_retrieval_exposure

The command first checks the exact Git-retained original treatment and evaluator CSV SHA-256 fingerprints, their published input-manifest aggregate reference, frozen task identities, full paired 40-cell matrix, source budgets, count arithmetic, support-rate mirrors and zero-evidence sentinels using the existing independent input auditor. A second descriptor-held treatment CSV capture must match its pinned original SHA-256 before descriptive calculations begin. The synthetic helper cannot establish those production provenance checks; it is used only by offline tests.

## Exhaustive descriptive fields

Each variant's ten reports contribute their scheduled slots, recorded successful sources, recorded failed sources, their sum (accounted source results), and scheduled slots less that sum (**capacity not accounted for by source results**). The diagnostic includes the full per-task inventory, totals/means, counts of reports with zero successful sources and residual capacity, and ratios of recorded successes and accounted results to scheduled slots. It separately reports search calls, model calls and total tokens.

For each of the three **predeclared treatment contrasts** D6−D3, P6−D6 and P6V−P6, the diagnostic emits every paired task's right-minus-left scheduled, successful, failed, accounted, residual, search-call, model-call and token counts. It counts tasks with more, fewer or equal successful sources on the right; no tasks are omitted and no inferential tests are calculated.

These fields allow a reader to see how *assignment* to retrieval capacity differs from *observed successful evidence retrieval* and other resource exposure. They do not establish why a source was missing or failed, whether an omitted slot was attempted, model/provider billing truth, the quality of retrieved evidence, or causation by retrieval depth, planning or verification.

## Research boundaries

The original task-paired strict-support estimand, deterministic confidence intervals, exact sign-flip p-values and Holm adjustment in the frozen confirmatory analysis are **unchanged**. This exploratory audit does not read support rates to compute its exposure descriptives (the independent input preflight nevertheless checks the original mirrored scores for integrity); no reweighting, subgroup selection, outcome-conditioned rerun, treatment-model call, evaluator call, or human rating occurs.

Only summary CSV bytes are locally pinned. Matching those bytes does not independently authenticate the missing original treatment reports/traces, provider retrieval execution, or original archives. Historical within-task fixed-order temporal confounding remains unresolved, as do the automated-to-human custody checks and genuine blinded evaluation by two eligible independent annotators. Keep diagnostic pilot, frozen automated confirmatory, exploratory retrieval exposure, and pending human-validation findings explicitly separate.
