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

Use a fixed, versioned task set with a mixture of:

- factual multi-source questions;
- comparison/synthesis questions;
- time-sensitive questions where current web evidence matters;
- ambiguous prompts that require careful scope interpretation;
- questions with conflicting sources;
- questions where primary sources are preferable to secondary summaries.

Store the task set in machine-readable form before running experiments. Do not modify tasks after seeing results unless the new version is explicitly labeled.

## Metrics

### 1. Completion rate

Fraction of runs that finish and produce a report.

### 2. Source success rate

For each run:

`(retrieved sources - failed sources) / retrieved sources`

This separates browsing reliability from LLM quality.

### 3. Source coverage

Count unique sources used by a report. When possible, also record unique domains and primary-source proportion.

### 4. Claim support / citation precision

Sample or annotate atomic claims in the final report and label each as:

- supported by cited evidence;
- partially supported;
- unsupported;
- contradicted by cited evidence.

The `citation_precision_proxy` in `logic/evaluation.py` is deliberately named a proxy. It should only be used after a fixed human-annotation protocol is applied.

### 5. Task quality

Use a blinded rubric such as:

- correctness: 1–5;
- completeness: 1–5;
- source quality: 1–5;
- synthesis / reasoning: 1–5;
- clarity: 1–5.

For higher rigor, use at least two evaluators on a subset and report inter-rater agreement.

### 6. Efficiency

Track:

- wall-clock latency;
- prompt tokens;
- completion tokens;
- estimated model cost;
- number of search queries;
- number of browsed sources.

Quality should be discussed together with cost and latency rather than in isolation.

## Ablation plan

When verification features are added, remove one component at a time:

1. no task decomposition;
2. no source deduplication;
3. sequential instead of concurrent browsing;
4. no evidence verifier;
5. no repair loop;
6. no adaptive stopping / fixed source budget.

Report both absolute metrics and change relative to the full system.

## Failure taxonomy

Every failed or low-quality run should be assigned one primary failure category:

- `planning_error`
- `search_failure`
- `browse_failure`
- `irrelevant_retrieval`
- `insufficient_evidence`
- `synthesis_error`
- `unsupported_claim`
- `citation_mismatch`
- `provider_error`
- `timeout_or_budget`

Keep representative traces for qualitative analysis.

## Reproducibility checklist

Record for each experiment:

- date/time;
- git commit SHA;
- task-set version;
- model/provider and exact model name;
- model parameters such as temperature;
- search provider and result limit;
- maximum source budget;
- prompt version;
- hardware/runtime environment where relevant;
- raw run traces;
- scoring script version.

## Statistical reporting

For a sufficiently large task set, report means with dispersion (standard deviation or confidence intervals) rather than only point estimates. When comparing two variants over the same tasks, use paired comparisons where possible.

The repository should not report statistical significance unless the assumptions and test are clearly documented.

## Result reporting template

| Variant | Completion | Quality | Claim support | Sources | Latency | Tokens | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| Single-pass | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Retrieval baseline | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Current agent | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| + verifier | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

`TBD` is intentional. Replace values only with reproducibly measured results.
