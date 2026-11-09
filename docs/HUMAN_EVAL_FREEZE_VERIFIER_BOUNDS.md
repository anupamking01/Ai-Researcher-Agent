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

The bounds match the human-analysis snapshot's established maximum
entry count, aggregate bytes, and tree depth. Verifiers should handle an
over-limit archive by investigating its provenance, not by selectively
removing ratings or increasing limits to obtain favorable results.

Reproduce the synthetic tests offline:

```bash
python -m pytest -q tests/test_human_eval_freeze_inventory_bounds.py
```

No original treatment reports or traces are recovered by this change. The
missing source-custody archive still blocks source-verified blinded human
evaluation; no real human ratings, agreement statistics, or automated–human
reconciliation are established by passing the inventory check.
