# Pilot v1 Canonical Results

## Scope and provenance

This file records the **diagnostic five-task pilot**, not the main study and not a publication-ready benchmark result.

The canonical 15-run dataset contains:

- the 13 successful D6/P6/P6V traces from GitHub Actions run `34377707838` (`144ed06b5b2826bf6b7d7b5fcf1c982f518c3d03`);
- only the two missing traces, `P6V/pilot-04` and `P6V/pilot-05`, from targeted GitHub Actions run `34388324051` (`508027ae98ea4bee79773fdda2bf1bfdb0f3f64d`).

The two original failed P6V traces from run `34377707838` are excluded because they terminated before experimental work when the API account exhausted prepaid credit. They are retained in the original workflow artifact as infrastructure-failure records and are not silently deleted.

Both selected workflow manifests used the same research configuration for the relevant runs:

- task set: `pilot-v1-2026-09-08`;
- smart model: `gpt-5.6-terra`;
- fast model: `gpt-5.6-luna`;
- temperature: `1`;
- source/browse-call budget: `6`;
- browse timeout: `60 s`;
- run timeout: `480 s`;
- maximum concurrent browsers: `2`.

The targeted rerun changed only the selected variant/task IDs needed to replace the two credit-exhaustion failures.

## Validation

The canonical dataset passes the following checks:

- exactly 15 unique `(variant, task)` pairs: 5 D6, 5 P6, 5 P6V;
- all 15 selected traces completed;
- all 15 used source budget 6;
- all 15 have provider-complete usage accounting;
- all 15 use the frozen cost estimator successfully;
- all selected traces use Terra/Luna with temperature 1;
- all five P6V verifier runs have `verification_status = ok`;
- no selected run timed out;
- every selected run retrieved at least one successful source.

## Descriptive pilot results

Values are means across the five tasks.

| Variant | n | Successful sources | Search calls | Model calls | Total tokens | Est. cost/run | Latency (s) | Report words | Claim support |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| D6 | 5 | 3.0 | 1.0 | 5.6 | 16,452.0 | $0.0524 | 93.8 | 2,657.0 | not measured |
| P6 | 5 | 3.4 | 4.0 | 7.0 | 20,721.6 | $0.0574 | 127.6 | 2,677.8 | not measured |
| P6V | 5 | 4.6 | 4.0 | 8.8 | 32,793.8 | $0.0900 | 126.7 | 2,669.8 | 0.84 macro |

Total estimated cost across the canonical 15 runs is approximately **$0.9992**: D6 `$0.2622`, P6 `$0.2871`, and P6V `$0.4499`.

For P6V, the verifier checked **88 claims** across the five reports: 75 supported, 9 partially supported, 4 unsupported, and 0 contradicted. The macro-average per-report fully-supported rate is **84.0%**; the micro-average across all checked claims is **85.23%**. Per-task fully-supported rates were 0.85, 0.85, 0.85, 0.75, and 0.90.

## Paired operational deltas

Because all three variants use the same five task IDs, operational quantities can be compared task-by-task. These are descriptive pilot deltas only.

### P6 - D6

Mean paired difference:

- successful sources: **+0.4**;
- model calls: **+1.4**;
- total tokens: **+4,269.6**;
- estimated cost: **+$0.00498/run**;
- latency: **+33.88 s**;
- report length: **+20.8 words**.

Planning therefore incurred clear search/latency overhead in this pilot. The source-success effect was small and heterogeneous across tasks (`-2, -1, 0, +4, +1`), so the five-task pilot does not establish that planning reliably improves retrieval success.

### P6V - P6

Mean paired difference:

- successful sources: **+1.2**;
- model calls: **+1.8**;
- total tokens: **+12,072.2**;
- estimated cost: **+$0.03256/run**;
- latency: **-0.98 s**;
- report length: **-8.0 words**.

The higher successful-source count should **not** be attributed causally to verification: retrieval happens before verification, and two P6V tasks were completed in a later targeted rerun after credit restoration. Live-web availability can vary across execution windows.

The useful pilot result is therefore that bounded verification executed reliably and produced structured claim-support measurements, while adding substantial token and dollar cost. Whether it improves report quality or evidence support relative to P6 cannot yet be answered because D6/P6 reports were not independently passed through the same evaluator.

## Interpretation limits

Do not promote these numbers to the paper's main empirical claims yet.

1. `n = 5` tasks is diagnostic and too small for strong generalization.
2. The pilot lacks blinded human report-quality evaluation.
3. Claim-support labels are available only for P6V, so there is no fair cross-variant support comparison.
4. Two P6V tasks were rerun later because of an external billing failure; the agent configuration was unchanged, but live-web conditions may differ.
5. Browse success is partly an infrastructure/web-availability outcome, not solely an agent-quality measure.
6. The current pilot compares D6, P6, and P6V only; it does not answer the planned retrieval-depth ablation (3/6/12 sources).

## Go/no-go conclusion

**Go for a larger study, but not for publication claims from this pilot alone.**

The pilot demonstrates that the instrumentation, fixed browse-call budget, provider usage accounting, cost estimation, source-failure handling, browser safeguards, and bounded verifier can execute end-to-end with a complete trace set. The next study should freeze a larger task set, apply the same support evaluator to reports from every compared variant (or use blinded human claim annotation), and then evaluate the planned retrieval-depth and quality-cost comparisons.
