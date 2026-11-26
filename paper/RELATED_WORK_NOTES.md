# Related Work Notes

This is a working literature map, not final manuscript prose. Verify every bibliographic detail again when preparing the paper.

## Deep-research-agent benchmarks

### Deep Research Bench: Evaluating AI Web Research Agents

- arXiv: 2506.06287
- URL: https://arxiv.org/abs/2506.06287
- Key idea: 89 multi-step web research tasks plus a frozen RetroSearch environment to make evaluations reproducible over time.
- Relevance: provides a strong example of controlled evaluation for changing-web research agents.
- Difference from VERA: benchmark construction is not our contribution. VERA compares four fixed pipeline configurations on a selected live-web task set, with scheduled browse-call caps rather than a shared total resource budget. RetroSearch is a useful future reproducibility precedent, not the environment used for the historical VERA treatments.

### DeepResearch Bench: A Comprehensive Benchmark for Deep Research Agents

- arXiv: 2506.11763
- URL: https://arxiv.org/abs/2506.11763
- Key idea: 100 expert-crafted PhD-level research tasks across 22 fields with report-quality and citation-oriented evaluation.
- Relevance: candidate source of public tasks/evaluation methodology if licensing and contamination concerns are addressed.
- Difference: benchmark/report evaluation rather than VERA's staged pipeline contrasts. Their reported human alignment does not validate VERA's separate automated support measure.

### ReportBench: Evaluating Deep Research Agents via Academic Survey Tasks

- arXiv: 2508.15804
- URL: https://arxiv.org/abs/2508.15804
- Key idea: evaluates deep-research reports against high-quality survey literature, emphasizing citation quality and statement faithfulness.
- Relevance: useful for claim/citation evaluation methodology.
- Difference: our study focuses on intervention location and resource allocation inside the agent pipeline.

### FINDER / DEFT: How Far Are We from Genuinely Useful Deep Research Agents?

- arXiv: 2512.01948
- URL: https://arxiv.org/abs/2512.01948
- Key idea: human-curated research tasks, checklist-based evaluation, and a fine-grained failure taxonomy for deep research agents.
- Relevance: means a generic 'new failure taxonomy' is not a defensible novelty claim for our work.
- Difference: we use failure categories operationally to understand how strengthening one stage moves failures elsewhere.

### DREAM: Deep Research Evaluation with Agentic Metrics

- arXiv: 2602.18940
- URL: https://arxiv.org/abs/2602.18940
- Key idea: argues that evaluation itself should be agentic to detect temporal/factual problems missed by static evaluators.
- Relevance: motivates treating automated judging as a secondary measure unless validated against human judgment.

## Verification

### Inference-Time Scaling of Verification: Self-Evolving Deep Research Agents via Test-Time Rubric-Guided Verification

- arXiv: 2601.15808
- URL: https://arxiv.org/abs/2601.15808
- Key idea: DeepVerifier uses rubric-guided verification and iterative refinement for deep research agents.
- Relevance: means 'adding a verifier' alone is not novel.
- Difference: VERA compares the addition of treatment-time verification at the same scheduled browse cap (P6V versus P6); it does not hold total inference cost fixed or identify a general optimal allocation.

### DeepSciVerify: Verifying Scientific Claim--Citation Alignment via LLM-Driven Evidence Escalation

- arXiv: 2605.27710
- URL: https://arxiv.org/abs/2605.27710
- Key idea: selectively escalates uncertain scientific claim/citation checks from abstract-level to passage-level evidence.
- Relevance: useful design reference for efficient evidence verification.

### FACTOR: Not All Claims Are Equally Risky

- arXiv: 2606.22474
- URL: https://arxiv.org/abs/2606.22474
- Key idea: adaptive verification based on claim-level hallucination risk in long-form factual generation.
- Relevance: means risk-aware selective verification is already an active research direction.

## Budget-aware tool use

### Budget-Aware Tool Use Enables Effective Agent Scaling

- Liu et al., arXiv: 2511.17006v2 (17 August 2026; arXiv records acceptance to COLM 2026).
- Version checked: https://arxiv.org/abs/2511.17006v2
- Key idea: Budget Tracker exposes remaining tool capacity to an agent; BATS adjusts planning and verification dynamically. The study also defines a cost measure incorporating token and tool expenditure.
- Relevance: a close precedent for the resource-allocation framing, including both planning and verification; it precludes a broad claim that these have not previously been studied together under budgets.
- Difference: VERA's historical study uses fixed pipeline configurations, not BATS, a budget-aware policy, or an equal-total-cost intervention. The cost measures and endpoints are not demonstrated comparable; no cross-paper performance ranking or superiority claim is supported.

