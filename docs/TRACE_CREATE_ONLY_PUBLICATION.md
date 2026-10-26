# Create-only research trace publication

## Risk and scope

The research agent records a JSON trace for each attempted treatment run,
including failures and timeouts. Previously `save_run_trace` used an
unconditional `Path.write_text` to publish `<trace_root>/<variant>/<run>.json`.
A duplicate run identifier could silently replace earlier evidence, while an
unvalidated path component could escape the intended variant directory. A
write interruption could also leave a partially written canonical JSON file.
These are prospective trace-custody failures, not evidence that any frozen
historical trace was altered.

## Implementation contract

`logic.experiment.save_run_trace` now:

1. Requires variant and run identifiers to be portable ASCII components
   matching `[A-Za-z0-9][A-Za-z0-9_-]{0,127}`, rejecting path traversal and
   ambiguous filenames before creating directories.
2. Serializes the complete JSON payload first, rejecting unserializable and
   non-finite values before touching the destination.
3. Rejects symlinked `trace_root` and variant directories at its explicit
   checks. Its configured ancestor path is still a caller-controlled location.
4. Opens the trace root and variant directory with `O_DIRECTORY | O_NOFOLLOW`
   and retains directory descriptors through publication. Creates, links and
   removes staging entries relative to those descriptors, even when another
   process renames or replaces a visible directory name mid-write.
5. Writes and fsyncs the staged file, then uses a descriptor-relative hard
   link for create-only publication. Fsyncs the variant directory after link
   creation and again after staging cleanup for best-effort entry durability.
6. Rejects observable root/variant identity changes before reporting the
   canonical output path. A replaced directory may retain the new trace under
   its original renamed location; this raises an error for investigation
   rather than rewriting or silently claiming a successful canonical write.

Successful outputs retain the existing schema version 2, JSON formatting,
folder layout and return path. The check is **create-only**, not a backup
policy or automatic retry. A legitimate new attempt needs a distinct run ID,
and an existing trace must be investigated rather than deleted to make room
for a more favorable outcome.

The mechanism requires a filesystem supporting same-directory hard links.
It does not establish origin authenticity, guarantee cross-filesystem or
hardware crash durability, defend against every privileged concurrent
filesystem mutation (including swaps immediately after return),
authenticate model responses, or retroactively prove historical trace custody. Descriptor-relative writes
require POSIX `dir_fd`, hard-link, and directory-`fsync` support; configured
ancestor directories remain caller-controlled. A post-publication `fsync`
failure can leave an existing canonical trace that must be investigated, not
automatically overwritten.

## Validation and scientific boundaries

`tests/test_trace_create_only_publication.py` tests normal publication,
duplicate collisions, concurrent writers, path traversal, direct directory
symlinks, output symlink preexistence, non-finite/unserializable payloads,
and staging cleanup after publication failure using synthetic local inputs.
Ordinary offline CI runs the full regression suite; no provider calls are
required for these tests.

This safeguard does not modify or rerun frozen treatment reports, the common
post-hoc evaluator, task-level paired analysis, exploratory audits or pending
human evaluation. Diagnostic pilot evidence, frozen automated confirmatory
analysis, post-hoc exploratory analysis and future independent blinded human
ratings remain separate.

## Additional adversarial verification (27 October 2026)

`tests/test_trace_directory_descriptor_custody.py` verifies descriptor-relative
source/destination names, directory fsync calls, and synthetic root/variant
replacement between staging and hard-link publication. In the replacement
cases, verification fails closed and no file is redirected into the attacker
replacement directory. This is an observable-race regression, not a proof of
immunity to all concurrent filesystem attacks.
