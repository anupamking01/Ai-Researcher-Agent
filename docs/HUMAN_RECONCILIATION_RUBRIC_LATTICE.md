# Half-point validity for blinded human-score reconciliation

The frozen human-evaluation analysis plan scores each report on five integer
1–5 rubric dimensions. Its report-level score is the arithmetic mean of
**one or two** observed independent integer ratings; blanks remain missing.
Therefore every nonmissing report score is an exact integer or half-integer.
For a task-paired contrast, the difference of two such report scores must
also be a multiple of **0.5**, in the permitted range [-4, 4].

The cross-analysis readiness verifier now rejects a human
`task_differences` entry outside that lattice, **even if** its reported mean
and sign counts have been consistently recomputed around the altered value.
It enforces the same rule for all five dimensions and all three frozen
contrasts, while leaving legitimate missing pairs and their denominators
untouched. This is a consistency check against the already frozen rubric,
not a new rounding rule: it does not round an invalid value into compliance.

Automated strict-support-rate differences are fractions over evidence
items rather than human rubric scores. Their existing [-1, 1] domain is
unchanged; an automated difference need not be a half-integer.

Synthetic offline regressions check off-lattice values, valid boundary and
interior half-steps, unchanged automated fractional support differences,
and the pre-existing missingness path. No experimental treatment, common
evaluator, frozen automated analysis, genuine human annotation, or
hypothesis test is run or changed.

The gate does **not** establish that submitted ratings came from eligible,
independent human annotators or authenticate missing original reports.
Independent verification against original retained ratings and source-bound
analysis artifacts remains mandatory. The five-task pilot is diagnostic;
automated designated-primary analyses have documented precollection
preregistration limitations; post-hoc sensitivity studies are exploratory;
human validation remains pending.

## Joint cross-contrast score and missingness feasibility

The three frozen contrasts form a consecutive report chain for each task and
dimension: D3 → D6 → P6 → P6V. Each included comparison establishes that
**both** endpoint reports have an observed report-level score. If comparisons
D6 − D3 and P6V − P6 are both present, then the D6 and P6 scores also exist:
P6 − D6 cannot legitimately be declared missing for that task/dimension.

Individually legal half-step differences can also contradict the shared 1–5
rubric. For any consecutive observed segment, cumulatively sum its differences,
starting at zero. All reports in that segment can be assigned valid 1–5
half-step scores **if and only if** the maximum minus minimum cumulative offset
is at most **4**. For example, differences (+1.5, +1.5, +1.5) each satisfy
the single-contrast bound, but jointly require a 4.5-point score span and
must be rejected. Differences (+4, −4, +4) remain valid: corresponding
report scores (1, 5, 1, 5) exist. Genuinely disconnected segments are checked
separately without imputing missing reports.

The readiness gate now checks this joint feasibility for **every frozen task
and each of the five dimensions**, after its existing contrast-level domain,
task partition, order, and summary checks. Synthetic regressions exercise
impossible spans, valid boundary cases, impossible middle-edge missingness,
and legitimate missing endpoints. It does not infer actual ratings or verify
their independence: the separate source-bound human-analysis recomputation
and original-report custody gates remain mandatory. No pilot outcomes, frozen
designated-primary automated results, exploratory estimates, or human-validation
results are created or changed; human validation remains pending.
