# Exploratory worst-case envelope for the evaluator recovery policy split

**Status:** post-hoc measurement sensitivity; read-only, nonconfirmatory. This is neither a confidence interval nor a repaired experimental design.

## Rationale

The pinned September 2026 workflow and published 40-cell CSV identify a 37+3 evaluator-recovery split. The three recovery cells are **P6V/main-02, P6V/main-08 and P6V/main-10**. The recovery evaluator introduced a zero-source sentinel absent from the original evaluator, and the two revisions cannot be described as byte-identical input policies. This source-level difference is concentrated in one arm. The published CSV does *not* independently authenticate evaluator calls or original reports.

An informative, assumption-transparent stress test is to treat **all three** recovery-phase P6V strict-support rates as unconstrained values in [0, 1], while keeping the other 37 recorded scores fixed. It is deliberately more conservative than treating only the one published `zero_successful_sources` cell as uncertain. It does not assert that any recovered score is wrong.

For the original ten-task equal-report macro contrast, with `R` the three recovered P6V task IDs and `s` each frozen strict-support rate:

- Lower bound: `(sum(s[P6V,t] for t not in R) - sum(s[P6,t] for all t))/10`.
- Upper bound: `lower + |R|/10` (here exactly `3/10`).
- Observed frozen contrast: `(sum(s[P6V,t]) - sum(s[P6,t]))/10`.

These are **algebraic replacement bounds**, not inferential coverage intervals or estimates of actual measurement bias. They apply only under the explicit stipulation that the 37 other recorded cell scores are held unchanged. If those scores are also affected by unobserved provenance or policy differences, the range is not a bound on the underlying true study effect.

## Reproduce without rerunning experiments

From a full-history Git checkout:

```bash
python -m scripts.analyze_evaluator_recovery_policy_bounds
```

The entrypoint first runs the historical recovery-policy source audit and the published SHA-256-pinned **both-input** preflight; it then recaptures the evaluator CSV, verifies its original SHA-256, and computes only arithmetic from the frozen per-cell supported/checked counts using exact rational numbers. CI stores a read-only JSON receipt alongside the historical source audits. Offline tests exercise synthetic rate extremes, paired comparator completeness, status boundaries and malformed counts.

For the existing published input, the frozen automated P6V–P6 macro contrast is **-1/15 ≈ -0.0667**. If all three recovered measurements may independently range from zero to one, the interval spans **-49/240 ≈ -0.2042 to 23/240 ≈ +0.0958**. Its width is exactly **0.3**. Zero lies in this deliberately broad envelope, but this does not change any frozen p-value, support score, hypothesis, analysis plan, or primary inference result. It does not tell us whether a policy-induced difference actually occurred, or in which direction.

## Limitations and research gates

This retrospective sensitivity is **exploratory** and motivated by documented evaluator-source drift, not chosen to improve apparent treatment performance. It does not remove treatment–execution-order aliasing, establish causal effects, prove precollection preregistration, authenticate missing original treatment reports/traces, or supply human validation. The five-task pilot remains diagnostic; the ten-task automated analysis remains frozen and methodologically qualified; this sensitivity is separate; independent blinded human ratings are still absent. Original report/trace custody and verified human packet distribution remain blocked.
