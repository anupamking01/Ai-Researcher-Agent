# Diagnostic-pilot summarizer: bounded source capture

This change covers the **standalone offline diagnostic-pilot summarizer**, not
the original experimental runner or the separate main-study analysis.
`scripts/summarize_pilot.py` previously validated the root/arm inventory
but traversed the directories without an entry-count bound, re-globbed each
arm after inventory, and parsed source JSON through a pathname-based,
unbounded `read_text()`. A large or concurrently replaced local artifact
could consume unbounded parsing memory or invalidate the selected source
roster after the preliminary check.

The frozen pilot design has **five tasks in each of D6, P6 and P6V** (15
cells). The summarizer now examines at most three root entries and five
trace entries per arm; an overflow or unexpected entry fails before any
trace is parsed. It reuses that exact sorted inventory rather than a second
`glob()` selection. Each selected source must be a single-link regular file
of at most **8 MiB**. The loader opens the file with no-follow/nonblocking
flags where supported, reads from a held descriptor with a hard bound,
checks inode/size/time/link metadata against the descriptor and final
pathname, and then passes the captured UTF-8 bytes to the same strict
duplicate-key/nonfinite-rejecting JSON parser used by postrun validation.
Missing arms and incomplete pilot workspaces retain their earlier diagnostic
behavior; no missing records are manufactured.

## Synthetic offline validation

```sh
python -m pytest -q tests/test_pilot_trace_capture_bounds.py
python -m pytest -q tests/test_pilot_trace_inventory_identity.py tests/test_pilot_summarizer_source_integrity.py
```

The regressions cover all 15 legitimate cells, partial inputs, excessive
arm/trace entries, oversized sources without parsing, hardlinks, in-place
growth, pathname replacement, and strict JSON retention. No live treatment,
evaluator, external request, frozen analysis, or human rating is rerun.

## Scope and limitations

These checks prevent ordinary unbounded enumeration, oversized-file parsing,
and observed source mutation while reading on a local filesystem; they do
**not** provide an OS-atomic multi-directory snapshot, independent archival
custody, protection against an adversary who can restore all metadata, or
provider authentication. File-size limits are a fail-closed operational policy,
not a retrospective claim that every historical source was within the cap.
The five-task pilot remains diagnostic. Frozen automated main-study results
still carry temporal-order, evaluator-recovery and analysis-plan-timing
limitations. Retrospective sensitivity work is exploratory. Original 40
main-study reports/traces and genuine blinded human annotations remain
unavailable/unverified for the pending human-validation gate.
