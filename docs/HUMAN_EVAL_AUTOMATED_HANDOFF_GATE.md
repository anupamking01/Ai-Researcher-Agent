# Coordinator gate: automated-run lineage to counterbalanced human handoff

**Status:** Optional read-only pre-distribution gate, before any human scores.
This does not alter the frozen human rubric, assignment, treatments,
confirmatory results, exploratory analyses, or statistical hypotheses.

## Why the joint check is needed

The existing `verify_human_eval_automated_run_lineage` checks that the
coordinator's 40 blinded reports correspond to the same run IDs as the
preserved common evaluator. Separately, the counterbalanced handoff verifier
checks that both annotator-facing distribution orders derive from one
externally pinned coordinator packet. Neither check alone proves **both**
that the actual distribution packets represent the evaluated run identities
and that the two distribution orders share the correct frozen source.

`scripts/verify_human_eval_automated_handoff.py` enforces the conjunction
as one coordinator-only, fail-closed operational check. It validates externally
retained pins for the historical input manifest **file** and the coordinator
packet manifest **file**. For the default frozen 4×10 task matrix it also
checks the canonical CSVs against the independently published
input-manifest **aggregate** digest before any lineage or distribution PASS;
a newly created file-byte pin cannot substitute for the historical digest.
For the genuine 40-cell study it also verifies the **exact original treatment
task-list bytes** via `scripts.verify_frozen_main_study_tasks` (treatment
workflow run `34620917346`, source revision
`c3c15e46a8eec3a8bbc24c968eedc0548172a897`, manifest-byte SHA-256
`5701df80036edb354f4f7d1efc409ea8f554a215f8c37da9d1a0b8ed01fdfd5f`).
The published CSV aggregate does not cover research question text; merely
re-pinning a coordinator packet cannot compensate for changed task questions.
This source-revision anchor is not independent signed archival custody.
It then runs both existing verifiers, checks the expected 40
cells, and re-fingerprints the shared handoff-file inputs across the
sequential verification window: both pinned manifests, the frozen task
manifest and guide, both automated CSVs, all four coordinator packet files,
and every file in each counterbalanced annotator-distribution bundle.
This additionally detects persistent changes to the first bundle while the
second is being checked.

## Procedure

Recover the original 40 treatment traces, Markdown reports, original
coordinator packet, both counterbalanced distribution directories, original
treatment and evaluator CSVs, and their retained archival input manifest.
Do **not** rerun treatments, alter reports, reselect samples, or reconstruct
the archival hashes from changed evidence.

Before distribution, obtain the two independently retained **file-byte**
SHA-256 hashes from the original restricted archival records:

```bash
python -m scripts.verify_human_eval_automated_handoff \
  --repo-root . \
  --packet-root outputs/human_eval \
  --canonical-root outputs/human_eval/annotator-canonical-v1 \
  --reverse-root outputs/human_eval/annotator-reverse-v1 \
  --task-manifest experiments/main_budget_tasks.json \
  --research-manifest <path-to-archived-main-study-input-manifest> \
  --research-manifest-sha256 <independently-retained-manifest-file-sha256> \
  --coordinator-manifest-sha256 <independently-retained-packet-manifest-file-sha256>
```

The published `4e94308472e87cc14b85e5911c40b5f72c63225862a347e624fc0725afd632aa`
main-study input-manifest **aggregate** digest is not the same as the SHA-256
of the JSON manifest *file*, and must not be substituted for the
`--research-manifest-sha256` argument. For the actual 40-cell study, the
gate now checks **both** values: the independently archived manifest-file
pin and the fixed published aggregate (over the same two canonical CSV
entries). It accepts an archived manifest at a different path without
mistaking its file hash for its aggregate fingerprint. A coherent replacement
of both CSVs and a newly pinned manifest will fail this historical check.
Custom-task test fixtures explicitly report
`published_frozen_input_anchor_verified: false` and
`original_treatment_run_task_manifest_verified: false`. Such diagnostics
cannot establish continuity with the historical study's CSVs **or questions**.

A PASS for the default genuine 40-cell study requires original retained inputs,
a match to the published aggregate **and original task-manifest bytes**,
exact coordinator/evaluator run-ID alignment for every treatment/task cell,
both independent file-byte anchors,
valid counterbalanced source-bound bundles, and unchanged observed source
bytes over the combined check. The receipt excludes human scores, rater
identities, coordinator key contents, and treatment-level effects. Store it
in coordinator-only records, never in annotator-facing bundles.

### Verify the actual delivery copy against the approved handoff

The combined receipt now records `bundle_manifest_sha256` separately for
`canonical` and `reverse`. Preserve this receipt independently, with the
original source pins, **before** transferring a bundle. For each actual delivered
or staged-to-send copy, use only its assigned manifest digest from that
approved receipt, not a digest recomputed from the delivery copy:

```bash
python -m scripts.export_human_eval_annotator_bundle \
  --verify-only \
  --output-root <actual-delivered-bundle-directory> \
  --expected-manifest-sha256 <trusted-digest-for-that-bundle>
```

This runs the existing source-free, treatment-blind packet and guide checks
but additionally rejects a coherent replacement of report bytes **and** local
manifest fingerprints after the coordinator's approved handoff. The unpinned
`--verify-only` command still provides useful local diagnostics, but cannot
authenticate a delivered copy. A PASS certifies exact agreement with the
previously approved bundle manifest, under the verifier's capture-window
limitations; it is not proof that the intended human received, read, or
independently rated those files. Do not give annotators the combined
coordinator receipt, research manifest, treatment/run mapping, or the second
annotator's bundle. If digest-sharing is needed, share only the one assigned
SHA-256 value through a separately trusted channel.

## Failure and scientific boundaries

