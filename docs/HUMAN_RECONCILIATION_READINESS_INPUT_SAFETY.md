# Bounded inputs at the automated–human reconciliation readiness gate

`scripts/verify_human_reconciliation_readiness.py` verifies previously captured
automated and human analysis before descriptive reconciliation. These are
**metadata receipts, predeclared contract text, and analysis summaries** for a
frozen 10-task design—not arbitrary-size experiment datasets.

## Input capture rule

The readiness gate now applies a **16 MiB per-file byte bound** to every
descriptor-captured input: frozen reconciliation contract, automated analysis
and provenance, human analysis, and human analysis manifest. Before reading,
it requires a regular file and rejects an oversized `fstat` size. Each
`pread` request is limited to the remaining budget plus one detection byte;
the extra byte detects growth when a file becomes too large after the initial
file-size check. A second size check, before/after descriptor identity and
timestamp comparison, and the existing closing path/descriptor recheck remain
mandatory. Exceeding the bound fails closed without a success receipt.

This closes an independent resource-exhaustion path in the **human-validation
readiness step**: a sparse oversized receipt previously reached an unbounded
read, and a concurrently growing regular file could consume unpredictable
memory. It does not change research inputs, canonical measurements, frozen
inference, human rubrics, eligibility, or descriptive reconciliation equations.

## Evidence and limitations

Synthetic offline tests in
`tests/test_human_reconciliation_readiness_input_bounds.py` cover ordinary
small inputs, the exact limit, fail-before-read on a large sparse file,
growth during reading, contract-precedence validation, and mutation between
first capture and final recheck. All are synthetic safety controls; no actual
human submissions are created by these tests.

This is a **per-file resource limit and observable consistency check**, not an
atomic multi-file snapshot, immutable source store, signature, or provenance
authentication. A 16 MiB analysis receipt should be reviewed rather than
silently accepted with an increased limit; any change to the limit must be
separately justified and regression-tested. No result about inter-annotator
agreement or automated–human alignment is implied while real blinded ratings
remain outstanding.
