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

- [ ] **Step 1: Write failing tests**

Test deterministic ordering, variant-label blinding, one-to-one blind IDs, rejection of duplicate variant/task cells, rejection of missing reports, and ratings-template bounds/schema.

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest -q tests/test_human_eval.py`
Expected: FAIL because `scripts.build_human_eval_packet` does not yet exist.

- [ ] **Step 3: Implement minimal offline builder**

Implement `build_packet(trace_root: Path, output_root: Path, seed: int = 20260915) -> dict` plus a CLI. Read trace JSON, resolve `report_path` to the corresponding `.md`, create deterministic randomized rows, write annotator packet without variant labels, write coordinator blinding key separately, and write a 1–5 rubric ratings template.

- [ ] **Step 4: Run targeted and full tests**

Run: `python -m pytest -q tests/test_human_eval.py` then `python -m pytest -q`.
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `research: add blinded human evaluation packet builder`.

### Task 2: Freeze the human-evaluation protocol

**Files:**
- Create: `paper/HUMAN_EVAL_PROTOCOL.md`
- Modify: `docs/EVALUATION.md`

**Interfaces:**
- Consumes: packet/key/template generated in Task 1.
- Produces: reviewer-facing instructions that keep annotators blind to variant identity and define the rubric before scoring.

- [ ] **Step 1: Document rubric and blinding rules**

Define five 1–5 dimensions: correctness, completeness, source quality, synthesis/reasoning, and clarity. Require evidence-based notes for scores 1 or 5, no access to blinding key during annotation, and at least two annotators on a reliability subset.

- [ ] **Step 2: Document adjudication and agreement**

Specify double-scored subset selection, agreement reporting, disagreement handling, missing-score policy, and that human results remain pending until real annotations exist.

- [ ] **Step 3: Update evaluation status**

Replace stale “planned study” language with the implemented D3/D6/P6/P6V main-study design and distinguish automated support evaluation from pending blinded human quality evaluation.

- [ ] **Step 4: Commit**

Commit message: `docs: freeze blinded human evaluation protocol`.

### Task 3: Make the repository landing page match the actual research state

**Files:**
- Modify: `README.md`
- Modify: pull request #1 description

**Interfaces:**
- Consumes: current branch capabilities and frozen research protocol.
- Produces: an admissions/reviewer-friendly project overview with accurate implemented/planned status.

- [ ] **Step 1: Update README research question and status**

Lead with: “Where should an autonomous research agent spend its inference and retrieval budget?” Describe the implemented D3/D6/P6/P6V matrix, frozen 10-task set, common post-hoc support evaluator, preregistered paired inference, cost accounting, and pending blinded human evaluation.

- [ ] **Step 2: Add reproducibility map**

Link the pilot results, research protocol, analysis plan, human-evaluation protocol, experiment task manifests, analysis script, and manual-only workflows. Remove stale claims that verification/systematic study are merely planned.

- [ ] **Step 3: Refresh PR description**

Summarize the pilot-to-main-study progression and make the remaining gate human annotation + final research write-up, without claiming unmeasured human-quality gains.

- [ ] **Step 4: Verify CI**

Confirm the pull-request test workflow passes at the final head SHA.

- [ ] **Step 5: Commit**

Commit message: `docs: align research overview with main-study pipeline`.
