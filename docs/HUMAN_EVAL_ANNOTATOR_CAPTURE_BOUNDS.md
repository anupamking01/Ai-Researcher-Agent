# Annotator-distribution bounded evidence capture

Status: research-engineering safeguard; **no human ratings or experimental outcomes are produced**.

The standalone annotator-bundle exporter and verifier both read coordinator and
annotator-facing files. Before this change, their shared `_regular_bytes`
helper used unrestricted `Path.read_bytes()`: a large or growing file could
consume unbounded memory before any packet validation ran. An input could also
be replaced between a pathname check and the read.

The helper now delegates to the existing captured regular-file reader in
`scripts/build_human_eval_packet.py`. This **reuses** the frozen packet
producer's **64 MiB per-file** bound, including coordinator packet, ratings
template, key/manifest, published packet, annotator guide, output manifest,
and content-validator source reads. It captures an initially observed file
length, checks for EOF or trailing growth, holds file and parent directory
descriptors, and verifies regular-file and path identity before accepting bytes.
It rejects symlinks, FIFOs, and observable in-place or replacement changes.
Sparse oversized fixtures test rejection without creating large payloads.

The new offline regressions exercise clean capture, each coordinator artifact
over the size limit, published packet over the size limit, non-regular inputs,
same-byte replacement, parent replacement, truncation, and growth. Run:

```bash
python -m pytest -q tests/test_human_eval_annotator_export_capture_bounds.py
python -m pytest -q tests/test_human_eval_annotator_export.py tests/test_human_eval_annotator_bundle_contract.py
```

**Boundaries:** This is a per-file observable-consistency/resource limit, not an
atomic multi-file snapshot or proof that an annotator has rated a report.
Existing coordinator packet and annotator-bundle source-bound verification
remain mandatory. Captures and hashes do not establish historical authenticity.
The frozen rubrics, blinded mapping, confirmatory results, exploratory analyses,
and pending genuine human-validation gate are unchanged.


## Bounded distribution-directory inventory (11 November 2026)

The four-file allowlist is also a **resource boundary**. The previous
`Path.iterdir()` set-comprehension materialized every entry in a candidate
annotator directory *before* discovering that an extra coordinator file or
other undeclared content made the bundle unsafe for distribution. Large or
adversarial directory inventories could consume excessive memory during
preflight, delaying detection of a blinding-contamination risk.

`_require_annotator_artifact_set` now iterates with `os.scandir()` and
fails immediately on the **fifth** directory entry, without enumerating
the rest. Exactly four correctly named entries continue to pass; missing
or substituted names fail with the original allowlist diagnostics. Offline
synthetic tests cover clean/missing inventories and an instrumented iterator
that fails if the verifier requests a sixth entry.

This bounds **entry enumeration**, not overall filesystem lookup latency or
the later per-file byte captures. It does not authenticate historical source
archives, an actual delivery, independent raters, or human scores.
