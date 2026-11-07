# Research Protocol: Budget Allocation in Web-Research Agents

## Working title

**Where Should a Research Agent Spend Its Budget? Stage-Wise Ablations of Planning, Retrieval, and Verification in Web Research**

## Goal

Turn the existing AI Research Agent into a reproducible empirical study of how limited inference/tool budgets should be allocated across three stages of a web-research pipeline:

1. planning / query decomposition;
2. retrieval / source acquisition;
3. claim-to-evidence verification and repair.

The study should not claim a new benchmark or a universally superior agent architecture. Its intended contribution is a controlled resource-allocation study that measures the marginal quality gained from spending additional resources at different stages of the pipeline.

## Pilot v1 status and scope

A five-task diagnostic pilot across D6, P6, and P6V is complete. Its canonical data and validation notes are in `paper/PILOT_RESULTS.md` and `experiments/results/pilot_v1_canonical_runs.csv`.

Pilot v1 fixed the **browse-call budget** at six scheduled URLs per run, but it did **not** equalize total tokens, model calls, latency, or dollar cost across variants. Accordingly, pilot v1 is an instrumentation/reliability study and must not be described as an equal-total-compute result. The main study must either impose an explicit total budget cap or report quality-cost Pareto frontiers.

## Motivation

Deep-research systems are increasingly evaluated end-to-end, but practitioners still face a concrete systems question: given a limited latency/token/tool/cost budget, which stage deserves additional computation? More searching can increase evidence coverage but also introduce irrelevant context; more planning can improve query diversity but add inference overhead; verification can improve support but consumes additional model calls.

The experiment therefore treats agent quality as a constrained resource-allocation problem rather than only a maximum-accuracy problem.

## Primary research question

Under a constrained research budget, how should computation be distributed among planning, retrieval, and verification to maximize evidence-supported report quality?

## Secondary research questions

**RQ1 — Planning:** At equal retrieval budget and with total cost reported, does explicit query decomposition improve report quality relative to directly retrieving from the original question?

**RQ2 — Retrieval depth:** How does increasing the scheduled browse-call budget affect completeness, evidence quality, latency, and unsupported-claim rate?

**RQ3 — Verification:** Does claim-level evidence verification improve support enough to justify its token, latency, and dollar overhead?

**RQ4 — Interaction:** Are planning and verification complementary, redundant, or competitive for the same limited budget?

**RQ5 — Failure movement:** When one stage is strengthened, which failure modes disappear and which new bottlenecks become dominant?

## Hypotheses

- **H1:** Planning improves source diversity and completeness most strongly at low-to-medium retrieval budgets.
- **H2:** Retrieval depth has diminishing returns: additional scheduled sources eventually add cost faster than supported content.
- **H3:** Verification reduces unsupported claims but may reduce total coverage when an overall compute budget is enforced.
- **H4:** The best quality-cost trade-off will use moderate planning and retrieval plus selective verification rather than maximizing any one stage independently.

These are hypotheses only. They must be revised or rejected according to measured results.

## Experimental factors

### Factor A: planning

- `direct`: use the original research question as the retrieval query or minimal query set;
- `planner`: use LLM-based query decomposition.

### Factor B: retrieval budget

Use **scheduled unique browse calls**, not successful-source count, because a successful-source target would grant extra tool calls to runs experiencing failures.

Planned main-study levels:

- `small`: 3 scheduled unique URLs maximum;
- `medium`: 6 scheduled unique URLs maximum;
- `large`: 12 scheduled unique URLs maximum.

For each run, record scheduled URLs, successful URLs, failed URLs, unique domains, and browse success rate separately. The exact levels must be frozen before the main run.

### Factor C: verification

- `none`: synthesize report directly from gathered evidence;
- `verify`: decompose the generated report into atomic factual claims, check each sampled/eligible claim against retrieved evidence, and record support labels;
- `verify_repair`: verify and perform one bounded repair pass for unsupported claims.

Pilot v1 implements `verify` without repair. Any repair condition added later must be treated as a separate experimental treatment.

## Budget principle

A central requirement of the final paper is that comparisons must not quietly give one variant more computation and then describe the result as equal-budget.

For every run record:

- prompt tokens;
- completion tokens;
- number of model calls;
- number of search calls;
- number of scheduled browse calls;
- successful/failed browse counts;
- wall-clock latency;
- estimated USD cost.

Primary analysis must use one of two defensible designs:

1. **explicit total-budget design:** enforce a predeclared total token/cost/latency budget across compared treatments, with treatment-specific allocation inside that cap; or
2. **Pareto design:** allow treatments to consume different resources, but compare report quality/evidence support against cost, tokens, and latency rather than calling the comparison equal-budget.

Pilot v1 follows the second design only for operational diagnostics; it does not yet have a common report-quality evaluator across variants.

## Variants

Minimum viable main-study matrix:

