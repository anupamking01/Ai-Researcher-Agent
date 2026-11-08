# Main-study paired-analysis numeric input integrity

**Scope:** Defensive, offline input validity at `scripts/analyze_main_study.py`'s
treatment/evaluator CSV join. This adds rejection rules for damaged or
contradictory research measurements; it does **not** re-estimate the historical
main study, revise the frozen analysis plan or canonical published outputs,
or authenticate unavailable original reports and traces.

## Source-to-analysis contract

The analysis now requires finite nonnegative numeric measurements rather than
allowing Python to propagate `NaN`, `Infinity`, negative costs or malformed
values into means, intervals, or the descriptive cost-quality frontier.
Evaluator claim counts must be **integral, nonnegative, bounded by the frozen
12-claim cap**, and partition exactly into supported, partially supported,
unsupported, and contradicted claims. Fractional values are **not rounded**
into ostensibly observed counts. The primary `strict_support_rate` column is
independently reconciled with `supported / claims_checked` to absolute
tolerance `1e-12` (zero relative tolerance), so a modified but plausible
rate cannot silently disagree with its own source counts. Where present,
the main-study treatment CSV's `posthoc_claims_checked` and
`posthoc_strict_support_rate` mirror fields must agree with the common
evaluator. These are consistency checks, not new measurements.

Small representational noise from binary floating-point serialization is
accepted. These rules do not demonstrate that the counts themselves reflect
original reports, that evaluator policies were identical between recovery
and earlier cells, or that outcomes were prospectively preregistered.
They must be combined with the independent historical provenance/custody
audits and the existing immutable input-manifest checks.

## Reproduce without rerunning experiments

```bash
python -m pytest -q tests/test_main_study_numeric_integrity.py
```

These tests use a synthetic one-task CSV join and deliberately corrupted
cells. They make no network or model calls and do not write the frozen
`outputs/main_study_inference.json` or
`paper/MAIN_STUDY_INFERENCE.md` artifacts. Do **not** invoke the
inference command against canonical outputs merely to claim a refreshed
statistical result; the published September results remain unchanged.

The original live-web 10-task automated main study retains its post-collection
analysis-plan chronology, fixed-order temporal confounding, and evaluator
recovery comparability qualifications. The five-task pilot is diagnostic.
Retrospective envelope/sensitivity analyses remain exploratory. Blinded
human evaluation remains unperformed pending authenticated source custody
and real independent annotations.
