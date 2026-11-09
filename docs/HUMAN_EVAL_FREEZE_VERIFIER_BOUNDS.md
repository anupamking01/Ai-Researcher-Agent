# Bounded pre-unblinding human-freeze inventory

The standalone verifier `scripts/verify_human_eval_freeze.py` recursively
inventories the supplied freeze tree **before** reading the manifest or
retained ratings. A damaged or untrusted archive could previously induce an
unbounded directory listing or arbitrarily deep traversal at this initial gate.

The inventory now fails closed when it observes more than **256** total child
entries, more than **64 MiB** in aggregate regular-file sizes (as reported by
`stat`), or nesting deeper than **8** levels below the freeze root. These are
resource-safety limits, not acceptance criteria for ratings or changes to
the frozen protocol. Enumeration stops immediately after the first excess
name; the verifier does not open or read these files to enforce the limits.
Within the bounds, existing path and directory-generation stability checks,
manifest verification, and independent blinded agreement replay are unchanged.

## External hardlink aliases

The standalone inventory also rejects any regular freeze file with a link
count other than **one**, including aliases whose second pathname is outside
the archived freeze tree. A hardlink shares the same inode: a process can edit
frozen ratings, attestations, or agreement bytes through that unlisted path
without editing the archive's visible filenames. File link counts are included
in both the initial and final inventory identities so changes observed during
verification fail closed. Filesystem links to files outside the freeze root
are not recovered or followed. Ordinary single-link files remain valid.

This strengthens **local file-custody verification only**. It is not a file lock,
not an independently retained hash of original treatment reports or traces,
and cannot prove the absence of short-lived modifications between observations.
The separate human-analysis snapshot hardlink guard remains independently
required for later processing; this verifier must not be treated as a substitute.

The bounds match the human-analysis snapshot's established maximum
entry count, aggregate bytes, and tree depth. Verifiers should handle an
over-limit archive by investigating its provenance, not by selectively
removing ratings or increasing limits to obtain favorable results.

Reproduce the synthetic tests offline:

```bash
python -m pytest -q tests/test_human_eval_freeze_inventory_bounds.py tests/test_human_eval_freeze_inventory_hardlinks.py
```

No original treatment reports or traces are recovered by this change. The
missing source-custody archive still blocks source-verified blinded human
evaluation; no real human ratings, agreement statistics, or automated–human
reconciliation are established by passing the inventory check.
