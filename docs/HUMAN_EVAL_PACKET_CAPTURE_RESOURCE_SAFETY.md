# Bounded blinded-packet source custody

The human-evaluation packet producer reads frozen task metadata, experiment
traces, and the reports intended for blinded annotators. The independent packet
verifier shares its regular-file capture reader. This boundary precedes the
later frozen-rating and treatment-unblinded human-analysis snapshots.

Previously, a substituted FIFO could block when opened, before the regular-file
check, and a growing or oversized source could consume unbounded memory.
The reader now opens files nonblocking, checks regular-file type and the
initial byte size, reads only the initial size, probes one byte for growth,
and rechecks file and parent identity/metadata. Any observed growth,
truncation, early EOF, or pathname replacement fails closed.

The ceiling is 64 MiB per captured file and 64 MiB in aggregate across
packet-building trace/report inputs. Before any create-only destination is
reserved, the producer also checks the exact UTF-8 byte length of
packet.jsonl against this ceiling. Published artifact fingerprints use
the same checked reader rather than an unrestricted pathname reopen.
Oversized evidence must be reviewed as an explicit blocker, never silently
truncated or selectively removed to improve study outcomes.

These checks improve observable file custody and resource safety; they cannot
guarantee an atomic filesystem snapshot or prove historical source authenticity.
The packet verifier and blinded freeze remain separately required. All
regression fixtures are synthetic: no ratings are generated and no treatment
outcomes or preregistered methods are changed.
