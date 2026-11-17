# Local diagnostic bundle verification: bound five-file custody

The optional `scripts.verify_main_study_diagnostic` checks **local, noncanonical**
diagnostic outputs, not September's archived automated measurements. The prior
reader rejected symlinked leaf files and checked each file during its read,
but could follow a symlinked ancestor, accept a directory substituted between
reads, or accept an identical-byte replacement of a previously read member.

The verifier now holds no-follow descriptors for the entire input directory
chain, pins the starting identity/write generation of **all five** permitted
bundle members, opens each file relative to the retained directory, then
rechecks every member, directory component, and the exact file inventory
after validation (including optional offline inference recomputation).
Explicit `..` traversal and redirected ancestors fail closed. Source-code
fingerprints and the unchanged historical analyzer remain checked separately.

Run the synthetic offline regressions with:

```bash
python -m pytest -q tests/test_main_study_diagnostic_input_receipt.py
```

The new cases exercise symlinked ancestors, parent traversal, directory
substitution after manifest capture, and identical-byte replacement of an
already read CSV after later files were captured. There are no network,
model, evaluator, treatment or human-rating calls.

These safeguards establish *observed local pathname and byte continuity*,
not an atomic filesystem snapshot; transient changes fully reversed between
observations remain outside this guarantee. Neither a locally coherent
manifest nor these checks independently authenticate unavailable original
September reports/traces, their historical custody, or provider actions.
The five-task pilot remains diagnostic. Frozen automated findings remain
qualified by post-collection analysis-plan chronology, fixed treatment
order and evaluator comparability. Retrospective sensitivities are exploratory,
not prospective confirmatory findings. Human validation is still blocked
pending source-authenticated handoff and genuine independent annotators.
