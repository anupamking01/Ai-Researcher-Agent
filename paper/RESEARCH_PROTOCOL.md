# Research Protocol: Budget Allocation in Web-Research Agents

## Working title

**Where Should a Research Agent Spend Its Budget? Stage-Wise Ablations of Planning, Retrieval, and Verification in Web Research**

## Goal

Turn the existing AI Research Agent into a reproducible empirical study of how limited inference/tool budgets should be allocated across three stages of a web-research pipeline:

1. planning / query decomposition;
2. retrieval / source acquisition;
3. claim-to-evidence verification and repair.

The study should not claim a new benchmark or a universally superior agent architecture. Its intended contribution is a controlled, equal-budget comparison that measures the marginal quality gained from spending additional resources at different stages of the pipeline.

## Motivation

Deep-research systems are increasingly evaluated end-to-end, but practitioners still face a concrete systems question: given a fixed latency/token/tool budget, which stage deserves additional computation? More searching can increase evidence coverage but also introduce irrelevant context; more planning can improve query diversity but add inference overhead; verification can improve support but consumes additional model calls.

The experiment therefore treats agent quality as a constrained resource-allocation problem rather than only a maximum-accuracy problem.

## Primary research question

Under a fixed total research budget, how should computation be distributed among planning, retrieval, and verification to maximize evidence-supported report quality?

## Secondary research questions

**RQ1 — Planning:** At equal total budget, does explicit query decomposition improve report quality relative to directly retrieving from the original question?

**RQ2 — Retrieval depth:** How does increasing the source budget affect completeness, evidence quality, latency, and unsupported-claim rate?

**RQ3 — Verification:** Does claim-level evidence verification improve support enough to justify its token and latency overhead when total budget is held constant?

**RQ4 — Interaction:** Are planning and verification complementary, redundant, or competitive for the same limited budget?

**RQ5 — Failure movement:** When one stage is strengthened, which failure modes disappear and which new bottlenecks become dominant?

## Hypotheses

- **H1:** Planning improves source diversity and completeness most strongly at low-to-medium retrieval budgets.
- **H2:** Retrieval depth has diminishing returns: additional sources eventually add cost faster than supported content.
- **H3:** Verification reduces unsupported claims but may reduce total coverage when the overall budget is fixed.
- **H4:** The best quality-cost trade-off will use moderate planning and retrieval plus selective verification rather than maximizing any one stage independently.

These are hypotheses only. They must be revised or rejected according to measured results.

## Experimental factors

### Factor A: planning

- `direct`: use the original research question as the retrieval query or minimal query set;
- `planner`: use LLM-based query decomposition.

### Factor B: source budget

Initial levels:

- `small`: 3 successfully browsed sources maximum;
- `medium`: 6 successfully browsed sources maximum;
- `large`: 12 successfully browsed sources maximum.

The exact values may be adjusted during pilot experiments, but must then be frozen before the main run.

### Factor C: verification

- `none`: synthesize report directly from gathered evidence;
- `verify`: decompose the generated report into atomic factual claims, check each sampled/eligible claim against cited evidence, and flag unsupported claims;
- `verify_repair`: verify and perform one bounded repair pass for unsupported claims.

For the first paper iteration, `verify` and `verify_repair` may be collapsed into a single verifier condition if implementation time is limited.

## Equal-budget principle

A central requirement of the paper is that comparisons must not quietly give one variant much more computation.

For every run record:

- prompt tokens;
- completion tokens;
- number of model calls;
- number of search calls;
- number of browsed URLs;
- wall-clock latency;
- estimated USD cost.

Primary comparisons should either:

1. operate under an explicit total budget cap; or
2. report quality-cost Pareto frontiers rather than comparing quality alone.

## Variants

Minimum viable matrix:

| ID | Planning | Source budget | Verification |
|---|---|---:|---|
| D3 | direct | 3 | none |
| D6 | direct | 6 | none |
| D12 | direct | 12 | none |
| P3 | planner | 3 | none |
| P6 | planner | 6 | none |
| P12 | planner | 12 | none |
| D6V | direct | 6 | verify |
| P6V | planner | 6 | verify |

If time and budget allow, extend verification to source budgets 3 and 12.

## Task set

Do not invent benchmark scores or alter tasks after seeing the main results.

Use a versioned task manifest containing a mixture of:

- multi-source factual synthesis;
- comparative research;
- questions requiring primary-source preference;
- conflicting-source questions;
- time-sensitive questions;
- long-form research/report prompts.

Preferred evaluation strategy:

1. use an established public deep-research benchmark where licensing permits;
2. supplement it with a small, separately labeled original task set for live-web robustness;
3. never merge test tasks into training/prompt-tuning material.

