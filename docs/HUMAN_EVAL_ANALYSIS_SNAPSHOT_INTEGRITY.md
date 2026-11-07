# Human-evaluation analysis snapshot integrity

`scripts/human_eval_analysis_core.py` now binds verification and analysis to the
same captured bytes.

Before any treatment identity is opened, the analyzer snapshots the archived raw
rating inputs, blinded packet, frozen ratings, agreement artifact, freeze
manifest, protocol, assignment plan, treatment-blind annotator guide, and
human-analysis plan into private temporary scratch space. Evidence-bound freezes
also carry the complete retained `submission_preflights/` tree into that same
snapshot. This preserves every neutralized intake receipt and treatment-blind
distribution bundle, including undeclared entries that the independent verifier
must reject, rather than laundering them away through selective copying.
The analyzer holds each source directory by descriptor, compares entry
inventories before and after copying, and rechecks each directory and file
binding. It also binds the freeze-root inventory across the optional-archive
decision. Replacements, late additions, symlinks, and other non-regular entries
therefore fail before unblinding. The pre-unblinding freeze verifier runs
against those snapshots and independently replays the retained receipt chain.
If that gate passes and the frozen two-rater requirement is satisfied, the
analyzer then reads the coordinator-only mapping artifacts.

The captured human-analysis plan must also match the literal SHA-256 anchor in
the analysis implementation before any coordinator mapping is read. Merely
fingerprinting an arbitrary supplied plan in the eventual result is not enough:
plan drift or substitution now stops the analysis while ratings remain blinded.
Updating the frozen plan therefore requires an explicit reviewed source change,
not only a different `--analysis-plan` file.

The packet manifest, blinding key, ratings template, and frozen task manifest are
captured only after the blinded gate. The packet verifier runs against that
second snapshot, using the already captured blinded packet. All report-level
aggregation, treatment mapping, agreement inclusion, and provenance hashes are
computed from the verified snapshots rather than reopening the live source paths.
The canonical analysis provenance records the exact captured protocol,
assignment plan, and annotator guide under stable repository-logical paths, so a
published result remains directly attributable to the instructions that governed
collection even when the freeze archive is stored separately.

This closes a time-of-check/time-of-use gap where an editor save after a verifier
returned could previously change the scores, task universe, treatment mapping,
agreement payload, or provenance that the analysis actually consumed.

The scratch copies are ephemeral and are deleted when analysis exits. They are
not a replacement for retaining the original archived ratings, packet bundle,
freeze bundle, or Git-tracked analysis plan. Source trace and report provenance
continues to be checked by the packet verifier against the repository; treatment
and evaluator runs are not regenerated.


## Resource-bounded snapshot capture

The human-analysis snapshotter rejects an individual input larger than
**16 MiB**, before copying it into scratch space. This applies consistently to
direct captures (including submitted ratings, the blinded packet, governing
documents, the frozen analysis plan, and the coordinator mapping/task files)
and to every file within the retained freeze-artifact tree, including nested
submission preflight receipts. The limit is a defensive input-snapshot rule,
not a requirement on research treatment outputs or a change to the frozen
statistical analysis plan.

Reads are limited to the size observed on the opened regular-file descriptor.
An extra one-byte probe detects growth beyond that observed size; premature
EOF fails closed. Existing inode/metadata/path and recursive directory-inventory
checks still run after capture. Consequently an unexpectedly oversized,
truncated, or growing source cannot be silently copied as verified evidence
or consume unbounded snapshot memory. These checks do not provide an atomic
filesystem snapshot or authenticate historical source origins; hostile
same-size in-place edits remain subject to observable metadata checks.

This hardening uses synthetic-only regression fixtures. No ratings, paired
effects, agreement statistics, treatment runs, or existing published results
are generated or changed.
