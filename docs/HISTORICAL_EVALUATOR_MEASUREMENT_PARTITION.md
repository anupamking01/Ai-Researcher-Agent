# Historical evaluator measurement partition — frozen-summary concordance

**Classification:** retrospective, read-only measurement-provenance audit. Not a new experiment, quality score, causal correction, confirmatory test or human validation.

## Motivation and reproduction

The September 11 treatment evaluator and September 13 evaluator-only recovery used different input-admissibility policies. The historical recovery workflow required 37 already-present evaluator records and exactly three missing P6V cells. The original evaluator rejected empty retrieved evidence; the recovery evaluator added an explicit zero-evidence sentinel. That difference is **arm-concentrated**, and the 40 outputs must not be described as having been obtained using byte-identical evaluators.

From a full-history checkout, run:

```bash
python -m scripts.audit_historical_evaluator_measurement_partition
```

This audit first verifies immutable historical Git source and evaluator-policy differences, then runs the existing published-SHA-pinned 40-cell treatment/evaluator CSV integrity preflight. It separately captures and checks the published evaluator CSV bytes and matches its recorded per-cell evidence-status metadata with the three cells explicitly named by the historical recovery workflow. Failures include changed bytes, inconsistent/missing/duplicate cells, extra/missing columns, reused run IDs, or changed recovery-status fields. Its receipt is retained in the existing offline historical-source CI.

## Recorded split (not independently authenticated historical execution)

| Field | Recorded result |
| --- | --- |
| Published evaluator-summary rows | 40 |
| Expected originally cached evaluations in historical recovery workflow | 37 |
| Expected evaluator-only recoveries | 3 |
| Recovery cells | P6V/main-02, P6V/main-08, P6V/main-10 |
| P6V cells covered by recovery | 3 of 10 |
| D3, D6, P6 cells covered by recovery | 0 of 30 |
| P6V/main-02 and main-08 published `evidence_status` | `retrieved_evidence` |
| P6V/main-10 published `evidence_status` | `zero_successful_sources` |
| Legacy blank `evidence_status` cells | 37 |

The **published CSV records** a zero-successful-source sentinel for P6V/main-10. This does **not** independently authenticate its treatment trace, exact prompt, provider request, or evaluator completion. The 37 blank legacy statuses are *unspecified*, not affirmative `retrieved_evidence` assertions. Retained status metadata are not original report or trace evidence.

The arm-concentrated policy difference is a measurement-comparability limitation, especially for the P6V-versus-P6 automated comparison. It neither establishes the direction/magnitude of bias nor justifies excluding, selecting, rerunning or re-scoring any cells. The frozen inference, p-values, confidence intervals, original measured outcomes and human-ratings protocol remain untouched.

The pilot is diagnostic; the automated ten-task analysis remains frozen with post-collection statistical-plan timing and fixed-order confounding qualifications; this audit is retrospective provenance analysis; human validation is not yet available. Original 40 report/trace custody, independent source authentication, and blinded annotator readiness remain open gates.
