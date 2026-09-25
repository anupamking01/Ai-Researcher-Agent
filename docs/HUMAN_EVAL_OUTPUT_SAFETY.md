# Human-evaluation freeze destination safety

This implementation note concerns `scripts/freeze_human_eval_ratings.py` only.
It does not change the frozen rubric, assignment coverage, agreement statistics,
or automated study results.

## Create-only destination

Pass a **nonexistent** path to `--output-root`, such as
`outputs/human_eval/frozen-v2`. Do not create that final directory in advance.
Existing parent directories are allowed; missing parents are created as needed.
The destination itself must not already be a directory, file, or symbolic link,
including an empty directory or a dangling link.

After input validation and agreement calculation, the freezer exclusively
creates the destination directory before writing any output. If another freezer
has already created it, this invocation fails without modifying that directory.
The initial existence check is only an early diagnostic; exclusive directory
creation is the decisive check against overlapping invocations.

This prevents two cooperating freezer processes from both accepting the same
output path and replacing each other's ratings or manifest. Existing directories
are never adopted, merged into, emptied, or deleted by this utility.

## Interrupted attempts

Input-validation failures occur before reserving the destination. An I/O error
or interruption after reservation may leave an empty or partially written
directory. It is deliberately preserved for inspection, not automatically
removed or reused by a later invocation. Preserve the original input files and
use a new versioned output path for another attempt.

Directory existence is **not** proof of a successful freeze. The manifest is
written last; a missing, malformed, or hash-inconsistent manifest must not be
accepted for unblinding. This change does not make the three output writes one
atomic transaction or guarantee recovery after power loss. It does not lock
input files or defend against another program deleting or replacing a reserved
directory while the freezer is running. Retain controlled filesystem access and
follow `docs/HUMAN_EVAL_INPUT_PROVENANCE.md` for input-retention requirements.

## Regression checks

`tests/test_human_eval_freeze_destination.py` uses synthetic data and deterministic
interleavings to check completed competing freezes, reservations made during
validation, overlapping attempts before the first output write, write failures,
existing paths and links, and normal fresh-directory behavior. No collected
human scores are used or generated.
