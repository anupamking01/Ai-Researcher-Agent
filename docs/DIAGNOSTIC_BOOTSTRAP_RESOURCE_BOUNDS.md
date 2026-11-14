# Bounded in-memory diagnostic bootstrap

The dependency-free `logic/evaluation.py` bootstrap helpers accept one-pass
synthetic or prospective diagnostic observations. Previously, a malformed
request could consume an unlimited producer or allocate unbounded bootstrap
draws. A green offline test run did not establish safe behavior for such inputs.

The helper now fails closed with three explicit **resource** ceilings:

- **10,000** input observations, stopping at the 10,001st item even for an
  infinite generator;
- **100,000** requested bootstrap resamples, rejected before reading an
  observation;
- **20,000,000** total resampled observations, calculated as
  `sample_count * n_resamples`, rejected before calling the statistic or RNG.

These are limits on diagnostic computation, **not** statistical sample-size
thresholds. They leave the default 2,000-resample method and all ordinary
in-budget seeded intervals unchanged. Valid integer seeds, the chosen
percentile estimator, task-keyed pairing and retained failed-task denominator
rules are unaffected. Unbounded-input and excessive-work synthetic regressions
run in both the targeted diagnostic pytest suite and the dependency-free
pre-install CI gate.

This change does not touch frozen September treatment or evaluator data,
replay treatments, revise any designated-primary effect estimate or inference,
or create human observations. The five-task pilot remains diagnostic;
frozen designated-primary automated results retain their post-collection
analysis-plan, fixed-order and evaluator-policy qualifications; retrospective
sensitivity analyses remain exploratory. Human ratings, agreement and
automated–human reconciliation remain pending, as does recovery of
independently authenticated original reports and traces.
