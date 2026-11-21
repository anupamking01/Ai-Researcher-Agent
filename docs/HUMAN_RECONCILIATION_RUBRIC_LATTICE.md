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

## Joint automated strict-support-rate feasibility

The separate automated–human reconciliation readiness gate must also respect
the domain of the **automated** common-evaluator measure. For each frozen task,
let `s_D3`, `s_D6`, `s_P6`, and `s_P6V` denote the four strict-support rates.
They are fractions in **[0, 1]**. The three designated adjacent contrasts
record `s_D6 - s_D3`, `s_P6 - s_D6`, and `s_P6V - s_P6`.

Individually restricting each difference to [-1, 1] is insufficient:
`(+0.4, +0.4, +0.4)` is individually legal but implies a cumulative span
of **1.2**, which no four [0, 1] rates can produce. The readiness validator
now checks the **shared-source joint feasibility** of all three automated
differences for each task. Starting from zero, it forms the four cumulative
offsets and rejects a span greater than 1 (with a 1e-12 floating-point
arithmetic tolerance). This condition is necessary and sufficient for a
common starting rate in [0, 1] to exist. It does not invent or alter any rate.

Unlike human report-level scores, automated support rates need **not** lie
on a half-point lattice. The new check preserves valid fractional support
differences. Offline synthetic tests include contradictory and realizable
chains, boundary cases, an exhaustive 625-chain quarter-grid of independently
constructed four-rate vectors, and read-only verification of the existing
frozen automated differences. Two pre-existing **synthetic-only** test
fixtures were adjusted to satisfy this domain invariant without changing
their sign-based test expectations.

This is a redundant semantic safeguard alongside the source-bound automated
output and provenance verifiers, **not** independent authentication of missing
historical treatment reports or traces, nor evidence of human agreement or
causal identification. The pilot remains diagnostic; frozen designated-primary
automated results retain their documented post-collection analysis-plan
chronology limitation; exploratory sensitivity analyses are separate; genuine
human validation is still pending.
