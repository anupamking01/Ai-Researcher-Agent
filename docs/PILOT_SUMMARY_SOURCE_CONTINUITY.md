# Diagnostic-pilot trace roster continuity before summary publication

This safeguard closes a *between-file and prepublication* gap in the standalone
offline diagnostic-pilot summarizer. Individual source traces were already
bounded, descriptor-read and checked for concurrent changes **during their own
reads**. Previously, however, an early trace could change after being read
while later traces were processed or summary/CSV files were staged. The
create-only output publisher could then preserve a derived pair of artifacts
whose selected sources no longer matched the local source roster.

Before parsing, the summarizer now captures a bounded, frozen-design roster of
D6/P6/P6V trace paths and each selected file's device/inode, mode/link count,
size and nanosecond timestamps. It independently performs the existing strict
descriptor-held parse. After preparing both derived artifacts, the publisher
re-enumerates the same bounded roster and checks the captured metadata
**immediately before each create-only hard-link publication**. A changed,
removed, replaced or newly added source aborts publication; if a change is
detected before the second link, the publisher rolls back only its own first
linked output and removes staging files. It does not silently select a retry,
impute a missing task, or alter a recorded observation.

Reproduce using only synthetic temporary traces:

```sh
python -m pytest -q tests/test_pilot_summary_source_continuity.py
python -m pytest -q tests/test_pilot_trace_capture_bounds.py tests/test_pilot_summary_create_only_publication.py
```

The dedicated tests cover stable sources, in-place modification, same-byte
pathname replacement, roster additions/removals, modification after all traces
were parsed, and a change between the two publication links with rollback.

**Limits:** This metadata-based best-effort check is not an atomic filesystem
snapshot, cryptographic archive of source bytes, external evidence custody, or
defense against an adversary able to restore all observed metadata. It does not
protect after successful publication. The frozen pricing fingerprint has a
separate independent audit; this change governs selected pilot *traces* only.
The five-task pilot remains diagnostic. Frozen main-study automated claims
remain qualified by post-collection analysis-plan timing, historical fixed
treatment ordering, evaluator recovery comparability, and missing original
source custody; sensitivity work is exploratory. It adds no confirmatory
inference and supplies no real human ratings or blinded human validation.
