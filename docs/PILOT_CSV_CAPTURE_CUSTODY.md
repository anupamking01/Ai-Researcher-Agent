# Diagnostic-pilot CSV: bounded source capture and alias custody

The schema-v5 postrun validator independently reconciles the entire
`pilot_runs.csv` against selected pilot traces. Previously it read the
CSV by pathname with no byte bound. A synthetic oversized file could consume
unbounded input resources, and replacement or in-place mutation between path
checks and parsing could cause an unreviewed generation of CSV bytes to be
validated. The schema-v5 audit now captures one **at-most 2 MiB** CSV as
bytes from a held descriptor before it invokes the CSV parser.

The capture requires a regular file with one hard link, rejects symlinks using
`O_NOFOLLOW`, uses nonblocking open to avoid hanging on special files, and
reconciles file identity, size, and modification/change timestamps between
the initial descriptor, final descriptor and final pathname. Read growth,
truncation, hard-link aliases and observed path replacement fail closed. The
entire bounded snapshot is decoded as UTF-8 and parsed with the pre-existing
strict CSV reader; the 27-column row and frozen trace/pricing checks are
unchanged. The limit is deliberately generous relative to 15 diagnostic
runs and does not truncate or select observations. Earlier summary schemas
do not acquire the v5 CSV gate retroactively.

Run offline synthetic regressions:

```bash
python -m pytest -q tests/test_pilot_csv_source_reconciliation.py
python -m pytest -q
```

This improves local parsing robustness and prevents observed file changes
during capture. It is **not** a cryptographic signed snapshot, a guarantee
against a privileged adversary capable of manipulating filesystem timestamps,
or external authentication of original experiment traces. No treatment,
model evaluation, frozen pricing, results, or human ratings are changed.
The five-task pilot remains diagnostic, frozen automated findings retain
their post-collection chronology and historical evaluator qualifications,
sensitivity results remain exploratory, and blinded human validation remains
blocked until independent original-report/trace custody is established.
