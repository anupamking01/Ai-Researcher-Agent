# Diagnostic-pilot trace roster continuity before summary publication

This safeguard closes a *between-file and prepublication* gap in the standalone
offline diagnostic-pilot summarizer. Individual source traces were already
bounded, descriptor-read and checked for concurrent changes **during their own
reads**. Previously, however, an early trace could change after being read
while later traces were processed or summary/CSV files were staged. The
create-only output publisher could then preserve a derived pair of artifacts
whose selected sources no longer matched the local source roster.

Before parsing, the summarizer captures a bounded, frozen-design roster of
D6/P6/P6V trace paths, device/inode, mode/link count, size, nanosecond
timestamps, **and SHA-256 of descriptor-held source bytes**. The independent
strict JSON parse must consume bytes matching the initial digest. After
preparing both derived artifacts, the publisher re-enumerates the bounded roster
and re-reads bounded source bytes, checking both identity metadata and SHA-256
**immediately before each create-only hard-link publication**. This detects
same-size source edits even when metadata appears unchanged. A changed,
removed, replaced or newly added source aborts publication; if a change is
detected before the second link, the publisher rolls back only its own first
linked output and removes staging files. It does not silently select a retry,
impute a missing task, or alter a recorded observation.

Reproduce using only synthetic temporary traces:

```sh
python -m pytest -q tests/test_pilot_summary_source_continuity.py
python -m pytest -q tests/test_pilot_trace_capture_bounds.py tests/test_pilot_summary_create_only_publication.py
```

The dedicated synthetic tests cover stable sources, in-place modification,
same-byte pathname replacement, roster additions/removals, source-byte changes
with metadata checks deliberately masked, mismatch between snapshot and parse,
modification after all traces were parsed, and a change between the two
publication links with rollback.

**Limits:** This bounded metadata-plus-SHA-256 continuity check is not an
atomic filesystem snapshot, externally authenticated source archive, or proof
that original historical traces were genuine. An adversary who changes the
inputs between separate checks and restores the original bytes before each
check may evade detection. The new checks also do not protect against
postpublication file changes. Each trace is re-read for hashing before both
links; the 8 MiB per-trace cap keeps this bounded. The frozen pricing fingerprint has a
separate independent audit; this change governs selected pilot *traces* only.
The five-task pilot remains diagnostic. Frozen main-study automated claims
remain qualified by post-collection analysis-plan timing, historical fixed
treatment ordering, evaluator recovery comparability, and missing original
source custody; sensitivity work is exploratory. It adds no confirmatory
inference and supplies no real human ratings or blinded human validation.
