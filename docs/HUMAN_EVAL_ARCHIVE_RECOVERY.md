# Recover the original automated-to-human VERA evidence (no outcome reruns)

**Status (2026-10-27): blocked on original report and handoff custody.**
This is an operational inventory and recovery plan, not an experiment or human-evaluation result.

## Why this is a research gate

VERA's versioned checkout contains the frozen automated-treatment/evaluator
CSVs and published input-manifest aggregate, but not the original 40 treatment
traces, Markdown report sources, coordinator blinded packet, or two distributable
annotator bundles. The combined automated-to-human handoff verifier is designed
to run against **original** sources with **independently retained** archival
manifest-file SHA-256 pins. Synthetic tests and a locally regenerated packet
cannot meet that original-evidence claim.

On 2026-10-27 the GitHub Actions artifacts endpoint returned **no artifacts**
for the original treatment workflow run 34620917346 and evaluator-recovery
run 34783525480. The canonical-analysis run 36070798723 still exposed its
10,270-byte analysis artifact (artifact ID 10837878458, expiry listed as
2026-12-23). This is an observation about artifact availability at that time,
not proof that the original reports are destroyed: local, restricted, offline
or institutional backups may exist.

## Read-only inventory

Run this diagnostic in the checkout, optionally passing external archive
locations and two *previously retained*, independently sourced file-byte
SHA-256 values:

```bash
python -m scripts.audit_human_eval_archive_readiness \
  --repo-root . \
  --trace-root <original-experiment-traces-directory> \
  --report-root <original-outputs-directory-containing-run-id-folders> \
  --packet-root <original-coordinator-packet-directory> \
  --canonical-root <original-canonical-distribution-directory> \
  --reverse-root <original-reverse-distribution-directory> \
  --research-manifest <original-archived-research-manifest.json> \
  --research-manifest-sha256 <independent-file-byte-sha256> \
  --coordinator-manifest-sha256 <independent-file-byte-sha256>
```

The JSON enumerates missing or unsafe file paths, the original-trace candidate
counts **by frozen treatment** and the Markdown report candidate count, plus
the canonical published automated-input fingerprint check. By default,
traces are sought under `outputs/experiment_traces/<variant>/<run-id>.json`
and reports under `outputs/<run-id>/research_report.md`; the two new root
arguments allow a read-only inventory of separately recovered evidence without
copying or rewriting it. A `40_matrix_candidates_unverified` status means
exactly 10 regular trace candidates exist under each of D3, D6, P6 and P6V,
with no duplicated run-id filenames or unexpected root entries. A
`40_report_candidates_unverified` status means that the corresponding 40
regular Markdown filenames were present. Neither status validates JSON,
run/task identities, report content, report-to-trace linkage, or historical
custody. Symlinks and missing/unsafe report candidates block readiness; a
balanced but incoherent archive can still pass this **structural inventory**.
When a historical manifest-file SHA-256 is supplied, the inventory now compares
it against the bounded, descriptor-captured bytes of the corresponding research
or coordinator manifest. A mismatch, missing/unsafe manifest, or unstable/oversized
capture is an explicit blocker; syntax-valid pins alone no longer satisfy the
readiness preflight. `pin_matches_file_not_authenticated` means only that the
local bytes match the supplied value, **not** that the pin has trustworthy
independent historical custody. Never compute a new pin from a suspect archive
and present it as an earlier retained fingerprint.
Even the zero-blocker
`candidate_inputs_present_not_verified` status is **not** an acceptance receipt.
The command never reads report or trace contents, rating submissions, or a
blinding key; it never writes files or calls live APIs. Even with external
archive roots, the full handoff verifier requires approved original evidence
staged in its documented source layout, with independent archival pins. `--require-candidates` exits nonzero for missing inputs.

## Accept only independently retained evidence

1. Search authorized offline storage or archival exports for the **unchanged**
   completed 40 experimental traces and each trace's associated Markdown report,
   preserving original paths and original bytes. Do not regenerate treatments
   or choose newer/better reports to fill missing cells.
2. Recover the original coordinator packet and both treatment-blind
   counterbalanced distribution bundles, if already created. If they were
   never generated, distinguish first-time prospective packet preparation from
   recovery of historical source reports; do not describe new packets as
   historical originals.
3. Recover the original research-input manifest JSON and the coordinator
   manifest. Their file-byte SHA-256 hashes must be obtained from independently
   retained trustworthy records, not recomputed from possibly altered copies.
   The published aggregate `4e94308472e87cc14b85e5911c40b5f72c63225862a347e624fc0725afd632aa`
   is **not** either manifest-file hash.
4. Only once genuine sources and independent pins are available, run
   `python -m scripts.verify_human_eval_automated_handoff` as documented in
   `docs/HUMAN_EVAL_AUTOMATED_HANDOFF_GATE.md`. Investigate mismatches; never
   rewrite the inputs, re-pin inconsistent archives or rerun treatments to
   obtain a passing result.
5. Retain the approved coordinator receipt separately and verify actual
   delivery copies against its individual bundle-manifest hashes before
   independent blinded scoring by two eligible annotators.

The pilot remains diagnostic, automated confirmatory findings remain frozen,
secondary/Pareto observations remain exploratory, and **human validation
remains pending**. Neither the inventory nor a passing archival handoff
constitutes an independent human judgment.
