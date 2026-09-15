# Blinded Human Evaluation Protocol

Status: **protocol frozen; human ratings not yet collected**.

Study: `budget-main-v1`

This protocol defines a blinded human evaluation layer for the D3, D6, P6, and P6V research-agent variants. It complements the common post-hoc support evaluator by measuring dimensions that automated claim-support scoring does not fully capture: overall correctness, completeness, source quality, synthesis/reasoning, and clarity.

No human-quality result should be reported until real annotations have been collected under this protocol. Missing ratings must never be imputed as positive evidence, and synthetic or model-generated ratings must not be presented as human judgments.

## 1. Evaluation unit

The evaluation unit is one final Markdown research report for one frozen task and one treatment variant.

Annotators see:

- a blinded report ID;
- the original research question;
- the generated report text.

Annotators do **not** see:

- the treatment/variant ID (`D3`, `D6`, `P6`, `P6V`);
- run IDs or filenames that reveal treatment identity;
- treatment-specific token, latency, source-budget, or cost information;
- the coordinator blinding key;
- aggregate scores from other annotators.

The purpose is to reduce expectation bias about which system should perform better.

## 2. Packet generation and blinding

Generate the evaluation packet only from completed experiment traces and their persisted Markdown reports:

```bash
python scripts/build_human_eval_packet.py
```

The builder is deterministic and offline. The default seed is `20260915`.

It writes four files under `outputs/human_eval/`:

- `packet.jsonl` — annotator-facing research questions and blinded reports;
- `ratings_template.csv` — annotator-facing scoring sheet;
- `blinding_key.csv` — coordinator-only mapping from blind IDs to treatment/run identities;
- `manifest.json` — packet metadata and blinding configuration.

### Blinding rule

Annotators receive only `packet.jsonl` and a copy of `ratings_template.csv`. `blinding_key.csv` remains inaccessible to annotators until all scores intended for the analysis are frozen.

The coordinator must not rename files, add treatment hints, or disclose expected hypotheses during annotation.

## 3. Rating rubric

Score each dimension from **1 to 5**. Evaluate the report as delivered; do not infer what the system may have intended to say.

### 3.1 Correctness

How accurate and internally defensible are the report's substantive claims?

- **1 — Poor:** major factual errors, contradictions, or misleading conclusions materially affect the answer.
- **3 — Adequate:** mostly correct, but contains noticeable uncertainty, minor errors, or claims that need stronger qualification.
- **5 — Excellent:** claims are consistently accurate, appropriately qualified, and free of material factual errors detectable from the report and cited/source context available to the evaluator.

### 3.2 Completeness

How well does the report cover the important parts of the research question?

- **1 — Poor:** misses central requirements or leaves major aspects unanswered.
- **3 — Adequate:** addresses the main question but omits some useful dimensions, caveats, or comparisons.
- **5 — Excellent:** covers the important dimensions comprehensively without obvious major omissions.

### 3.3 Source quality

How appropriate and trustworthy is the evidence base presented in the report?

- **1 — Poor:** relies mainly on weak, irrelevant, unverifiable, or clearly inappropriate sources.
- **3 — Adequate:** uses generally relevant sources but with mixed authority, recency, or directness.
- **5 — Excellent:** consistently prioritizes authoritative, relevant, sufficiently current, and preferably primary evidence where appropriate.

### 3.4 Synthesis / reasoning

How well does the report combine evidence into a coherent answer rather than merely listing retrieved facts?

- **1 — Poor:** fragmented, contradictory, or unsupported reasoning; little useful synthesis.
- **3 — Adequate:** reasonable organization and comparison, but important connections or trade-offs are underdeveloped.
- **5 — Excellent:** integrates evidence coherently, distinguishes competing considerations, and makes conclusions proportional to the evidence.

### 3.5 Clarity

How readable, well-structured, and precise is the report?

- **1 — Poor:** confusing, disorganized, repetitive, or difficult to interpret.
- **3 — Adequate:** understandable overall, with some verbosity, awkward structure, or imprecision.
- **5 — Excellent:** clear, concise relative to task complexity, logically structured, and easy to audit.

## 4. Annotation procedure

For every assigned report:

