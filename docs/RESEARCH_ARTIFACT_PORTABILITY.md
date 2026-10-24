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

## Multi-artifact capture coherence

The manifest generator and independent verifier both re-read every selected
artifact after completing the initial scan. The second pass checks the
descriptor-bound file's SHA-256, byte count, and filesystem identity against
the first pass. It fails closed when a file was overwritten, replaced with a
byte-identical different inode, removed, or replaced by a symlink after its
initial capture while another artifact was inspected. A signed/recomputed
aggregate manifest cannot turn a demonstrably mixed-time scan into a
successful verification.

This is a **two-pass consistency check**, not an atomic snapshot, lock, or
guarantee that all files existed in one unchanged state: concurrent changes
after an artifact's final recheck, including adversarial swap-and-restore,
can still escape detection. For strong simultaneous provenance, use an immutable
snapshot or locked source bundle obtained under an independently documented
capture procedure. The extra read I/O is deliberate. No existing frozen
study inputs are modified or re-evaluated.

**Boundary:** These are portability, path-identity, and current filesystem
alias safeguards, not claims that different names came from independent
sources or that SHA-256 proves data authenticity. No frozen study artifacts,
measurements, human ratings, treatment execution, or preregistered analysis
were changed.

Offline regression tests:
`python -m pytest -q tests/test_research_artifact_portable_paths.py tests/test_research_artifact_hardlink_aliases.py`.


## Manifest output is create-only

The fingerprint CLI's `--output` is a **new artifact destination**, not a
replace-in-place export. It previously used an unrestricted `write_text`, so
an incorrect destination could overwrite a frozen CSV, an existing fingerprint
manifest, or the target of a symlink. The writer now creates the destination
exclusively and refuses any existing file, including dangling symlinks.
It creates nested output directories while rejecting symlinked parent
components; on systems with directory-relative operations, creation is
anchored to checked directory descriptors. If a write fails, a newly created
incomplete destination is removed.

For example, writing `--output outputs/main_study_runs.csv` now fails
without changing preserved treatment evidence. To retain multiple captures,
choose a **new** versioned filename each time; no retry overwrites the old one.
Standard output (without `--output`) remains unchanged.

This is a **destination-safety safeguard**, not an atomic snapshot of changing
inputs or proof that source files were historically authentic. On platforms
without directory-relative operations, the fallback checks parent symlinks
but cannot guarantee race-free parent traversal. No real experiment, evaluator,
human rating, frozen rubric, or analysis has been modified.


## Optional independent manifest trust anchor

An artifact manifest is **self-consistent**, not self-authenticating. If a
mutable dataset and its manifest are both replaced, every artifact SHA-256 and
the aggregate digest can be recomputed and the unpinned verifier can still
pass. To detect this class of retrospective replacement, retain the exact
manifest-file SHA-256 **independently** (for example, in a reviewed,
access-controlled run record or immutable external log) at the time the
canonical snapshot is frozen.

Once that independently recorded lowercase 64-hex digest is available:

```bash
python scripts/verify_research_artifact_manifest.py \
  outputs/main_study_analysis_inputs_manifest.json \
  --expected-manifest-sha256 <independently-recorded-sha256>
```

The verifier checks the SHA-256 of the original manifest **file bytes**,
including JSON whitespace and newline, before accepting its entries; it
also checks that the manifest file's content and physical identity remain
stable during capture. This is distinct from the in-band aggregate digest,
which is calculated from canonicalized artifact entries. The optional pin
does not change existing manifests, default unpinned verification, treatment
data, or frozen inference.

**Trust boundary:** A digest copied from the same mutable folder at
verification time is not an independent pin. An attacker able to change the
reference digest too can bypass the protection. SHA-256 is byte identity,
not a digital signature, author attestation, immutable storage guarantee, or
proof of experimental validity. No canonical-study trust anchor is claimed
to exist merely because this option is implemented.
