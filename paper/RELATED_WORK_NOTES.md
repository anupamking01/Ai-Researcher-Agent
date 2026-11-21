# Related Work Notes

This is a working literature map, not final manuscript prose. Verify every bibliographic detail again when preparing the paper.

## Deep-research-agent benchmarks

### Deep Research Bench: Evaluating AI Web Research Agents

- arXiv: 2506.06287
- URL: https://arxiv.org/abs/2506.06287
- Key idea: 89 multi-step web research tasks plus a frozen RetroSearch environment to make evaluations reproducible over time.
- Relevance: provides a strong example of controlled evaluation for changing-web research agents.
- Difference from our planned study: our central question is not benchmark construction; it is how a fixed resource budget should be allocated across planning, retrieval depth, and verification.

### DeepResearch Bench: A Comprehensive Benchmark for Deep Research Agents

- arXiv: 2506.11763
- URL: https://arxiv.org/abs/2506.11763
- Key idea: 100 expert-crafted PhD-level research tasks across 22 fields with report-quality and citation-oriented evaluation.
- Relevance: candidate source of public tasks/evaluation methodology if licensing and contamination concerns are addressed.
- Difference: benchmark/report evaluation rather than an equal-budget stage-wise systems ablation.

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
- Difference: our question is the marginal value of verification relative to planning/retrieval when the overall resource budget is constrained.

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

### Budget-Aware Tool-Use Enables Effective Agent Scaling

- arXiv: 2511.17006
- URL: https://arxiv.org/abs/2511.17006
- Key idea: explicit tool-budget awareness and adaptive planning/verification improve cost-performance scaling for web-search agents.
- Relevance: closest work to the resource-allocation framing.
- Difference to test carefully: rather than proposing a learned or adaptive budget-allocation policy, our first study performs controlled stage-wise interventions under comparable budgets and asks which component creates the strongest marginal return.

### One Policy, Any Budget: Internalizing Budget-Aware Search via Reinforcement Learning

- arXiv: 2609.00813
- URL: https://arxiv.org/abs/2609.00813
- Key idea: reinforcement-learning approach to a single policy that adapts to changing search budgets.
- Relevance: very recent evidence that budget-aware search is moving quickly; final manuscript must explicitly distinguish itself from training a budget-aware policy.

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

A defensible empirical gap to investigate is:

> Existing work has separately advanced deep-research benchmarking, failure diagnosis, verification, and budget-aware tool use. Less clear is the marginal return of spending a fixed research budget at different stages of the same end-to-end pipeline. We therefore conduct controlled stage-wise ablations of planning, retrieval depth, and verification, reporting evidence support, report quality, latency, token/tool consumption, and cost on the same tasks.

This statement must be re-checked against additional literature before submission.