Missing independently archived hashes or a changed original task manifest
are **blockers to this stronger pre-distribution claim**; rerunning an analysis
or hashing freshly changed files cannot supply historical anchoring. A mismatch requires investigation
against the original retained evidence, not substitution or treatment reruns.
The gate cannot prove the authenticity of the upstream archive, an atomic
snapshot spanning mutable filesystems, annotator independence, actual
blinding, informed consent, human score collection, or human-validation
conclusions. Each listed handoff file is captured under the existing bounded
regular-file reader and compared by SHA-256 before and after the two checks,
without keeping two copies of the report contents. This detects persistent
content changes but not an ABA mutation that reverts to the original bytes,
unobserved modifications to individual source traces/reports between the two
component verifiers, or later changes after the verification receipt.

This is not a human-evaluation result. The diagnostic pilot, frozen automated
confirmatory inference, exploratory analyses, and any future independently
collected and frozen human ratings remain distinct. Genuine two-rater blinded
scores on all 40 reports, provenance/attestation freeze, inter-annotator
agreement, and automated–human reconciliation are still outstanding.


## Composite full-matrix and diagnostic-status safeguard (11 November 2026)

The combined coordinator gate now independently checks that the two component
receipts report the **expected verification statuses**, that the automated
packet report count, evaluator run-ID count and counterbalanced distribution
report count are all exact Python integers equal to the full expected matrix,
and that the historical task matrix has exactly 40 cells. In particular,
**two matching partial counts no longer produce a successful joint receipt**.
These checks protect the composition boundary against incomplete, stale, or
regressed component contracts; they supplement rather than replace each
source-bound verifier's underlying row and fingerprint checks.

Synthetic/custom-task runs remain supported for offline development, but their
receipt status is now
`noncanonical_handoff_diagnostic_not_historical_release` and
`historical_40_cell_source_checks_completed` is false. Only the default,
fully source-checked historical matrix can return the existing
`automated_run_and_counterbalanced_handoff_verified` status. No receipt by
itself establishes an independently authenticated original report archive,
genuine annotator identities, human ratings or human-validation outcomes.
The missing September treatment/recovery source ZIPs remain an external
blocker; this change neither recreates them nor alters any frozen results.


## Component-receipt identity and byte reconciliation (11 November 2026)

The joint gate now requires both component PASS receipts to identify the same
schema version and study, and checks the automated task count and explicit
no-ratings/no-rerun flags. It also requires the counterbalanced verifier's
coordinator-manifest digest to equal the independently retained coordinator
pin and its declared presentation orders to be canonical then reverse.
Before issuing the final joint receipt it compares each component-reported
packet, ratings-template and annotator-guide SHA-256 value **for both bundles**
to its own earlier descriptor-captured bytes. A stale or incorrectly composed
upstream receipt therefore cannot supply a seemingly approved delivery digest
that differs from the actual files, even when the upstream component reports
success. Offline synthetic tests cover both orderings, all three digests,
contradictory component claims and malformed bundle maps.

These are cross-checks of the combined verifier's contract, not independent
archival attestation. They do not change original reports, automated outcomes,
blinded human procedures or collection status. Original treatment/recovery
archive recovery, independent source authentication and genuine human ratings
remain prerequisite gates; a valid local composite receipt alone does not
establish research completion or participant independence.


## Combined-window bundle inventory and identity check (11 November 2026)

The paired counterbalance verifier already checks its bundle inventory during
its own run, but the joint automated-to-human gate previously checked only
named file digests *after* that verifier returned. An extra coordinator-only
file inserted into an annotator directory in this gap could escape the final
hash comparison, exposing a blinding secret despite a successful joint receipt.
An existing file also could be replaced with identical bytes, leaving the
joint gate's content-only comparison unchanged.

The joint gate now snapshots the complete canonical and reverse distribution
inventories and each root/file inode/stat identity before its component checks.
After the two components return, it validates named bytes as before and then
requires both complete inventories and identities to match the starting
snapshots. Synthetic tests inject an extra secret-named file and replace the
same-byte annotator guide in each order after the paired component returns;
all must be rejected. No original study evidence or human ratings are touched.

This is an observable same-filesystem verification-window safeguard, **not**
an atomic snapshot, proof of trusted archives, or protection against mutations
after a receipt has been issued. The separately pinned delivered-copy check
remains mandatory before releasing a bundle to an eligible annotator.


## Coordinator and published-source same-byte replacement guard (11 November 2026)

The combined verifier's two bounded content captures already compared SHA-256
values across the full handoff window. Unlike the annotator distribution
bundles, however, coordinator-only files and the upstream frozen/published
inputs were not protected against *same-byte pathname replacement*. A changed
blinding-key inode, independently pinned manifest, frozen task source, guide or
measurement CSV could retain an identical digest while no longer being the
file observed at the start of verification.

The joint gate now snapshots each nondistribution source's pathname identity
(device/inode, mode, link count, size, mtime and ctime) before the combined
checks and requires it unchanged after the initial and final descriptor-held
byte captures. This supplements, rather than replaces, the original digest
checks and the full-inventory guard for the two annotator bundles. Synthetic
offline regressions replace coordinator keys/manifests, the source manifest,
and both automated CSVs with **byte-identical new inodes** after the paired
distribution component returns. All are rejected without touching original
research evidence or collecting ratings.

This establishes only observable local verification-window consistency, not
an atomic snapshot or independent custody of September's original reports.
It cannot detect transient mutations fully reversed between observations,
prove trusted timestamps or authentic annotator identities, or enable human
validation without independently authenticated original evidence and actual
independent ratings. Diagnostic pilot, post-collection designated-primary
automated analyses, exploratory robustness analyses and future genuine human
validation remain separate.
