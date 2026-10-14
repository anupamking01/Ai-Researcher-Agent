# Human-evaluation annotator distribution

This implementation note defines the safe handoff from the coordinator-side
human-evaluation packet to annotators. It does not change the frozen rating
rubric, treatment outputs, automated analysis, or human-validation estimands.

## Why a separate distribution bundle exists

The coordinator packet directory contains both annotator-facing files and
coordinator-only provenance, including `blinding_key.csv` and packet metadata.
Sending the directory itself creates an avoidable risk of exposing treatment
identity or other blinding information.

Use `scripts/export_human_eval_annotator_bundle.py` to create a clean,
create-only distribution directory. The exporter first snapshots the complete
coordinator packet, verifies that captured snapshot with
`scripts/verify_human_eval_packet.py`, and only then copies the two
coordinator-generated annotator-facing byte streams plus the independently
frozen treatment-blind guide:

- `packet.jsonl`
- `ratings_template.csv`
- `annotator_instructions.md`

It also writes `annotator_manifest.json`, which contains only fingerprints of
those three files, the treatment-blind content-audit runtime contract, and an
explicit declaration that coordinator artifacts are not included.

## Recommended workflow

After building the coordinator packet and before sending anything to annotators:

    python scripts/verify_human_eval_packet.py

Then create a fresh distribution directory:

    python scripts/export_human_eval_annotator_bundle.py \
      --output-root outputs/human_eval/annotator-bundle-v1

Verify it again immediately before distribution:

    python scripts/export_human_eval_annotator_bundle.py \
      --output-root outputs/human_eval/annotator-bundle-v1 \
      --verify-only

Distribute the contents of that directory, not the coordinator packet root.

## Integrity properties

The exporter fails closed if the coordinator packet does not pass its existing
source/mapping verifier or if the guide no longer matches its frozen SHA-256.
It snapshots packet artifacts before verification, so a change to the live
coordinator packet after verification cannot silently change the bytes copied
to the annotator bundle. The guide contains the full five-dimension rubric and
scoring procedure without treatment labels, hypotheses, mappings, or results.

The destination must not already exist. Publication writes only the expected
annotator artifacts, snapshots the completed directory, verifies that captured
revision, and requires its packet and template bytes to equal the already
verified coordinator snapshot. The success receipt records this source binding
and the verified coordinator-manifest SHA-256. The verifier rejects extra files,
including a coordinator blinding key copied into the distribution directory
after export.

Publication is built in a descriptor-bound staging directory. The exporter
creates all three files relative to the opened staging inode rather than
repeatedly resolving its path, checks that path-to-inode binding around
snapshot verification, and requires the captured annotator manifest to equal
the exact bytes it generated rather than a semantically equivalent JSON
document. Only after those checks does Linux `renameat2(RENAME_NOREPLACE)`
atomically install the staged directory at the requested output path. A
competing file, directory, or symlink at that path is never replaced. The
exporter then requires the published path to name the opened inode before it
returns the receipt. Persistent staging replacement, a redirected write, a
coherent manifest replacement, or a competing destination thus fails closed
without a success receipt. Platforms without atomic no-replace directory
publication are rejected rather than using a racy check-then-rename fallback.
If publication fails after staging begins, the staging directory is retained:
automatic pathname cleanup could delete data from a concurrent replacement.
An operator may inspect and remove a failed `.annotator-bundle-v1.staging-*`
directory only after confirming no other process owns it.

Independent distribution verification also enforces a plain-text packet contract:
all four packet fields must be nonempty strings, not nested JSON objects,
numbers, or arrays that could conceal coordinator metadata. The manifest's
`n_reports` must be an integer exactly matching the number of packet items,
and the ratings-template blind IDs must appear once each in precisely the
packet's order. A bundle with correctly recomputed local SHA-256 fingerprints
is rejected when any of those semantic checks fail. These checks preserve the
already-frozen protocol; they neither generate ratings nor open treatment IDs.

The standalone verifier also rejects duplicate JSON members at any depth in
the packet or manifest, including names made equivalent by Unicode escapes.
The manifest schema is closed: only the declared distribution fields are
accepted, and the optional distribution note must exactly match the producer's
fixed safety notice. This prevents last-value-wins parsing or added manifest
metadata from concealing treatment information in a bundle declared safe for
annotators.

The standalone verifier requires `annotator_instructions.md` to match the
frozen guide fingerprint even if its local manifest fingerprint has been
recomputed. Source-bound verification additionally requires its bytes to match
the selected frozen guide source file.

The manifest also binds the runtime semantics used to audit annotator-visible
content: Python implementation/version, Unicode database version, exact
`markdown-it-py` and delegated `mdurl` versions, CommonMark preset, and renderer
options. Standalone and source-bound verification fail closed when this contract
is absent or differs from the verification environment. This preserves what
“rendered annotator-visible text” meant when the distribution was created;
source bytes alone do not capture parser behavior.

## Limits

This safeguard prevents accidental file-level leakage; it is not a substitute
for procedural blinding. Annotators should still receive no treatment labels,
coordinator metadata, hypotheses, or repository instructions that reveal
treatment identity.

A valid distribution bundle also does not imply that ratings have been
collected, that inter-annotator agreement is adequate, or that any
human-validation conclusion exists. Real blinded annotations remain pending
until they are actually collected and frozen under the existing protocol.


## Coordinator source-bound verification

The ordinary `--verify-only` mode checks that a distribution directory is
internally well formed and that its local fingerprints match its current
contents. That is useful for annotator-side transfer checks, but local
consistency cannot by itself prove origin: someone could change
`packet.jsonl` and recompute `annotator_manifest.json` to match.

The default export command now performs source-bound verification before it
reports success, using the same captured coordinator revision that supplied the
published bytes. The command fails if a coherently replaced packet or template
is present when the completed output is snapshotted.

Before distribution, the coordinator should therefore also run:

    python scripts/export_human_eval_annotator_bundle.py \
      --packet-root outputs/human_eval \
      --output-root outputs/human_eval/annotator-bundle-v1 \
      --verify-against-source

This stronger mode captures the coordinator packet and annotator bundle once,
verifies the captured coordinator packet with the existing provenance gate,
verifies the captured annotator bundle locally, and then requires byte-for-byte
identity for `packet.jsonl` and `ratings_template.csv`. The returned
coordinator-only receipt records that source binding and the SHA-256 of the
verified coordinator manifest; those details are not added to the annotator
bundle.

Both sides are snapshotted before verification, so a later change to either
live directory cannot change the bytes that were compared. These snapshot and
identity checks are coordinator-side provenance checks, not filesystem locks:
they cannot detect every transient staging rename/replacement that is restored
between point-in-time checks, or prevent replacement of the published path
after the final check. Retain the verified bundle bytes or distribute them
immediately through the controlled annotation workflow.
