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

## Coordinator-only file confidentiality at creation and handoff

The private `blinding_key.csv` and `manifest.json` (which holds the
256-bit permutation seed) are created **owner-readable/writable only
(`0600`)**, regardless of a permissive process umask. Permissions are set
atomically with exclusive file creation, not tightened after the secret
has already been written. Annotator-facing `packet.jsonl` and
`ratings_template.csv` retain ordinary umask-based file permissions.

Both annotator bundle export and source-bound bundle verification reject
a coordinator key or manifest with group/other permission bits or a
non-regular file type before copying the source. Existing legacy packets
with relaxed access permissions must not be distributed for genuine
blinded scoring: merely changing the mode afterwards cannot establish
that their treatment mapping or seed was never observed. Preserve
superseded versions for provenance; construct a fresh packet from
independently authenticated original evidence before any scoring.

These POSIX file-mode checks are defense in depth, **not evidence of
historical secrecy**. Coordinators must still use a restricted local
directory/account, protect backups, restrict cloud-sharing ACLs and
logs, and distribute only the separately verified annotator bundle.

This guardrail does not prove annotator independence, make all four writes an
atomic filesystem transaction, or protect against an unrelated process that
deletes files after publication. The packet verifier and the pre-unblinding
freeze verifier remain separate required provenance checks.
