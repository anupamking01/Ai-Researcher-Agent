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
packet manifest **file**, runs both existing verifiers, checks the expected 40
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
`--research-manifest-sha256` argument.

A PASS requires genuine retained inputs, exact coordinator/evaluator run-ID
alignment for every treatment/task cell, both independent file-byte anchors,
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

Missing independently archived hashes are a **blocker to this stronger
pre-distribution claim**; rerunning an analysis or hashing freshly changed
files cannot supply historical anchoring. A mismatch requires investigation
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
