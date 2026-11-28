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

After input validation and agreement calculation, the freezer creates a sibling
staging directory, writes the complete candidate there, and independently
verifies it from its retained inputs. The requested destination remains absent
throughout those steps. Linux `renameat2(RENAME_NOREPLACE)` then atomically
publishes the verified directory. If another freezer or process has already
created the destination, publication fails without modifying that path.

This prevents two cooperating freezer processes from both accepting the same
output path and replacing each other's ratings or manifest. Existing directories
are never adopted, merged into, emptied, or deleted by this utility.

## Atomic visibility and interrupted attempts

Input-validation failures occur before reserving the destination. An I/O error
or interruption while building a candidate can leave a hidden sibling directory
named like `.frozen-v1.staging-*`, but it does not expose that partial candidate
at the requested final path. Failed staging directories are deliberately
preserved for inspection rather than automatically deleted by pathname. Preserve
the original input files, inspect or archive the failed candidate, and use a new
versioned output path for another attempt.

Directory existence is **not** proof of a successful freeze. The manifest is
written last and the staged candidate must pass `verify_human_eval_freeze`
before publication. The directory rename makes visibility atomic, but it does
not provide durability guarantees across power loss or lock the external input
files. The staging inode is checked against an open directory descriptor before
verification, before publication, and after publication; controlled filesystem
access is still required for nested contents. Follow
`docs/HUMAN_EVAL_INPUT_PROVENANCE.md` for input-retention requirements.

## Regression checks

`tests/test_human_eval_freeze_destination.py` uses synthetic data and deterministic
interleavings to check completed competing freezes, contenders created during
validation or at publication, staged-verifier ordering, write failures, existing
paths and links, and normal fresh-directory behavior. No collected human scores
are used or generated.
