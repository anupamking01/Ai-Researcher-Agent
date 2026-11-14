# Main-study inferential results

Generated offline by `scripts/analyze_main_study.py` under the frozen rules in `paper/ANALYSIS_PLAN.md`.

## Variant means

| Variant | Strict support | Broad support | Sources | Tokens | Treatment cost | Latency (s) | Zero-evidence runs |
|---|---:|---:|---:|---:|---:|---:|---:|
| D3 | 0.8375 | 0.9208 | 1.80 | 10794.5 | $0.0476 | 64.8 | 0 |
| D6 | 0.8167 | 0.9292 | 3.30 | 16532.9 | $0.0533 | 68.4 | 0 |
| P6 | 0.7875 | 0.9208 | 3.10 | 17682.9 | $0.0555 | 93.0 | 0 |
| P6V | 0.7208 | 0.8417 | 2.80 | 22807.7 | $0.0845 | 111.2 | 1 |

## Primary paired contrasts: strict support

### D6_minus_D3_retrieval_depth

- Mean paired difference: **-0.0208**
- Median paired difference: 0.0000
- Paired-bootstrap 95% CI: [-0.0667, 0.0292]
- Exact two-sided sign-flip p: 0.5938
- Holm-adjusted p across the three primary contrasts: 1.0000
- Paired d_z: -0.2483
- Task direction: 2 positive / 4 negative / 4 tied

### P6_minus_D6_planning

- Mean paired difference: **-0.0292**
- Median paired difference: 0.0000
- Paired-bootstrap 95% CI: [-0.1000, 0.0500]
- Exact two-sided sign-flip p: 0.5625
- Holm-adjusted p across the three primary contrasts: 1.0000
- Paired d_z: -0.2290
- Task direction: 2 positive / 4 negative / 4 tied

### P6V_minus_P6_verification

- Mean paired difference: **-0.0667**
- Median paired difference: 0.0000
- Paired-bootstrap 95% CI: [-0.2958, 0.0792]
- Exact two-sided sign-flip p: 0.8672
- Holm-adjusted p across the three primary contrasts: 1.0000
- Paired d_z: -0.1952
- Task direction: 4 positive / 4 negative / 2 tied

## Cost-quality Pareto view

Non-dominated variants: D3

## Interpretation constraints

- The 10-task set is an original live-web set, not an established public benchmark.
- The common support evaluator is automated; blinded human quality scoring remains necessary.
- Primary inference is limited to the three preregistered strict-support contrasts.
- Live-web availability can vary across treatment executions.
- Later duplicate executions must not replace the primary dataset based on favorable outcomes.