Before running the main study, save the exact task IDs and benchmark version in `experiments/manifests/`.

## Primary metrics

### Evidence support

Atomic factual claims should be labeled as:

- supported;
- partially supported;
- unsupported;
- contradicted.

Primary claim-support metric:

`fully_supported_claims / all_annotated_factual_claims`

Do not call this factual accuracy unless the annotation protocol actually verifies truth beyond citation support.

### Report quality

Blind rubric, 1–5 each:

- correctness;
- completeness;
- source quality;
- synthesis/reasoning;
- clarity.

### Efficiency

- latency;
- total tokens;
- model calls;
- web/search calls;
- successfully browsed sources;
- estimated cost.

### Retrieval/source metrics

- unique source count;
- unique domain count;
- browse success rate;
- primary-source proportion where labels are available;
- duplicate-source rate.

## Secondary metrics

- completion rate;
- citation count;
- unsupported claim count;
- claim support per 1,000 tokens;
- quality score per dollar;
- quality score per minute;
- failure category distribution.

## Failure taxonomy

Use the existing repository taxonomy as an operational annotation scheme rather than claiming the taxonomy itself is novel:

- planning_error;
- search_failure;
- browse_failure;
- irrelevant_retrieval;
- insufficient_evidence;
- synthesis_error;
- unsupported_claim;
- citation_mismatch;
- provider_error;
- timeout_or_budget.

Allow one primary and optionally one secondary label per low-quality run.

## Annotation protocol

At least a subset of reports should be independently assessed by two human annotators.

For claim support:

1. split the final report into atomic externally verifiable claims;
2. ignore purely stylistic statements and clearly marked opinions;
3. inspect the cited/source evidence available to the agent;
4. assign the four-level support label;
5. resolve disagreements after recording the initial independent labels.

Report inter-rater agreement on the independently annotated subset.

Automated LLM judging can be used as a secondary metric, but human evaluation should remain the reference for the main claim-support analysis unless a validated benchmark evaluator is used.

## Statistical analysis

Because the same tasks are evaluated under multiple variants, prefer paired analyses.

Minimum reporting:

- mean;
- median where distributions are skewed;
- standard deviation or bootstrap confidence intervals;
- per-task paired differences between key variants.

Do not report p-values unless the selected test and its assumptions are documented in the analysis script.

Important comparisons:

- `P6 - D6`: value of planning at equal source budget;
- `D12 - D6`: marginal value of additional retrieval;
- `P6V - P6`: value/cost of verification;
- Pareto comparison of all variants on report quality vs. cost/latency.

## Reproducibility requirements

Every main-study run must record:

- task ID;
- variant ID;
- timestamp;
- git commit SHA;
- prompt version;
- model/provider exact identifier;
- temperature and other decoding parameters;
- search provider;
- source budget;
- raw URLs;
- browse failures;
- raw model output;
- token usage;
- latency;
- estimated cost;
- evaluator version.

Raw traces should be retained even when a run fails.

## Paper structure

1. Abstract
2. Introduction
3. Related Work
4. System and Experimental Factors
5. Evaluation Protocol
6. Results
7. Stage-Wise Ablations
8. Failure Analysis
9. Quality-Cost Pareto Analysis
10. Limitations and Threats to Validity
11. Conclusion
12. AI Assistance Disclosure (venue-dependent / required when applicable)

## Contributions to claim only if demonstrated

A final manuscript may claim the following only after experiments support them:

1. a controlled stage-wise ablation of planning, retrieval depth, and verification in a web-research agent;
2. an equal-budget analysis of quality, evidence support, latency, and cost;
3. empirical evidence about interactions and diminishing returns across research-agent stages;
4. an open reproducibility package containing configurations, traces, evaluation scripts, and analysis.

Do not claim state-of-the-art performance unless directly and fairly demonstrated.

## Immediate implementation order

1. add normalized run-trace logging to the end-to-end pipeline;
2. make source budget configurable;
3. implement a direct/no-planner baseline;
4. implement claim extraction and evidence-verification output without repair;
5. freeze pilot task manifest;
6. run a 5-task pilot across D6, P6, and P6V;
7. inspect failures and lock experiment settings;
8. run the full matrix;
9. perform human annotation on a predeclared subset;
10. generate tables/plots from saved traces;
11. write the manuscript from measured results only.

## Stop/go gate for ICLR 2027

Do not submit merely to meet the deadline. A genuine submission should exist by the decision gate with:

- implemented core variants;
- frozen task set;
- completed main experimental runs;
- reproducible saved traces;
- at least preliminary human evaluation;
- at least one non-trivial empirical finding;
- complete paper draft with limitations and AI-use disclosure.

If these conditions are not met, release a high-quality preprint after the experiments are complete and target a later suitable venue.