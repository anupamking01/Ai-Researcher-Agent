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

## Invisible directional-mark display integrity (prospective packets)

Before publishing a blinded packet, the offline content checker rejects three
invisible bidirectional marks (U+061C ARABIC LETTER MARK, U+200E LEFT-TO-RIGHT
MARK, U+200F RIGHT-TO-LEFT MARK) as well as the previously blocked explicit
embedding/override/isolate characters and deprecated directional controls
U+206A–U+206F. The policy checks the original question/report text, rendered
Markdown character references, and decoded link/title metadata. Invisible
marks can change the perceived order of identifiers, citations, or source URLs
without changing their underlying bytes; permitting them could make otherwise
identical blind review materials appear different to annotators. Synthetic
regressions cover raw marks, HTML character references, and percent-encoded
link metadata. Ordinary printable Arabic, Hebrew, Hindi, and other Unicode
text remains allowed, as do regular tabs and line breaks.

This is a conservative presentation-integrity rule for **future** blinded
human evaluation, not a claim that any historical report contained these marks
or that hidden markers are the only possible source of unblinding. If an
authentic recovered report contains a legitimate directional mark, preserve
its exact source bytes, record the display limitation, and resolve a
pre-distribution protocol deviation rather than silently editing the report.
The source-recovery gate, independent archival authentication, and recruitment
of two independent blinded annotators remain unmet. No human ratings or
historical measurements are produced or changed by this check.
