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
annotator-facing byte streams:

- `packet.jsonl`
- `ratings_template.csv`

It also writes `annotator_manifest.json`, which contains only fingerprints of
those two files and an explicit declaration that coordinator artifacts are not
included.

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
source/mapping verifier. It snapshots packet artifacts before verification, so a
change to the live coordinator packet after verification cannot silently change
the bytes copied to the annotator bundle.

The destination must not already exist. Publication writes only the expected
annotator artifacts, fingerprints them, and verifies the resulting directory.
The verifier rejects extra files, including a coordinator blinding key copied
into the distribution directory after export.

## Limits

This safeguard prevents accidental file-level leakage; it is not a substitute
for procedural blinding. Annotators should still receive no treatment labels,
coordinator metadata, hypotheses, or repository instructions that reveal
treatment identity.

A valid distribution bundle also does not imply that ratings have been
collected, that inter-annotator agreement is adequate, or that any
human-validation conclusion exists. Real blinded annotations remain pending
until they are actually collected and frozen under the existing protocol.