### Thinking vs. Doing: Agents that Reason by Scaling Test-Time Interaction

- Shen et al., arXiv: 2506.07976v2 (10 June 2025).
- Version checked: https://arxiv.org/abs/2506.07976v2
- Key idea: extends the interaction horizon rather than only increasing per-step reasoning; studies prompting and curriculum-based online reinforcement learning on web-agent tasks.
- Relevance: a precedent for distinguishing environmental interaction from internal inference. VERA changes a scheduled unique-URL browse-call cap, not the whole interaction horizon, and does not train an adaptive policy.

### One Policy, Any Budget: Internalizing Budget-Aware Search via Reinforcement Learning

- arXiv: 2609.00813
- URL: https://arxiv.org/abs/2609.00813
- Key idea: reinforcement-learning approach to a single policy that adapts to changing search budgets.
- Relevance: a contemporaneous example (first submitted 1 September 2026) of training a budget-adaptive search policy. VERA does not train or evaluate AnySearch; its fixed configuration comparisons are a different empirical question.

## Retrieval evaluation

### RAGCHECKER

- arXiv: 2408.08067
- URL: https://arxiv.org/abs/2408.08067
- Key idea: fine-grained diagnostic metrics for retrieval and generation modules in RAG systems.
- Relevance: useful methodological precedent for module-level diagnosis rather than only end-to-end scoring.

### BRIGHT

- arXiv: 2407.12883
- URL: https://arxiv.org/abs/2407.12883
- Key idea: reasoning-intensive retrieval benchmark.
- Relevance: potential supplemental retrieval stress test, though it is not a long-form deep-research benchmark.

## Intended gap statement

Avoid claiming that deep-research evaluation, failure taxonomies, verification, or budget awareness are new.

## Source-checked positioning and claim boundary (26 November 2026)

The primary abstracts for [FutureSearch's Deep Research Bench](https://arxiv.org/abs/2506.06287), [Du et al.'s DeepResearch Bench](https://arxiv.org/abs/2506.11763v1), [BATS](https://arxiv.org/abs/2511.17006v2), [test-time interaction](https://arxiv.org/abs/2506.07976v2), and [AnySearch](https://arxiv.org/abs/2609.00813) were checked for this positioning update. This is a targeted comparison, not an exhaustive systematic review or independent reproduction of their results.

| VERA contrast | Planned source change | What must not be inferred |
| --- | --- | --- |
| D6 minus D3 | Scheduled unique-URL browse cap 3 to 6; direct mode in both | Six successful sources, equal total compute, or the causal return of each additional source |
| P6 minus D6 | Planner rather than direct mode, both capped at six browses | Equal token/search/model-call costs or an isolated causal planning effect |
| P6V minus P6 | Treatment-time verification added, both planner and six-browse cap | Equal inference cost, a common evaluator-policy guarantee, or proof verification harms quality |

The planned settings are source-audited in [historical variant factors](../docs/HISTORICAL_VARIANT_FACTOR_SOURCE_AUDIT.md); [realized retrieval exposure](../docs/MAIN_STUDY_RETRIEVAL_EXPOSURE.md) is a separate exploratory analysis of retained summary counts. The fixed within-task execution order aliases treatment and position ([design audit](../docs/MAIN_STUDY_DESIGN_IDENTIFIABILITY.md)). Three recovered common-evaluator cells are concentrated in P6V ([measurement partition](../docs/HISTORICAL_EVALUATOR_MEASUREMENT_PARTITION.md)).

A bounded description for a future manuscript is:

> Prior work has developed research benchmarks and budget-adaptive agents. VERA contributes an auditable, task-paired case study of four fixed web-research pipeline configurations that vary scheduled retrieval capacity, planning and treatment-time verification. The retained automated evidence describes strict support and recorded resource use on ten selected live-web tasks; it does not identify causal marginal returns under a common total budget, establish an optimal policy or rank VERA against external benchmarks.

The five-task pilot is diagnostic. The automated analysis is frozen but post-collection, with designated primary contrasts and unverified outcome blinding at freeze ([required reporting cover](MAIN_STUDY_REPORTING_COVER.md)). Retrospective analyses are exploratory. Original report/trace custody and genuine blinded human report-quality ratings and agreement remain pending; do not describe report quality as a completed human outcome. No external benchmark scores, new VERA measurements or treatment reruns enter this literature update. Recheck additional literature before submission; do not claim novelty by absence from this limited map.
