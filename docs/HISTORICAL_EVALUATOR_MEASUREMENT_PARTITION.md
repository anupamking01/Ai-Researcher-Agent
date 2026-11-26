# Historical evaluator measurement partition — frozen-summary concordance

**Classification:** retrospective, read-only measurement-provenance audit. Not a new experiment, quality score, causal correction, confirmatory test or human validation.

## Motivation and reproduction

The September 11 treatment evaluator and September 13 evaluator-only recovery used different input-admissibility policies. The historical recovery workflow required 37 already-present evaluator records and exactly three missing P6V cells. The original evaluator rejected empty retrieved evidence; the recovery evaluator added an explicit zero-evidence sentinel. That difference is **arm-concentrated**, and the 40 outputs must not be described as having been obtained using byte-identical evaluators.

From a full-history checkout, run:

```bash
python -m scripts.audit_historical_evaluator_measurement_partition
```

This audit first verifies immutable historical Git source and evaluator-policy differences, then runs the existing published-SHA-pinned 40-cell treatment/evaluator CSV integrity preflight. The summary preflight requires **both published CSV SHA-256 pins**; its optional
task-manifest helper is disabled only to avoid importing the Markdown parser
into this deliberately dependency-free historical CI job. The same job runs
the separate full-history original task-manifest freeze audit, and this
partition independently requires the original exact ten task IDs.
It separately captures and checks the published evaluator CSV bytes and matches its recorded per-cell evidence-status metadata with the three cells explicitly named by the historical recovery workflow. Failures include changed bytes, inconsistent/missing/duplicate cells, extra/missing columns, reused run IDs, or changed recovery-status fields. Its receipt is retained in the existing offline historical-source CI.

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

## Historical text-mode versus schema-v2 replay input identity

Both historical evaluator revisions used `Path.read_text(encoding="utf-8")` for Markdown reports and sorted saved query text files. The source-policy audit now verifies the exact two helper ASTs at each pinned revision. Python text-mode reads translate CRLF and standalone CR to LF; the historical evidence reader additionally stripped each query file, omitted empty text, and joined the remaining snippets with two LF characters. In contrast, the current noncanonical schema-v2 replay and archive fingerprint verifier use strict raw UTF-8 decoding. For a synthetic input containing embedded CRLF or CR, the decoded strings (and therefore potentially prompt bytes and hashes) differ. The archive concordance receipt identifies the two text-decoding policies explicitly.

This is a source-level reproducibility qualification, not evidence that any historical input actually contained those line endings. Neither the original nor recovery historical evaluator recorded per-cell prompt fingerprints; a matching schema-v2 replay fingerprint cannot establish what the historical provider received. No existing archive member, evaluator score, frozen input, or analysis output is rewritten, and no evaluator or treatment is rerun. The original raw archive hashes remain distinct from decoded text and provider-request identity.

When both role-pinned archive candidates are available and pass source concordance, the receipt now records `candidate_newline_input_cells_checked` and a sorted `candidate_newline_input_differences` list keyed by treatment and task, distinguishing changed report input from changed joined evidence input. The comparison detects CRLF or standalone CR surviving in the decoded inputs; CR at the stripped boundaries of individual evidence snippets is not counted. An empty list means only that no such difference exists in the inspected candidate inputs under these two decoding rules. This does not authenticate historical prompt bytes, establish which provider inputs were actually used, or imply identical scores. The diagnostic requires the real source archives; synthetic tests are not results for the original study.
