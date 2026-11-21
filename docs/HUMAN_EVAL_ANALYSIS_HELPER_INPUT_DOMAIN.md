# Human-analysis helper input integrity

This implementation-only safeguard does **not** revise the frozen human rubric,
the 20,000-draw paired bootstrap, the confirmatory automated analysis, or any
observed result. Human annotations remain pending.

## Failure mode

The full human-validation pipeline checks a retained blinded freeze before
unblinding. However, direct callers of `human_eval_analysis_core.report_scores`
previously could aggregate the same annotator/report pair multiple times or
accept an out-of-rubric score such as 6. Similarly, direct callers of
`_paired_summary` could propagate NaN or infinity into bootstrap statistics,
or pass a noninteger seed. Such intermediate summaries could look plausible
without satisfying the frozen input contract.

## Contract

* `score` delegates to the existing blinded freeze's strict 1–5-or-blank
  rubric parser.
* `report_scores` checks all dimensions of every row, requires nonempty
  pseudonymous annotator and blind IDs, applies the existing canonical
  annotator-identity check, and rejects duplicate annotator/blind-ID pairs
  instead of weighting the repeated row.
* `_paired_summary` accepts only finite numeric report-level means in the
  closed interval [1, 5] **on the integer/half-integer lattice** and an integer
  bootstrap seed. For the frozen two-rater protocol, every observed report mean
  must average one or two independent integer 1–5 ratings; quarter-point values
  are impossible. No rounding or tolerance permits off-lattice inputs.
  Wholly missing dimensions retain the already-frozen behavior.
* `report_scores` rejects a third distinct canonical annotator identity across
  the direct rating set, even if those three pseudonyms appear on different
  reports. Exactly two global annotators are predeclared for treatment-level
  analysis; the separate *blinded agreement diagnostic* still supports
  reporting multi-rater data pending a prospectively declared method.
  Direct callers may analyze a partial one- or two-rater input for diagnostics,
  but must not mistake this helper for the independent full-freeze coverage gate.

These controls are defense in depth for library/direct-helper use. They
cannot authenticate human raters or replace the coordinator's complete
blinded-freeze, attestation, provenance, and full-coverage gates.

Synthetic regression tests exercise invalid input rejection and preservation
of valid mean, missingness, deterministic bootstrap, and undefined-dz behavior.
No treatment runs, canonical outputs, human ratings, or frozen measurements are
modified.
