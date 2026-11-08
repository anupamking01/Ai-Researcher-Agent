# Diagnostic-pilot immutable frozen-price byte pin (summary schema v4)

## Risk and change

VERA's independent diagnostic-pilot cost auditor already recomputes USD estimates
from selected traces and a local dated rate table. But until schema v4, it
trusted the *current* file at that path. Editing the file and recomputing the
summary could silently replace the original 2026-09-08 pricing basis while
retaining the same displayed effective date, currency and source. An unchanged
rate table with altered whitespace is also a changed archival source byte set.

The exact originally committed 1,090-byte file
`experiments/openai_pricing_2026-09-08.json` is now independently anchored by
SHA-256 `35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace` in
`scripts/audit_pilot_cost_summary.py`. New standalone summaries identify
**schema version 4**, record their observed pricing-file SHA-256 in
`pricing_reference.sha256`, and are accepted by the independent postrun
auditor only when **both** the actual file's SHA-256 equals the pinned value
and the recorded summary digest equals the actual file. This verifies the
*input rate-table bytes* in addition to existing source-based token, cost,
missingness and per-arm operational reconciliation. An operator may not satisfy
the pin by editing both a rate table and its summary hash; doing so requires a
visible source-code change to the independent anchor itself. The offline test
suite separately verifies the checked-in price file still matches that anchor.

Schemas v1, v2 and v3 retain their original validation scopes. In particular,
v2/v3 cost arithmetic does not retroactively acquire independent price-byte
custody; a downgrade from v4 must not be described as satisfying the v4 gate.
An external independent saved digest or signed archive remains stronger than
an in-repository code constant, and Git history must be reviewed if the pin is
intentionally updated. The committed price table is a dated *research* rate
assumption, not an authenticated provider bill, proof that advertised rates
applied to each invocation, or evidence about long-context/cached pricing.

## Reproduction and status

```sh
python -m pytest -q tests/test_pilot_paired_summary_reconciliation.py
python -m scripts.validate_pilot_artifacts
```

The synthetic regressions exercise unchanged prices, falsified/missing
summary digests, byte-only price edits, coordinated price-and-hash edits,
and explicitly preserved schema-v3 compatibility. The default postrun command
requires genuine local diagnostic-pilot outputs; their absence is not a
regression or an invitation to rerun live experimental treatments.

This change does **not** rerun the diagnostic five-task pilot, the frozen
10-task automated main study, automated evaluators, or human raters. Pilot
metrics remain **diagnostic**; frozen automated main-study estimates keep their
post-collection analysis-plan, fixed-order and recovery-comparability caveats;
retrospective sensitivities remain **exploratory**. Independently authenticated
original main-study reports/traces and genuine blinded human validation are
still missing. Cost provenance validation does not resolve those gates.