1. Read the research question before the report.
2. Read the entire report before entering final scores.
3. Score all five rubric dimensions independently.
4. Use integer scores only: `1`, `2`, `3`, `4`, or `5`.
5. Add a short note explaining any score of **1** or **5**. Notes for intermediate scores are encouraged when they identify a concrete strength, weakness, factual concern, or missing dimension.
6. Do not compare the current report with another report for the same task while scoring it. The unit is an independent absolute rubric judgment, not a forced-choice preference.
7. Do not search for treatment identity or inspect repository metadata that may reveal it.

If an annotator cannot fairly score a dimension because a report is malformed or unusable, the value should remain blank and the reason must be recorded in `notes`; do not substitute a neutral score automatically.

## 5. Assignment and reliability

At minimum, a predeclared subset must be scored independently by **two human annotators**. If practical, double-score the full packet because the study contains a small paired task set.

Before unblinding, report agreement separately for each rubric dimension. For two annotators, use a weighted agreement statistic appropriate for ordered 1–5 ratings (for example, quadratic-weighted Cohen's kappa) together with raw absolute agreement. If more than two annotators score the same items, use an appropriate ordinal/multi-rater reliability statistic and document it before analysis.

Agreement must be computed on the original independent ratings, before adjudication.

## 6. Disagreements and adjudication

Do not alter an annotator's original independent score after seeing treatment identity.

If adjudication is required:

1. preserve the original ratings;
2. identify disagreements using blinded IDs only;
3. allow annotators to discuss the rubric and report text while still blinded;
4. record any adjudicated value in a separate field/file rather than overwriting raw ratings;
5. freeze adjudicated ratings before opening the blinding key.

Rubric definitions must not be rewritten in response to which treatment appears to benefit.

## 7. Data freeze and unblinding

Before joining ratings with `blinding_key.csv`, the coordinator should create an immutable analysis snapshot containing:

- annotator IDs;
- blind IDs;
- all five rubric scores;
- notes;
- timestamp/version of the scoring file;
- protocol version/commit SHA.

Only after that freeze should treatment identities be merged for statistical analysis.

## 8. Human-evaluation analysis

The main automated study remains governed by `paper/ANALYSIS_PLAN.md`. Human-quality ratings are a complementary validation layer and should be reported separately unless a dedicated human-evaluation analysis plan is preregistered before unblinding.

Minimum reporting for each dimension:

- number of rated reports and missing ratings;
- per-variant mean and median;
- distribution of 1–5 scores;
- paired task-level differences for predeclared comparisons where the design supports them;
- inter-annotator agreement on the independently double-scored subset;
- adjudication rate, if adjudication is used.

For the existing treatment matrix, the natural paired comparisons are:

- `D6 - D3` — additional retrieval depth;
- `P6 - D6` — explicit planning at the same browse-call budget;
- `P6V - P6` — treatment verification overhead/value.

Because the task set is small, emphasize effect sizes, paired consistency, uncertainty, and raw distributions rather than binary significance claims.

## 9. Separation from automated support evaluation

The common post-hoc evaluator measures whether sampled factual claims are supported by evidence available to a treatment. It is intentionally not treated as a complete substitute for human report-quality judgment.

Human ratings add information about:

- whether the answer is useful and complete;
- whether source selection is appropriate;
- whether reasoning and synthesis are coherent;
- whether the report is readable and well calibrated.

If automated and human assessments disagree, report the disagreement rather than selectively replacing one with the other.

## 10. Integrity requirements

- Never fabricate or backfill human scores.
- Never unblind annotators before their ratings are frozen.
- Never drop a treatment/task cell because its human score is inconvenient.
- Never modify the rubric after inspecting treatment-level human results without clearly labeling the new analysis exploratory.
- Preserve raw ratings, the generated packet, the blinding key, and analysis scripts as reproducibility artifacts.
- Report deviations from this protocol explicitly.

## 11. Known limitations

Human rubric scoring is subjective and the study uses a small original task set. Blinding reduces treatment-expectation bias but does not eliminate evaluator subjectivity, task-domain expertise differences, or uncertainty about rapidly changing web facts. These limitations should be reported alongside any human-evaluation findings.
