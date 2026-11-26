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

### 2026-11-26 — Retrospective disclosure of recent AI-assisted research work

This dated entry records ten recent AI-assisted contributions for which the assistance conversation and the corresponding Git commits are available. The commit paths were checked at the immutable revisions below. It is a **partial retrospective disclosure**, not a complete reconstruction of all assistance since the 9 September entry. Git attribution alone does not establish whether a change was AI-assisted or independently reviewed by a human.

| Contribution | Commit evidence | Scope of assistance |
| --- | --- | --- |
| ZIP member flag validation | [a7f8d320](https://github.com/anupamking01/Ai-Researcher-Agent/commit/a7f8d320a89aec202908938937cf1ebf67a1d861) | Recovery-tool code, synthetic regressions, documentation |
| Historical semantic archive-read integrity | [abca99aa](https://github.com/anupamking01/Ai-Researcher-Agent/commit/abca99aa5c9431d65f37083fdacc20a0e30643d8) | Source-custody code, regressions, documentation |
| Preliminary archive fingerprint custody | [9ca9f9a0](https://github.com/anupamking01/Ai-Researcher-Agent/commit/9ca9f9a0fd5010174827207277624a7a635f0dcf) | Source-custody code, regressions, documentation |
| Portable evidence namespace inventory | [aed3ee45](https://github.com/anupamking01/Ai-Researcher-Agent/commit/aed3ee45301c0b638e97b5365750399610040fc8) | Inventory code, regressions, documentation |
| Historical evaluator newline-policy qualification | [0735454d](https://github.com/anupamking01/Ai-Researcher-Agent/commit/0735454d7d7d02cfba3c5646475671d194b1c995) | Historical source comparison, audit code, tests, methods qualification |
| Cell-level candidate newline-input diagnostic | [cda9c6b8](https://github.com/anupamking01/Ai-Researcher-Agent/commit/cda9c6b8d21a371adf2fcc27cdb6ed4ac5f1a891) | Diagnostic code, tests, qualification of candidate evidence |
| Saved-query evidence inventory | [112fea9b](https://github.com/anupamking01/Ai-Researcher-Agent/commit/112fea9bcd351a59a5f2806d309512229b06a25b) | Inventory code, regressions, documentation |
| Historical dependency-resolution comparison | [2aa1f7b8](https://github.com/anupamking01/Ai-Researcher-Agent/commit/2aa1f7b864865652ba25c8021b7d8be1b70314bc) | Historical log comparison and reproducibility limitations |
| Scientific reporting and analysis-freeze qualification | [3a18e6a1](https://github.com/anupamking01/Ai-Researcher-Agent/commit/3a18e6a13e97138037d5d9fcab36581acf59d6ab) | Methods interpretation and research-document editing |
| Literature positioning | [1d9c4a11](https://github.com/anupamking01/Ai-Researcher-Agent/commit/1d9c4a11743e74ad18a85abe0ff52749fa6ed205) | Literature comparison and novelty/claim-boundary editing |

Generative AI assistance also identified the disclosure gap, inspected the current branch and CI, and drafted this log update. At the inspected tip `1d9c4a11743e74ad18a85abe0ff52749fa6ed205`, all 18 listed pull-request workflow runs had completed successfully. This records automated validation at that revision, not a claim that every earlier test was executed independently or that the human author has reviewed every change.

**Outstanding disclosure and review:** The interval after the 9 September entry and before these recorded contributions has not been exhaustively reconciled against available assistance records. Before submission, the human author should reconcile that interval, verify citations and scientific interpretations, review the AI-assisted implementation and its actual validation receipts, and record material corrections or unresolved gaps. Do not infer a completed human review from a Git author field, a successful CI run, or the absence of review comments.

These contributions do not establish recovery or authentication of original treatment reports, prospective automated-analysis preregistration, a causal effect of any treatment, or completed human evaluation. The [required reporting cover](MAIN_STUDY_REPORTING_COVER.md) governs the frozen automated results; the pilot remains diagnostic, retrospective sensitivity analyses remain exploratory, and genuine human ratings and agreement remain pending.

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

> Generative AI tools were used to assist with literature discovery, research-question refinement, experimental-method feedback, software development, workflow debugging/orchestration, trace-based data analysis, research interpretation, and manuscript editing. The intended evidence policy is to report experimental values only from retained evidence, not invented or interpolated by the assistant. The retained automated evidence and its unresolved original-report custody limitations must be described separately from pending human validation.

This is a provisional disclosure, not a signed human-author attestation. Add a statement of completed human review and responsibility only after the author actually performs and confirms that review; reconcile outstanding assistance records and check the target venue's policy before submission.
