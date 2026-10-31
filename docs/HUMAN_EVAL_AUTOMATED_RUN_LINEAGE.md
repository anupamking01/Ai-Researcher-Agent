# Cross-check human packet runs against the frozen automated evaluator

**Scope:** Optional coordinator-only, treatment-blind *to annotators* and
read-only alignment gate. No human annotations have yet been collected.
This check neither changes the automated confirmatory analysis nor introduces
a new human-validation outcome, hypothesis, or treatment run.

## Motivation

The packet verifier establishes that each blinded item corresponds to a
persisted trace and Markdown report. The automated main-study verifier
establishes internal agreement between treatment and common-evaluator
measurements. Their frozen task/treatment matrices can nevertheless agree even
when the automated evaluator's **run ID for one treatment/task cell** differs
from the run ID of the report handed to a human annotator.

Comparing only the same ten task IDs is therefore insufficient for a
defensible automated–human reconciliation. This independent optional audit
binds all **40 cell-specific run IDs** in the coordinator's blinding key to the
corresponding **40 run IDs** in the preserved common-evaluator CSV. It also
requires the same exact matrix in the preserved main treatment CSV and checks
the available treatment/evaluator claims-checked mirror.

## Run the check before annotator distribution

Run from the selected checked-out repository root with all genuine, previously
preserved sources restored **without regenerating treatments or evaluators**:

\`\`\`bash
python -m scripts.verify_human_eval_automated_run_lineage \
  --repo-root . \
  --packet-root outputs/human_eval \
  --task-manifest experiments/main_budget_tasks.json \
  --research-manifest outputs/main_study_input_manifest.json \
  --expected-manifest-sha256 <independently-retained-SHA256-of-manifest-file>
\`\`\`

The actual manifest path depends on where the canonical manifest was
preserved; do not guess a path or compute the expected hash from a freshly
rewritten manifest and describe that as independent anchoring. The original
canonical analysis published its input-manifest **aggregate** SHA-256 as
\`4e94308472e87cc14b85e5911c40b5f72c63225862a347e624fc0725afd632aa\`.
That aggregate fingerprint is **not** interchangeable with the
\`--expected-manifest-sha256\` argument, which is the SHA-256 of the
*manifest file bytes*. Use the separately archived exact manifest-file hash.

Without \`--research-manifest\` and
\`--expected-manifest-sha256\`, the command still runs a **diagnostic**
alignment check but labels the archive as **not externally pinned**.

The command requires:

- exact 4×10 cell coverage in the coordinator's key, treatment CSV, and common-evaluator CSV;
- distinct, well-formed run IDs in the key and evaluator CSV, matched for
  **each** treatment/task cell (not merely as a set);
- the existing scientific row-domain checks and the historical treatment
  CSV's available claims-checked mirror;
- the existing packet verification against persisted traces, reports, task
  manifest, source fingerprints, and seeded blind-ID mapping;
- optional independently pinned archival manifest binding both canonical CSVs.

It reports counts and provenance flags only; it never prints the coordinator
key, run IDs, scores, report contents, or per-treatment outcomes. Retain the
blinding key and input sources in coordinator-only storage. No ratings need
exist for this check.

## Interpretation and limitations

A pass establishes an observed chain from a blinded packet item to its
persisted report run and the common evaluator's run ID for the same cell.
It **does not** prove that an annotator is human, independent, or remained
blind; does not authenticate original treatment generation or report quality;
and is not an atomic snapshot across separate mutable filesystems. The
external archival hash protects only the declared manifest bytes under
the separately retained trust assumption. Cross-window file rereads detect
observable changes, not adversarial changes that leave no trace.

A failure must be investigated against the original retained artifacts.
Do not choose a different report or rerun a treatment to obtain a match or
more favorable result. Document any discrepancy as a provenance problem and
keep the affected human-validation gate closed. Preserve the diagnostic pilot,
frozen automated confirmatory findings, exploratory analyses, and future
blinded human-validation results as distinct categories.

This check is an additional audit, not a modification of the frozen human
rubric, analysis plan, assignment plan, or existing provenance receipts.
