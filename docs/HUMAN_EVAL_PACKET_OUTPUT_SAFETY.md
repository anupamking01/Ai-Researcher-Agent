# Human-evaluation packet publication safety

The blinded human-evaluation packet is an identity-bearing research artifact.
Once annotators receive a packet, its blind IDs and coordinator mapping must not
be regenerated in place.

`scripts/build_human_eval_packet.py` therefore treats these four files as a
create-only bundle:

- `packet.jsonl`
- `blinding_key.csv`
- `ratings_template.csv`
- `manifest.json`

The builder may use an existing parent directory (for example one that already
contains an archived freeze), but it refuses to replace any of those packet
artifacts. `packet.jsonl` is created with exclusive file creation and acts as
the reservation point, so two cooperating builders cannot both publish to the
same destination after passing a preflight check.

A failed or interrupted build can leave a partial bundle. That partial state is
deliberately preserved for inspection and is not silently reused. Do not delete
or overwrite a packet that may already have been distributed. Use a new
versioned output root for a deliberate replacement and document why the earlier
packet was superseded before any ratings are collected.

This guardrail does not prove annotator independence, make all four writes an
atomic filesystem transaction, or protect against an unrelated process that
deletes files after publication. The packet verifier and the pre-unblinding
freeze verifier remain separate required provenance checks.
