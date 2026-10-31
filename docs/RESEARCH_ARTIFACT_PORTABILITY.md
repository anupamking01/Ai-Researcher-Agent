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
anchored to checked directory descriptors. If a write fails, cleanup only removes the incomplete destination when its
physical filesystem identity still matches the file this writer created.
If another process has replaced that pathname, the replacement is retained;
this avoids deleting a displaced evidence file or symlink during error cleanup.
As with any separate identity-check/unlink operations, a hostile concurrent
replacement **after** the final identity check is outside this safeguard. This
does not make manifest creation an atomic multi-process transaction.

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


## Bounded, descriptor-bound manifest JSON capture

The verifier's manifest path is untrusted input. The earlier two checked
fingerprints were separated by a `Path.read_bytes()` call, which could open a
*different* filesystem object after an intervening path substitution. In
particular, replacing a JSON pathname with a named pipe could block that
middle read indefinitely, even though the surrounding fingerprint calls
reject non-regular files.

Manifest JSON is now read from a single `os.open` descriptor using
nonblocking/no-follow flags where supported, with regular-file checks
before reading and stable file-identity/size/mtime/ctime checks afterwards.
The read is capped at **16 MiB** of *manifest JSON* (not source artifact
bytes). It fails closed if the pathname is replaced by a FIFO or, on
no-follow platforms, a leaf symlink, or if the opened file mutates during
the read. The existing independent first, second, and post-source-scan
fingerprints still bind the content, file identity, and artifacts throughout
verification. The manifest schema and existing digests are unchanged.

This is an I/O-safety and reproducibility safeguard, not a filesystem
lock, atomic snapshot, guarantee against adversarial swap-and-restore, or
proof of input authenticity. Platforms lacking descriptor no-follow may
require stronger filesystem isolation. The size cap is intentionally
conservative and is not an experimental sampling or evaluation limit.
Synthetic tests are in
`tests/test_research_manifest_descriptor_capture.py`.

## Manifest identity through the source scan

The verifier originally checked the manifest file twice **before** scanning its
referenced artifacts. A manifest replaced or rewritten while a slow source
scan was in progress could therefore result in a successful verification of
the earlier parsed manifest even though the current manifest on disk no longer
matched those bytes. The artifact recheck cannot detect changes to the
*manifest file* itself.

The verifier now fingerprints the manifest a **third time, after all selected
artifacts and the aggregate digest pass**. It requires the exact original
SHA-256, byte count, and descriptor-bound filesystem (device, inode) identity
to match. A changed, removed, symlink-substituted, or byte-identically replaced
manifest fails closed rather than reporting a successful provenance check.
The rule applies equally to default and independently pinned verification;
existing manifest JSON and command-line interfaces are unchanged.

Synthetic regression tests deliberately rewrite, remove, and replace the
manifest during artifact verification, with and without a separately supplied
manifest pin. An unchanged manifest remains accepted. No canonical treatment
outputs, human ratings, frozen analysis, or evaluator measurements are touched.

**Limit:** This checks observable coherence over the verification window, not
an atomic snapshot or immutability after the final read. A malicious
swap-and-restore between observations can evade it. Independent custody of
the external pin and immutable input storage remain stronger provenance
requirements.

## Producer–verifier manifest-size agreement

The independent verifier caps a **serialized manifest JSON file** at 16 MiB.
Previously, a very large manifest was fully SHA-256-hashed before its size was
rejected, and the manifest producer could write a JSON file that the verifier
would never accept. Both tools now share a single 16 MiB metadata bound:

- the fingerprint CLI refuses to emit an oversized serialized JSON manifest,
  including standard output, before creating any destination or parent path;
- direct create-only writes apply the same UTF-8 **byte** count (rather than
  Python character count) before making new filesystem entries;
- the verifier checks current regular-file metadata and the cap before each
  full manifest SHA-256 pass. Its descriptor-bound read separately enforces
  the cap if the file changes or grows during reading.

This is a metadata-resource and cross-tool reproducibility control; research
**artifact file sizes themselves are not capped**. A concurrent replacement
between a stat preflight and a hash read can still cause extra I/O; these
checks are not an adversarial filesystem lock or a guarantee of atomic
multi-file capture. None of the frozen inputs or analyses is changed.

The synthetic regression suite is
`python -m pytest -q tests/test_research_manifest_size_contract.py`.

## Manifest-bound main-study snapshot capture

The verified main-study runner previously verified its two CSV artifacts with
checked file descriptors, but copied them into its isolated analysis directory
using an unrestricted second `Path.read_bytes()` call. It likewise loaded the
source code for its pinned numeric validator through an unchecked middle read.
A pathname swapped to a FIFO between verification and this second read could
block the analysis indefinitely; concurrent file growth could also allocate
unbounded bytes before a hash mismatch was discovered.

Both capture paths now use `_capture_manifest_pinned_regular_bytes`. They first
take a checked research-file fingerprint, then open a **nonblocking, no-follow**
descriptor where the platform supports those flags. The opened object must be
a regular file with the checked inode and expected size. Streaming reads are
bounded to the pinned byte length plus one detection byte. Content SHA-256,
byte count, inode, mtime and ctime are checked, followed by another
directory-traversal-safe pathname fingerprint. The isolated frozen analysis
continues to consume only the copied, validated bytes.

The source-size bound comes from the previously verified manifest; the
validator's bound comes from its checked source fingerprint. Neither adds a
new experiment-data sampling cap, reruns a treatment/evaluator, or modifies
any canonical results. This closes detectable blocking, replacement and
unbounded-middle-read behavior, **not** every concurrent swap-and-restore,
filesystem race, or attack on independent input custody. Synthetic coverage:
`tests/test_verified_main_study_snapshot_capture.py`.



## Verified main-study output custody and publication

The frozen analyzer's candidate JSON/Markdown and already-published canonical
results are *outputs*, not the manifest-pinned inputs. They previously crossed a
distinct unchecked boundary: candidate publication and provenance receipt
generation used unbounded path-based reads, while descriptor-relative canonical
reads performed an unbounded read after a separate pathname stat. Substitution
with a FIFO between those operations could hang; inode replacement or file
growth could escape the initial file-type check.

The runner now captures candidate and published bytes through a checked parent
directory descriptor and a nonblocking/no-follow regular-file descriptor.
Captures enforce a **16 MiB per-output safety limit**, match the pre-open and
post-read file identity/size/timestamps, detect growth with an extra byte, and
recheck the pathname's identity after reading. Missing canonical outputs remain
distinguishable from changed or nonregular files; no canonical output is
silently repaired or replaced.

Before the candidate passes the existing semantic output verifier, the runner
pins SHA-256 digests of the exact candidate bytes. It checks those digests again
after semantic verification and requires the identical pinned bytes at
publication. The final receipt compares the independently reread published
outputs to these pre-verification digests, **not** to a later unchecked candidate
read. Consequently, mutation during verification, between verification and
publication, or before receipt binding fails closed. Existing published results
are not overwritten to make a rerun pass.

The size bound applies to the **two manuscript-facing output files** (not
the 40 study treatment reports, canonical input CSVs, or model budgets).
These are current-filesystem coherence checks, not an atomic snapshot,
signature, historical-authenticity proof, or defense against every adversarial
swap-and-restore race. No treatment or evaluator rerun, human score, frozen
analysis rule, or canonical measurement is changed. Tests are in
`tests/test_verified_main_study_output_custody.py`.
