# Cross-platform research-artifact path identity

Research input fingerprints are byte-level SHA-256 bindings, but a valid hash
alone cannot guarantee that *two paths* continue to denote distinct artifacts
when copied or checked out on another operating system.

The offline manifest generator and independent verifier now reject ambiguous
path identities, before an archive or analysis is treated as reproducible:

- different path spellings that collide under conservative Unicode NFKC and
  case folding (for example, `Run.csv` versus `run.csv`, or composed versus
  decomposed accented characters);
- Windows reserved device names, alternate-data-stream separators, trailing
  dots/spaces, and other forbidden path characters;
- compatibility characters that normalize into path separators, and invisible
  Unicode formatting controls within artifact names.

The verifier applies this check to every manifest entry even when an externally
created manifest has valid individual hashes and a correctly recomputed
aggregate digest. The generator applies the same rule to newly selected files.
Ordinary distinct canonical paths continue to round-trip unchanged.

## Physical file aliases (hard links)

Two distinct, portable names can still address **the same underlying file**.
Both the manifest generator and the independent verifier now reject multiple
selected artifact paths whose checked file descriptors have the same filesystem
`(device, inode)` identity. This closes a physical-alias loophole that byte
hashes and spelling-based path checks cannot detect. A manually recomputed
aggregate hash does not bypass verification. The original two-value
`fingerprint_regular_file()` API is unchanged.

Separately stored files with *identical bytes* remain valid: content equality
alone does not imply the names are aliases. This safeguard assumes a filesystem
that exposes stable, meaningful file identities; it does not verify historical
source independence, prove authenticity, or attest that files were originally
collected from separate systems. Hard links not listed in a manifest are not
discoverable by this check.

**Boundary:** These are portability, path-identity, and current filesystem
alias safeguards, not claims that different names came from independent
sources or that SHA-256 proves data authenticity. No frozen study artifacts,
measurements, human ratings, treatment execution, or preregistered analysis
were changed.

Offline regression tests:
`python -m pytest -q tests/test_research_artifact_portable_paths.py tests/test_research_artifact_hardlink_aliases.py`.