| ID | Planning | Browse-call budget | Verification |
|---|---|---:|---|
| D3 | direct | 3 | none |
| D6 | direct | 6 | none |
| D12 | direct | 12 | none |
| P3 | planner | 3 | none |
| P6 | planner | 6 | none |
| P12 | planner | 12 | none |
| D6V | direct | 6 | verify |
| P6V | planner | 6 | verify |

If time and budget allow, extend verification to browse-call budgets 3 and 12.

## Task set

Do not invent benchmark scores or alter tasks after seeing main-study results.

Use a versioned task manifest containing a mixture of:

- multi-source factual synthesis;
- comparative research;
- questions requiring primary-source preference;
- conflicting-source questions;
- time-sensitive questions;
- long-form research/report prompts.

Preferred evaluation strategy:

1. use an established public deep-research benchmark where licensing permits;
2. supplement it with a separately labeled original live-web task set;
3. never merge test tasks into training/prompt-tuning material.

Before running the main study, save the exact task IDs, benchmark version, prompt/evaluator versions, and frozen experimental configuration in `experiments/manifests/`.

## Primary metrics

### Evidence support

Atomic factual claims should be labeled as:

- supported;
- partially supported;
- unsupported;
- contradicted.

Primary claim-support metric:

`fully_supported_claims / all_annotated_factual_claims`

Do not call this factual accuracy unless the annotation protocol verifies truth beyond citation support.

A crucial main-study requirement is that **all compared reports receive a common support evaluation**. Treatment verification cannot be the only source of claim-support labels, otherwise P6V cannot be fairly compared with D6/P6. Use either:

- blinded human claim annotation for every sampled report; or
- a fixed evaluation-only verifier applied post hoc to all variants and kept separate from the treatment pipeline, with human validation on a subset.

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
- scheduled and successfully browsed sources;
- estimated cost.

### Retrieval/source metrics

- unique scheduled source count;
- successful source count;
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
3. inspect the source evidence available to the agent;
4. assign the four-level support label;
5. resolve disagreements after recording the initial independent labels.

Report inter-rater agreement on the independently annotated subset.

Automated LLM judging can be used as a secondary or scaling metric, but human evaluation should remain the reference for the main claim-support analysis unless a validated benchmark evaluator is used.

## Statistical analysis

Because the same tasks are evaluated under multiple variants, prefer paired analyses.

Minimum reporting:

- mean;
- median where distributions are skewed;
- standard deviation or bootstrap confidence intervals;
- per-task paired differences between key variants.

Do not report p-values unless the selected test and its assumptions are documented in the analysis script. With small pilot samples, emphasize effect sizes and uncertainty rather than significance testing.

Important comparisons:

- `P6 - D6`: value/overhead of planning at equal browse-call budget;
- `D12 - D6`: marginal value of additional retrieval;
- `P6V - P6`: value/cost of treatment verification;
- Pareto comparison of all variants on common report-quality/support metrics vs. cost/latency.

## Reproducibility requirements

Every main-study run must record:

- task ID;
- variant ID;
- timestamp;
- git commit SHA;
- prompt version;
- model/provider exact identifier;
- temperature and other decoding parameters;
- search provider/backend state where available;
- browse-call budget;
- raw candidate/scheduled/successful/failed URLs;
- raw model output;
- token usage;
- latency;
- estimated cost;
- evaluator version;
- timeout configuration.

Raw traces should be retained even when a run fails. Infrastructure failures must remain distinguishable from low-quality but completed experimental outputs.

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
2. a resource-aware analysis of quality, evidence support, latency, tokens, and cost;
3. empirical evidence about interactions and diminishing returns across research-agent stages;
4. an open reproducibility package containing configurations, traces, evaluation scripts, and analysis.

Do not claim state-of-the-art performance unless directly and fairly demonstrated. Do not call a comparison equal-budget unless the total budget is genuinely equalized.

## Immediate implementation order after pilot v1

1. freeze a larger main-study task manifest before observing main-study outcomes;
2. implement retrieval levels D3/D12/P3/P12 around the already validated D6/P6 paths;
3. define the total-budget/Pareto analysis policy before running the matrix;
4. implement a common post-hoc support evaluator for every variant, kept separate from the treatment verifier;
5. freeze human-annotation instructions and blinded report IDs;
6. run a small predeclared smoke test only for infrastructure, not treatment tuning;
7. execute the frozen main matrix and preserve all traces, including failures;
8. perform human annotation on the predeclared subset;
9. generate tables/plots from saved traces with scripted analysis;
10. write the manuscript from measured results only.

## Stop/go gate for ICLR 2027

Do not submit merely to meet the deadline. A genuine submission should exist by the decision gate with:

- implemented core variants;
- frozen main task set;
- completed main experimental runs;
- reproducible saved traces;
- at least preliminary human evaluation;
- at least one non-trivial empirical finding under a defensible budget analysis;
- complete paper draft with limitations and AI-use disclosure.

If these conditions are not met, release a high-quality preprint after the experiments are complete and target a later suitable venue.
