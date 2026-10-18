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

New post-hoc evaluator caches use schema version 2. Each cache binds the exact
UTF-8 question, report, retrieved-evidence context, and final evaluator prompt
with SHA-256 and byte-size fingerprints. Evaluator-only resume recomputes these
fingerprints before any model call and rejects a stale schema-v2 cache if any
prompt input changed. The already-frozen canonical recovery caches predate this
field and remain readable as schema version 1 for historical reproducibility;
their cell identity and accounting are validated, but they must not be described
as carrying the newer byte-level evaluator-input binding.

Evaluator resume and offline summary generation also load the frozen task file
and require every treatment trace to carry its exact task-set ID and question
text. A trace whose task ID is absent from the frozen task set, whose task-set
metadata drifts, or whose recorded question differs from the frozen definition
is rejected before any evaluator model import/call and before summary outputs
are published. This prevents a correctly shaped treatment/evaluator cell from
being silently attributed to a changed research question.

The common evaluator configuration is also an explicit frozen contract:
`gpt-5.6-terra` at temperature `1.0`. Evaluator recovery rejects different
runtime settings before importing or calling the model client, and offline
summary generation validates every cache against those fixed values rather
than inferring the expected configuration from the first cache. This prevents
a coherently replaced cache set from silently redefining the measurement
instrument.

The evaluator renders both canonical aggregate artifacts completely before it
publishes either one. Each staged file is flushed and synchronized, then moved
over its destination with an atomic replacement; the output directory is
synchronized after both replacements. A failure while rendering or staging
therefore leaves the previous JSON summary and run-level CSV untouched and
removes temporary files. The two final path replacements cannot form one
filesystem transaction, so an interruption between them may leave generations
temporarily mismatched. To make that state detectable, the JSON summary binds
the exact run-level CSV bytes with SHA-256; the evaluator verifies that binding
after publication, and the downstream offline summarizer rejects a missing or
mismatched binding before it writes study-summary outputs.

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

The manuscript-facing entry point, `scripts/run_verified_main_study_analysis.py`,
does not analyze live CSV paths after merely checking them. It captures both
canonical CSV inputs, re-checks the captured byte counts and SHA-256 digests
against the recorded manifest, validates that snapshot, and points the frozen
analyzer at the same snapshot. A concurrent edit therefore cannot make a
successful provenance receipt describe different bytes from those analyzed.
Before numeric or inferential validation, the shared study-input reader also
requires an unambiguous CSV table: headers must exist, be nonblank, and be
unique; every row must have exactly the declared number of fields; and malformed
CSV quoting is rejected. Canonical inputs are restricted to one CSV record per
physical line, and blank physical records are errors rather than silently
ignored data. The standalone preflight and verified snapshot gate use this same
reader, so a byte-fingerprinted but ambiguously parsed artifact cannot proceed
through the manuscript-facing analysis entry point.
New execution receipts bind the exact shared input-validator source alongside
the verified runner and independent execution verifier. The runner fingerprints
the validator source before validation, executes that exact captured byte stream
rather than a previously cached import, rechecks the canonical source after
analysis, and records the captured digest. This makes validator drift during or
after a run detectable without altering the frozen analyzer used by the
preserved legacy receipt.
The final success receipt is serialized completely into a same-directory
staging file, flushed, and synchronized before an atomic no-replace link makes
it visible. The receipt parent is opened without following a leaf symlink and
its inode is rechecked during invalidation and publication. A concurrent
publisher is therefore preserved and reported rather than overwritten, while
an interruption before the publication boundary cannot expose truncated JSON
at the canonical receipt path.
The analyzer runs in an isolated subprocess so concurrent in-process callers
cannot redirect one another through module-global paths. Future receipts emitted
by this updated entry point also bind the exact runner and independent
`scripts/verify_main_study_execution.py` source bytes. The preserved canonical
receipt predates that added execution-layer field and remains governed by
`scripts/verify_analysis_provenance.py`; it is not retroactively relabeled.
Downstream reconciliation permits that compatibility path only for the exact
pinned SHA-256 of the preserved receipt, so stripping `verified_execution` from
a future receipt cannot downgrade it to legacy verification.

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

The packet is deterministic under a fixed seed and fails closed on duplicate treatment/task cells, incomplete runs, missing Markdown reports, unexpected variants, or incomplete task matrices. The annotator-facing leakage audit covers rendered text and recursively percent-decoded Markdown URL metadata so encoded treatment labels cannot be hidden in link or image destinations; metadata exceeding the bounded decoding depth is rejected instead of bypassing or exhausting the audit. Only canonical schema-version-2 treatment traces with object-valued experiment and trace sections can enter or later verify against the packet. When a persisted trace carries task-set identity in both its experiment configuration and run-trace payload, those copies must agree and match the frozen task manifest; neither packet generation nor later packet verification silently prefers one conflicting identity.

Annotators must not receive `blinding_key.csv` until ratings are frozen. At least a predeclared subset should be independently double-scored and inter-annotator agreement should be reported before adjudication.

After real ratings are frozen, the complementary human-analysis command writes
a create-only result bundle whose manifest binds the exact analysis and verifier
sources, `requirements.txt`, `.python-version`, and the Python implementation,
version, and standard-library PRNG state contract that produced the numeric
outputs. Independent verification rejects source, pinned-environment, or runtime
drift before recomputing the analysis. Before either blinded verification or
unblinding, every analysis input is copied from an open regular-file descriptor
under a non-symlink parent and checked for stable path, inode, metadata, and byte
identity. Redirected parents and same-byte path replacement therefore fail
closed instead of being laundered into the retained analysis snapshot. This
records reproducibility metadata; it does not create ratings or convert pending
human validation into a result.

The downstream descriptive reconciliation bundle applies the same fail-closed
environment binding and additionally proves that both pinned files are the exact
bytes recorded in its producing Git commit. This remains a provenance check, not
an inferential extension or a substitute for real blinded ratings. Its manifest
is a closed schema: undeclared fields, an altered integrity statement, extra
fingerprint members, and non-integer byte counts are rejected rather than being
accepted through permissive JSON or numeric equality. The bundle directory is
also closed to exactly the canonical JSON, deterministic Markdown, and manifest;
undeclared files or directories are rejected, including entries added while the
verifier captures the declared artifacts.

The reconciliation readiness gate holds every contract, automated-analysis,
provenance, human-analysis, and human-manifest input open by descriptor for the
full verification phase. It rejects symlinked input parents and detects entry,
inode, metadata, or byte changes before emitting a readiness receipt. The
reconciler repeats that descriptor-bound capture while consuming the verified
analysis inputs, closing the gap between readiness and result computation.
Before reconciliation, it also validates the mathematical support of the
pre-frozen measures: strict-support-rate task contrasts must be in `[-1, 1]`,
1–5 rubric task contrasts must be in `[-4, 4]`, and all declared task/pair/sign
counts must be non-negative integers. Impossible values and JSON booleans that
would otherwise compare equal to `0` or `1` fail closed.

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
