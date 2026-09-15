# Human Evaluation & Reproducibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic blinded human-evaluation packet workflow and update the research-facing documentation so the completed automated main-study pipeline can be supplemented by reproducible human scoring.

**Architecture:** Keep treatment generation frozen. Read existing experiment traces and Markdown reports only after the study has completed, derive stable blinded IDs from a fixed seed, emit separate annotator-facing and coordinator-only artifacts, and validate the process entirely offline. Documentation must clearly separate pilot evidence, automated main-study evaluation, and pending human evaluation.

**Tech Stack:** Python 3.11 standard library, pytest, Markdown, GitHub Actions.

**Spec:** `paper/ANALYSIS_PLAN.md`, `paper/RESEARCH_PROTOCOL.md`, `docs/EVALUATION.md`

## Global Constraints

- Do not change D3/D6/P6/P6V treatment behavior.
- Do not make network or model calls in the human-evaluation builder.
- Never expose `variant_id` in annotator-facing packet or ratings template.
- Use a fixed seed for deterministic packet ordering.
- Fail closed on missing/duplicate/incomplete reports.
- Do not invent human ratings or convert pending human evaluation into a result claim.

---

### Task 1: Blinded packet builder

**Files:**
- Create: `tests/test_human_eval.py`
- Create: `scripts/build_human_eval_packet.py`

**Interfaces:**
- Consumes: `outputs/experiment_traces/<variant>/*.json` and each trace's sibling Markdown report.
- Produces: `outputs/human_eval/packet.jsonl`, `outputs/human_eval/blinding_key.csv`, `outputs/human_eval/ratings_template.csv`, `outputs/human_eval/manifest.json`.

- [x] **Step 1: Write failing tests**

Test deterministic ordering, variant-label blinding, one-to-one blind IDs, rejection of duplicate variant/task cells, rejection of missing reports, and ratings-template bounds/schema.

- [x] **Step 2: Run tests to verify RED**

GitHub Actions run `35004042197` failed after the contract test was added and before the implementation existed, establishing the RED phase.

- [x] **Step 3: Implement minimal offline builder**

Implemented `build_packet(trace_root: Path, output_root: Path, seed: int = 20260915) -> dict` plus CLI. The builder reads persisted trace JSON and sibling Markdown reports, deterministically randomizes the packet, keeps treatment labels out of annotator artifacts, writes the coordinator key separately, and creates a five-dimension ratings template.

- [x] **Step 4: Run targeted/full CI verification**

GitHub Actions run `35004173840` completed successfully after the implementation was added.

- [x] **Step 5: Commit implementation**

Implementation and tests are committed on `research-paper-eval-2027`.

### Task 2: Freeze the human-evaluation protocol

**Files:**
- Create: `paper/HUMAN_EVAL_PROTOCOL.md`
- Modify: `docs/EVALUATION.md`

**Interfaces:**
- Consumes: packet/key/template generated in Task 1.
- Produces: reviewer-facing instructions that keep annotators blind to variant identity and define the rubric before scoring.

- [x] **Step 1: Document rubric and blinding rules**

Five 1–5 dimensions are frozen: correctness, completeness, source quality, synthesis/reasoning, and clarity. The protocol requires notes for extreme scores, keeps the key hidden during annotation, and requires independent double-scoring on at least a predeclared subset.

- [x] **Step 2: Document adjudication and agreement**

The protocol specifies independent ratings, agreement measurement before adjudication, preservation of raw scores, blinded disagreement handling, missing-score policy, and a freeze-before-unblinding rule.

- [x] **Step 3: Update evaluation status**

`docs/EVALUATION.md` now reflects the implemented D3/D6/P6/P6V study layers, common post-hoc evaluator, frozen paired analysis, and pending blinded human-quality validation.

- [x] **Step 4: Commit documentation**

Protocol and methodology updates are committed on the research branch.

### Task 3: Make the repository landing page match the actual research state

**Files:**
- Modify: `README.md`
- Modify: pull request #1 description

**Interfaces:**
- Consumes: current branch capabilities and frozen research protocol.
- Produces: an admissions/reviewer-friendly project overview with accurate implemented/planned status.

- [x] **Step 1: Update README research question and status**

The README now leads with the budget-allocation research question and distinguishes implemented treatments/evaluation infrastructure from pending human validation and final paper-level claims.

- [x] **Step 2: Add reproducibility map**

The README links the pilot results, research protocol, analysis plan, human-evaluation protocol, evaluation methodology, orchestration/analysis scripts, tests, and workflows. Stale claims that the systematic study and verification layer are merely future plans were removed.

- [x] **Step 3: Refresh PR description**

PR #1 now documents the pilot-to-main-study progression, the preserved 40-treatment artifact, successful evaluator-only recovery, blinded human-evaluation tooling, research-integrity safeguards, and remaining research gates.

- [x] **Step 4: Verify CI**

GitHub Actions tests run `35004552088` passed on the updated code/docs head before this plan-status bookkeeping commit.

- [x] **Step 5: Record implementation status**

This file records completion of the scoped implementation while leaving actual human annotation and final scientific interpretation as future research work.
