# Blinded human-evaluation annotator guide

Status: **frozen before collecting human ratings**.

Study: `budget-main-v1`

This guide contains the complete treatment-blind instructions needed to score
the supplied research reports. Do not inspect the project repository or seek
information about how any report was produced. Score each report independently
from the research question, report text, and rubric below.

## Files and submission

The annotation bundle contains:

- `packet.jsonl`, with one blinded research question and report per line;
- `ratings_template.csv`, with one row per blinded report;
- this `annotator_instructions.md` guide.

Enter one stable `annotator_id` in every CSV row. Complete the assignment using
only your own judgment. Do not use an LLM, automated evaluator, or another
person to supply scores, and do not inspect another annotator's ratings. Submit
one completed CSV without adding, removing, renaming, or reordering columns.

## Procedure

For every assigned report:

1. Read the research question before the report.
2. Read the entire report before entering final scores.
3. Score all five dimensions independently with an integer from 1 to 5.
4. Add a short note explaining every score of 1 or 5.
5. Do not compare the report with another report for the same question while
   scoring it; apply the absolute rubric below.

If a dimension cannot be scored fairly because a report is malformed or
unusable, leave that score blank and record the reason in `notes`. Never insert
a neutral score merely to avoid a missing value. Notes for intermediate scores
are encouraged when they identify a concrete strength, weakness, factual
concern, or missing dimension.

## Correctness

How accurate and internally defensible are the report's substantive claims?

- **1 — Poor:** major factual errors, contradictions, or misleading conclusions
  materially affect the answer.
- **3 — Adequate:** mostly correct, but contains noticeable uncertainty, minor
  errors, or claims that need stronger qualification.
- **5 — Excellent:** claims are consistently accurate, appropriately qualified,
  and free of material factual errors detectable from the report and
  cited/source context available to the evaluator.

## Completeness

How well does the report cover the important parts of the research question?

- **1 — Poor:** misses central requirements or leaves major aspects unanswered.
- **3 — Adequate:** addresses the main question but omits some useful
  dimensions, caveats, or comparisons.
- **5 — Excellent:** covers the important dimensions comprehensively without
  obvious major omissions.

## Source quality

How appropriate and trustworthy is the evidence base presented in the report?

- **1 — Poor:** relies mainly on weak, irrelevant, unverifiable, or clearly
  inappropriate sources.
- **3 — Adequate:** uses generally relevant sources but with mixed authority,
  recency, or directness.
- **5 — Excellent:** consistently prioritizes authoritative, relevant,
  sufficiently current, and preferably primary evidence where appropriate.

## Synthesis / reasoning

How well does the report combine evidence into a coherent answer rather than
merely listing retrieved facts?

- **1 — Poor:** fragmented, contradictory, or unsupported reasoning; little
  useful synthesis.
- **3 — Adequate:** reasonable organization and comparison, but important
  connections or trade-offs are underdeveloped.
- **5 — Excellent:** integrates evidence coherently, distinguishes competing
  considerations, and makes conclusions proportional to the evidence.

## Clarity

How readable, well-structured, and precise is the report?

- **1 — Poor:** confusing, disorganized, repetitive, or difficult to interpret.
- **3 — Adequate:** understandable overall, with some verbosity, awkward
  structure, or imprecision.
- **5 — Excellent:** clear, concise relative to task complexity, logically
  structured, and easy to audit.

## Independence and corrections

Do not try to infer report provenance or condition identity, and do not discuss
scores before submitting your independent ratings. If you discover a clerical
mistake before seeing any other ratings or identity information, contact the
coordinator. Corrections must replace the whole submission; do not selectively
combine favorable rows from different versions.

These instructions define human judgments only. They contain no study result,
preferred outcome, or claim about which reports should score better.
