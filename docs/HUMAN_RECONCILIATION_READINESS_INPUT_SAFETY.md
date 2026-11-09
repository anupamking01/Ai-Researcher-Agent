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

## Strict finite JSON-number decoding at reconciliation preflight

The independent reconciliation-readiness reader rejects nonstandard JSON
numeric constants (`NaN`, `Infinity`, and `-Infinity`) and decimal
exponents that overflow to nonfinite Python floats (for example, `1e999`).
It also rejects integer tokens exceeding **128 decimal digits** before
converting them, keeping even a file below the 16 MiB byte bound from
carrying an unreasonably large integer token. Numeric validation converts
ordinary Python integers through a guarded finite-float conversion so that
injected extreme values fail as `ValueError`, not an uncaught
`OverflowError`. JSON `null`, booleans, ordinary finite fractions, and
string literals containing these words remain valid at the decoder boundary.

These are *readiness-layer* checks on already collected automated and human
analysis receipts, complementary to upstream independent output verification;
they neither authenticate original missing treatment reports nor change
the frozen analysis. Synthetic tests in
`tests/test_human_reconciliation_readiness_json_numbers.py` cover illegal
constants, exponent overflow, integer-token limits, nested values, valid
boundary values, the preserved automated snapshot, and direct numeric
overflow. No treatments, evaluations, analyses, or human ratings were rerun
or generated. Pilot observations remain diagnostic, frozen automated
designated-primary findings retain post-collection plan-timing qualifications,
retrospective sensitivity findings remain exploratory, and human validation
is pending original-source recovery and eligible annotators.
