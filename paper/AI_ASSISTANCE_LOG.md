# AI Assistance Log

This file records generative-AI assistance used during the research project so that venue-specific disclosure requirements can be satisfied accurately.

The human author remains responsible for all experiments, claims, citations, code correctness, analysis, and final manuscript content.

## Log

### 2026-09-08 — Research framing and methodology design

Generative AI assistance was used to:

- inspect the existing repository structure and research roadmap;
- review recent public literature on deep-research-agent evaluation, failure analysis, verification, and budget-aware tool use;
- refine the research question from a broad agent-evaluation study to a resource-aware stage-wise ablation study;
- propose research questions and falsifiable hypotheses;
- design an initial experimental matrix comparing planning, retrieval depth, and verification;
- propose metrics, annotation procedures, reproducibility requirements, and a statistical-analysis plan;
- draft `paper/RESEARCH_PROTOCOL.md`.

The proposed methodology must be reviewed and modified by the human author before experiments are treated as final.

### 2026-09-08 — Pilot implementation and reproducibility hardening

Generative AI assistance was used to implement and review the pilot infrastructure, including:

- D6/P6/P6V experiment configuration and fixed browse-call allocation;
- direct/planner execution paths and bounded claim verification;
- run-level JSON tracing and task metadata;
- exact search-query and source-URL audit trails;
- correction of failed-scrape accounting so error strings are not counted as successful evidence;
- provider-reported prompt/completion token accounting with a thread-safe run ledger;
- non-streaming pilot report generation to expose provider usage metadata;
- separation of provider-independent usage accounting from the OpenAI adapter to preserve offline tests;
- explicit environment-variable precedence over local `.env` settings;
- current Selenium driver resolution rather than the repository's stale pinned ChromeDriver path;
- pilot manifest creation and an offline JSON/CSV summarizer;
- a GitHub Actions live-pilot workflow that uses a repository secret rather than committed credentials;
- offline unit tests for variant configuration, budget allocation, verifier normalization, trace persistence, and usage accounting;
- debugging CI dependency failures and refactoring the usage ledger so the offline test job remained provider-independent;
- updating pilot implementation documentation and PR status.

No experimental values were invented during this implementation phase. Live outcomes were to be accepted only from persisted API-backed traces.

### 2026-09-09 — Live-pilot infrastructure diagnosis and compatibility corrections

Generative AI assistance was used to inspect GitHub Actions logs/artifacts and diagnose several pre-result infrastructure failures. Changes made before a complete valid pilot existed included:

- adding API credit after provider `no credits remaining` failures;
- changing temperature from the predeclared `0` to provider-supported `1` after the model rejected temperature 0, before any successful evidence-backed pilot completed;
- making legacy `js/overlay.js` injection optional;
- isolating Chrome debugging ports and bounding concurrent browser extraction;
- adding Selenium, browse, run, and provider request timeouts;
- adding atomic progress checkpoints and stale-run cancellation;
- adding live search/browser preflight checks before experiment API spending;
- bounding source summarization to one fast-model call per successfully extracted source;
- expanding regression tests and adding strict artifact validation so incomplete experimental sets fail CI.

Invalid diagnostic runs with zero usable web evidence, browser failures, unsupported temperature, or provider-credit failures were not treated as research results. The infrastructure changes were responses to execution failures observed before a complete valid result set, not outcome-driven tuning of a successful experiment.

### 2026-09-09 — Canonical pilot completion and analysis

Generative AI assistance was used to:

- inspect workflow run `34377707838`, which produced 13 completed experimental traces before API credit exhaustion;
- identify that only `P6V/pilot-04` and `P6V/pilot-05` were missing because of the external billing failure;
- launch and inspect targeted workflow run `34388324051` after credit was restored, using the same model, temperature, browse budget, and timeout configuration;
- verify that the targeted run passed offline tests, live browser/search preflight, experiment execution, summary generation, strict artifact validation, and artifact upload;
- construct the canonical 15-run dataset by retaining the original 13 completed traces and replacing only the two billing-failure slots with their targeted successful reruns;
- verify unique `(variant, task)` coverage, completion, source-budget settings, provider usage accounting, cost accounting, model IDs, temperature, timeout configuration, and P6V verifier status;
- compute descriptive variant averages and paired operational deltas from the persisted CSV/traces;
- draft `paper/PILOT_RESULTS.md` and update the research protocol to distinguish a fixed browse-call budget from an equal-total-compute design.

The analysis explicitly preserves limitations: the pilot has only five tasks, lacks blinded human quality evaluation, and does not have common claim-support labels for D6/P6. Therefore no claim is made that P6V improves evidence support over P6 from this pilot alone. Reported numerical values come from persisted workflow artifacts; none were invented or interpolated.

After successful canonical completion, the temporary automatic push trigger for the live workflow was removed so future API spending requires explicit manual dispatch.

## Rules for future entries

Add a dated entry whenever generative AI materially assists with any of the following:

- hypothesis generation or refinement;
- research methodology or experimental design;
- implementation of experimental methods;
- experimental orchestration or debugging;
- data cleaning or transformation;
- statistical analysis or result interpretation;
- literature review or reference discovery;
- manuscript drafting or editing;
- figures or tables;
- rebuttal preparation.

For every AI-assisted contribution:

1. verify cited papers against the original source;
2. test AI-assisted code before relying on its outputs;
3. never fabricate or interpolate experimental results;
4. preserve raw experiment traces, including failed runs;
5. document significant human corrections to AI suggestions when they affect methodology or conclusions;
6. clearly distinguish infrastructure diagnostics, pilot findings, and main-study findings.

## Manuscript disclosure draft

Do not copy this blindly into a submission; adapt it to the target venue's current policy.

> Generative AI tools were used to assist with literature discovery, research-question refinement, experimental-method feedback, software development, workflow debugging/orchestration, trace-based data analysis, and manuscript editing. All reported experimental values were derived from persisted run artifacts rather than generated or inferred by the assistant. The human author reviewed the research design, experimental records, analysis, citations, limitations, and final claims and takes responsibility for the full content of the work.
