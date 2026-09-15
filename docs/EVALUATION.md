# Evaluation Methodology

This repository treats evaluation as part of the research system rather than as a post-hoc demo score. The current experimental program asks a focused systems question:

> **Where should a web-research agent spend limited retrieval and inference budget: deeper retrieval, explicit planning, or verification?**

The project has progressed beyond the original proposed-study document. Pilot infrastructure, D3/D6/P6/P6V treatments, persisted traces, a common post-hoc support evaluator, cost accounting, a frozen paired analysis plan, evaluator-only recovery, and deterministic blinded-human-evaluation packet generation are implemented on the research branch.

Human quality ratings are **not yet results**. They remain pending and must be collected under `paper/HUMAN_EVAL_PROTOCOL.md` before any human-quality claim is made.

## 1. Research questions

The main study is organized around three primary stage-wise questions plus a broader systems question:

- **Retrieval depth:** What changes when the direct-retrieval treatment receives six scheduled browse opportunities rather than three (`D6 - D3`)?
- **Planning:** At the same six-source browse budget, what is the marginal effect of explicit query decomposition (`P6 - D6`)?
- **Verification:** What is the marginal effect and cost of treatment-time verification (`P6V - P6`)?
- **Quality–cost trade-off:** Do improvements in evidence support justify additional model tokens, model calls, latency, and estimated dollar cost?

The broader research protocol and hypotheses are documented in `paper/RESEARCH_PROTOCOL.md`.

## 2. Study layers

The project deliberately separates four layers that should not be conflated.

### Layer A — Treatment execution

Each experimental variant generates a report under a defined planning/retrieval/verification configuration. The treatment itself records provenance, usage, costs, source outcomes, and final report artifacts.

### Layer B — Common automated measurement

A fixed post-hoc evaluator is applied to all treatment variants so that support labels are not available only for the verifier-enabled treatment. The evaluator is measurement-only and is kept separate from treatment generation.

### Layer C — Offline statistical analysis

Saved traces/evaluator records are summarized with a frozen paired analysis plan. Analysis operates on persisted artifacts; it does not rerun treatments merely because an observed result is inconvenient.

### Layer D — Blinded human validation

A deterministic offline packet builder hides variant identity and prepares the same reports for rubric-based human evaluation. Human annotations are a complementary measure of overall quality and usefulness, not a synthetic replacement for the automated support metric.

## 3. Frozen main-study treatment matrix

The current main-study analysis focuses on the following four conditions over the same frozen task set:

| Variant | Planning | Scheduled browse budget | Treatment verification | Main contrast role |
|---|---|---:|---|---|
| `D3` | Direct | 3 | No | Retrieval-depth baseline |
| `D6` | Direct | 6 | No | Retrieval-depth comparison / planning baseline |
| `P6` | Planner | 6 | No | Planning comparison / verification baseline |
| `P6V` | Planner | 6 | Yes | Verification comparison |

The full research protocol discusses additional possible retrieval levels, but those should not be silently mixed into the frozen confirmatory analysis unless a new study version explicitly declares them.

## 4. Task design

The study uses a versioned, frozen task set. The intended task mixture includes:

- multi-source factual synthesis;
- comparative research;
- questions where primary sources are preferable;
- conflicting-source questions;
- time-sensitive research;
- long-form synthesis prompts.

Tasks must not be edited after outcomes are observed and still be described as the same study version. New or corrected task sets require a new manifest/version and should be analyzed separately.

## 5. Primary automated outcome

The main automated outcome is **strict evidence support rate** from the common post-hoc evaluator:

`supported claims / claims checked`

The evaluator samples/checks a bounded number of factual claims and classifies support using evidence retrieved by the corresponding treatment. The analysis plan distinguishes strict support from broader support and explicitly avoids calling citation support equivalent to universal factual accuracy.

The automated evaluator should not be described as an unbiased human judge. It is a reproducible measurement instrument with its own model and prompt limitations.

## 6. Secondary outcomes

Secondary measurements include:

- broad support rate: `(supported + partially_supported) / claims_checked`;
- unsupported-or-contradicted rate;
- successful retrieved sources;
- scheduled/attempted source counts where available;
- prompt, completion, and total model tokens;
- model-call count;
- treatment latency;
- treatment-model estimated USD cost;
- report word count;
- completion/failure status;
- failure/provenance diagnostics.

Evaluator usage and evaluator cost are research-measurement overhead. They must not be mixed into the treatment/deployment cost comparison.

## 7. Budget accounting

A central integrity rule is that additional planning or verification computation cannot be described as “free.” Every relevant treatment run should retain enough metadata to reconstruct resource use, including:

- model/provider identifier;
- prompt/completion token usage;
- number of model calls;
- retrieval/search/browse activity;
- latency;
- configured browse budget;
- estimated cost under a frozen pricing snapshot.

When total compute differs across variants, the project uses a **quality–cost/Pareto interpretation** rather than falsely describing the variants as equal-total-budget systems.

## 8. Failure handling and provenance

A failed source fetch is not equivalent to a missing experiment. Likewise, zero successful evidence can be a valid treatment outcome rather than a reason to discard the run.

Important rules:

