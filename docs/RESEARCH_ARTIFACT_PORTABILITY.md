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

**Boundary:** This is a portability and *path* identity check, not a claim that
files with different names came from independent sources, or that SHA-256 proves
data authenticity. It does not alter frozen study artifacts, measurements,
human ratings, treatment execution, or the preregistered analysis plan.

Offline regression tests: `python -m pytest -q tests/test_research_artifact_portable_paths.py`.
