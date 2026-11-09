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
