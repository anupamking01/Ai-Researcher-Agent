# Human-analysis output producer/verifier byte-size contract

Human-analysis output is complementary to the **frozen automated confirmatory**
results. The result publisher emits `analysis.json`, `analysis.md`, and
`analysis_manifest.json`. Its independent verifier also snapshots those three
files and the local implementation/environment sources used for provenance.

## Distinct failure mode

The independent output verifier previously called `os.pread` repeatedly until
EOF without a byte ceiling, even when reading a very large regular file. A
growing file could consume unbounded memory before the existing identity checks
failed. The producer had no matching output limit, so it could publish a bundle
that a bounded verifier would later reject.

## Safeguard

`MAX_HUMAN_ANALYSIS_ARTIFACT_BYTES = 16 MiB` is declared by the producer and
consumed by the independent verifier. The producer rejects *serialized UTF-8
bytes* for each of its three artifacts **before staging any output directory**.
The verifier checks the opened descriptor's regular-file type and declared
length before reading, reads exactly that length in bounded chunks, probes one
additional byte for observable growth, rejects early EOF, and retains the
existing metadata, inode, pathname, and directory binding checks. The same
reader bounds the independently captured source/environment provenance files.

The limit does **not** cap raw research datasets, treatment traces, blinded
annotation collection, or frozen input receipts. It is a memory-safety and
producer/verifier compatibility contract for human-analysis *result artifacts*
and verifier-owned source snapshots. No model or evaluator is run.

Synthetic regressions cover exact-boundary inputs, an oversized sparse file
rejected before any read, concurrent append, early EOF, bounded read sizes,
and rejection of oversized producer JSON/Markdown/manifest before reserving
an output destination.

## What this does not establish

A SHA-256 digest or consistent local read does not prove a file's historical
authenticity, provide an atomic multi-file snapshot, or prevent modification
after the last verification observation. Do not treat these engineering tests
as human ratings, inter-annotator agreement, automated–human reconciliation,
or manuscript evidence. Pilot, automated confirmatory, exploratory, and
pending human-validation findings remain distinct.
