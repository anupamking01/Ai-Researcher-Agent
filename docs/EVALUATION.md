# Evaluation Methodology

The purpose of this evaluation plan is to convert the project from a demo-oriented agent into a reproducible experimental system. No benchmark values are reported here until experiments are actually run.

## Research questions

**RQ1 — Research quality:** Does agentic task decomposition improve answer completeness and source coverage compared with a single-pass research prompt?

**RQ2 — Reliability:** Which failure modes dominate the pipeline: search, browsing, source relevance, synthesis, or citation support?

**RQ3 — Efficiency:** What quality–cost–latency trade-off is produced by different model and orchestration configurations?

**RQ4 — Verification:** Do claim/source verification and repair loops improve support for generated claims enough to justify their additional cost?

## Experimental variants

The initial study should compare at least these variants under the same task set:

| Variant | Planning | Multi-query retrieval | Concurrent browsing | Verification | Purpose |
|---|---:|---:|---:|---:|---|
| Single-pass baseline | No | No | No | No | Establish simple LLM baseline |
| Retrieval baseline | No | Yes | Yes | No | Isolate retrieval benefit |
| Current agent | Yes | Yes | Yes | No | Measure planner/execution workflow |
| + evidence verifier | Yes | Yes | Yes | Yes | Planned reliability extension |

For model comparisons, hold prompts, retrieval settings, and task set constant wherever possible.

## Task set

Use a fixed, versioned task set with a mixture of factual multi-source questions, comparison/synthesis questions, time-sensitive questions, ambiguous prompts, conflicting-source questions, and questions where primary sources are preferable. Store the task set in machine-readable form before running experiments and version changes explicitly.

## Metrics

Track completion rate, source/browse success, unique source/domain coverage, claim support, blinded task-quality rubric scores, latency, prompt/completion tokens, estimated cost, search-query count, and browsed-source count. The `citation_precision_proxy` in `logic/evaluation.py` is deliberately a proxy and should only be used after a fixed human-annotation protocol is applied.

For task quality, a suitable 1–5 rubric includes correctness, completeness, source quality, synthesis/reasoning, and clarity. For higher rigor, use at least two evaluators on a subset and report inter-rater agreement.

## Paired variant comparisons

Variants should be run on the **same task IDs** whenever possible. Comparing only two global averages can hide task difficulty: a candidate may look better simply because it was evaluated on easier prompts. For every scalar metric where larger is better, align baseline and candidate values by task ID and report:

- number of paired tasks;
- mean per-task delta (`candidate - baseline`);
- median per-task delta;
- standard deviation of per-task deltas;
- task-level wins, ties, and losses.

`logic.evaluation.paired_metric_comparison` implements this descriptive summary without external dependencies. For metrics where smaller is better (for example latency or cost), either negate the metric before comparison or clearly interpret negative deltas as improvements. Do not treat win counts or descriptive deltas as statistical significance.

If a task is missing from one variant because of a failed run, report the missingness and completion-rate difference separately rather than silently dropping failures until both systems appear successful.

## Ablation plan

When verification features are added, remove one component at a time: task decomposition, source deduplication, concurrent browsing, evidence verification, repair loop, and adaptive stopping/source budget. Report both absolute metrics and paired change relative to the full system.

## Failure taxonomy

Assign failed or low-quality runs one primary category: `planning_error`, `search_failure`, `browse_failure`, `irrelevant_retrieval`, `insufficient_evidence`, `synthesis_error`, `unsupported_claim`, `citation_mismatch`, `provider_error`, or `timeout_or_budget`. Keep representative traces for qualitative analysis.

## Reproducibility checklist

Record date/time, git commit SHA, task-set version, provider/model identifier, model parameters, search provider/result limit, maximum source budget, prompt version, runtime environment where relevant, raw traces, and scoring-script version.

## Statistical reporting

For a sufficiently large task set, report means with dispersion rather than only point estimates. When comparing variants over the same tasks, use paired comparisons. The repository should not report statistical significance unless the assumptions and test are clearly documented.

## Result reporting template

| Variant | Completion | Quality | Claim support | Sources | Latency | Tokens | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| Single-pass | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Retrieval baseline | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Current agent | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| + verifier | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

`TBD` is intentional. Replace values only with reproducibly measured results.