- zero retrieved evidence remains an observable outcome;
- treatment failures/timeouts are preserved rather than silently rerun until success;
- duplicate treatment executions are not substituted because their outcomes look better;
- if treatment execution is complete but measurement is interrupted, evaluator-only recovery may fill missing evaluator records without replacing the original treatment output;
- saved evidence and trace provenance must agree before an evaluation cell is considered valid;
- exclusions require an explicit pre-existing validity rule and must be reported.

Representative operational failure categories include:

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

## 9. Frozen paired statistical analysis

The confirmatory automated analysis is specified in `paper/ANALYSIS_PLAN.md` and was frozen before inspecting main-study outcome summaries.

Primary paired contrasts are:

1. `D6 - D3` — retrieval depth;
2. `P6 - D6` — planning;
3. `P6V - P6` — verification.

For the primary strict-support outcome, the analysis reports:

- paired mean difference;
- paired median difference;
- deterministic paired bootstrap 95% percentile confidence interval for the mean difference;
- exact two-sided sign-flip/randomization p-value when all paired cells are present;
- paired standardized mean difference (`d_z`) when defined;
- counts of positive, negative, and tied task-level effects.

The three confirmatory p-values are adjusted together with the Holm step-down procedure. Because the frozen task set is small, effect size, uncertainty, and task-level consistency should be emphasized over binary significance language.

Additional metrics and contrasts are exploratory unless separately preregistered.

## 10. Pilot vs. main study

The repository keeps pilot evidence distinct from the main study.

### Pilot

`paper/PILOT_RESULTS.md` documents the completed diagnostic pilot. It was used to validate instrumentation and expose reliability/accounting issues. It should not be promoted into a universal benchmark claim.

### Main-study infrastructure

The research branch implements:

- D3/D6/P6/P6V treatments;
- versioned run metadata and trace persistence;
- treatment usage/cost accounting;
- common post-hoc support evaluation;
- workflow validation and evaluator-only recovery;
- offline summary generation;
- a frozen paired inference script/analysis plan;
- deterministic human-evaluation packet generation.

A workflow or recovery run failing operationally must not be rewritten in documentation as a successful end-to-end execution. Final numerical claims should cite the exact canonical artifact set and execution provenance used for analysis.

## 11. Blinded human evaluation

Human evaluation is designed to answer questions the support evaluator does not fully capture.

The frozen rubric scores five dimensions from 1–5:

- correctness;
- completeness;
- source quality;
- synthesis/reasoning;
- clarity.

Build a packet from completed experiment traces with:

```bash
python scripts/build_human_eval_packet.py
```

The script creates:

- `outputs/human_eval/packet.jsonl` — blinded reports and research questions;
- `outputs/human_eval/ratings_template.csv` — blinded rating sheet;
- `outputs/human_eval/blinding_key.csv` — coordinator-only treatment mapping;
- `outputs/human_eval/manifest.json` — packet metadata.

The packet is deterministic under a fixed seed and fails closed on duplicate treatment/task cells, incomplete runs, missing Markdown reports, unexpected variants, or incomplete task matrices.

Annotators must not receive `blinding_key.csv` until ratings are frozen. At least a predeclared subset should be independently double-scored and inter-annotator agreement should be reported before adjudication.

Full instructions are in `paper/HUMAN_EVAL_PROTOCOL.md`.

## 12. Reproducibility map

Key research artifacts:

| Artifact | Purpose |
|---|---|
| `paper/RESEARCH_PROTOCOL.md` | Research question, hypotheses, experimental principles |
| `paper/PILOT_RESULTS.md` | Canonical pilot evidence and caveats |
| `paper/ANALYSIS_PLAN.md` | Frozen main-study confirmatory analysis |
| `paper/HUMAN_EVAL_PROTOCOL.md` | Blinded human-quality scoring protocol |
| `logic/experiment.py` | Experimental configuration/provenance structures |
| `scripts/run_budget_main_study.py` | Main-study treatment/evaluation orchestration |
| `scripts/summarize_budget_main_study.py` | Offline aggregation/validation |
| `scripts/analyze_main_study.py` | Paired preregistered inference |
| `scripts/build_human_eval_packet.py` | Deterministic blinded human-evaluation packet |
| `tests/` | Offline invariants and regression tests |
| `.github/workflows/` | CI and manual research workflows |

## 13. Offline verification

Install test dependencies and run:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The ordinary unit-test suite is designed to run without making live LLM or web calls.

The human-evaluation packet builder is also offline; it consumes only persisted traces and Markdown reports.

## 14. Reporting rules

Research-facing documentation should follow these rules:

- do not convert `TBD`, pending annotations, or incomplete workflow artifacts into numerical claims;
- do not call support scoring “factual accuracy” unless truth is independently verified;
- do not call variants equal-budget when total compute differs;
- separate treatment cost from evaluator overhead;
- tie every reported number to a study/task version, commit/workflow provenance, model configuration, and analysis script;
- report failed runs and protocol deviations;
- distinguish pilot, confirmatory main-study, exploratory, and human-validation findings;
- avoid state-of-the-art or universal-superiority claims without a fair external benchmark.

## 15. Current status

The repository now has a reproducible evaluation architecture and a frozen human-evaluation protocol. The remaining research step is not to invent another metric: it is to collect real blinded annotations, validate the canonical main-study artifact set, run the predeclared analysis against that set, and write conclusions that stay within the measured evidence.
