# Frozen diagnostic-pilot pricing-source continuity

The standalone diagnostic-pilot summarizer now binds **the pricing bytes used
to compute costs** to **the SHA-256 published in the summary**, and verifies
that the same frozen local source generation remains in place immediately
before publishing each create-only JSON/CSV file. Previously the CLI loaded
pricing, later re-read the pathname for the summary fingerprint, and published
without rechecking the pricing document. A concurrent rate-table replacement
could therefore leave mutually inconsistent derived research artifacts.

The loader captures at most 64 KiB from a held, no-follow descriptor; accepts
only a single-link regular file; verifies device/inode, mode, link count,
size, and high-resolution timestamps against the pathname; and parses the
captured bytes with strict duplicate-key/nonfinite-value rejection. It reuses
the **independent historical pricing SHA-256 pin** in
`scripts/audit_pilot_cost_summary.py`, not a self-declared digest. The
summary's `pricing_reference.sha256` comes from those same captured bytes.
Before each output link, the producer recaptures the price document and
compares both its immutable pin and local identity snapshot. If pricing
changes between the two links, only the first output created by that
publication attempt is removed; no earlier output or competing file is
overwritten.

Reproduce offline with only temporary synthetic traces:

```sh
python -m pytest -q tests/test_pilot_pricing_source_continuity.py
python -m pytest -q tests/test_pilot_summary_source_continuity.py tests/test_pilot_summarizer_source_integrity.py
```

This is an **upstream production-time** source-consistency gate, distinct
from the already-existing *downstream independent* frozen-price cost audit.
It does not establish that historical model prices reflect invoices, prove
provider billing authenticity, yield an atomic filesystem snapshot, or
authenticate missing original main-study reports. Diagnostic-pilot
measurements remain diagnostic; automated main-study results remain
historically qualified; retrospective sensitivity work remains exploratory;
and no human judgments are represented as collected.
