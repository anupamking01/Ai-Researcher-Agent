# Diagnostic-pilot CSV: fail-closed spreadsheet formula safety

The diagnostic-pilot per-run CSV is a human-readable research export. Python's
CSV quoting protects parsing but **does not prevent** spreadsheet software from
interpreting text cells beginning with `=`, `+`, `-`, or `@` as formulas.
The selected trace supplies free-text fields (run/task IDs, model names, and
usage/verification statuses); even a CSV exactly matching those traces could
carry dangerous spreadsheet instructions.

The standalone `scripts/summarize_pilot.py` now refuses to render
formula-looking **string** cells. It recognizes a dangerous leading marker
even after leading whitespace, Unicode separators, control characters, or
format characters such as a byte-order mark and zero-width space. **It never
escapes, strips, or changes source measurements or identifiers**: if an input
cannot be safely represented as an ordinary spreadsheet cell, publication
fails before either canonical JSON or CSV path is created.

The independent schema-v5 source-to-CSV auditor in
`scripts/audit_pilot_runs_csv.py` separately rejects formula-like text in
record identifiers and the exported status/model columns. That prevents a
matching malicious trace plus CSV from passing solely by source-to-export
equality. The independent check does not import the producer and retains the
exact-value provenance contract. The auditor also checks **every parsed
exported CSV cell**, including numeric cells, for a formula-like prefix *before*
floating-point equivalence: `+1.25` and `1.25` may compare equal as Python
numbers, but a spreadsheet may evaluate the first as a formula. A safe trace
is not enough when the subsequent CSV export has been modified. Previous schema versions are not retroactively
claimed to have this CSV reconciliation gate.

Synthetic offline reproduction:

```sh
python -m pytest -q tests/test_pilot_csv_formula_safety.py
python -m pytest -q
```

This is local research-export hygiene, **not** sanitization of all downstream
spreadsheet programs or proof that upstream traces are genuine. Spreadsheet
interpretation varies by application; researchers should use an importer that
treats these columns as literal text rather than executing formulas. No pilot
or main-study experiments, evaluators, frozen analyses, or human ratings are
rerun. The pilot remains diagnostic; frozen automated results are qualified
by their post-collection plan timing, fixed order, and evaluator-policy
limitations; retrospective sensitivity remains exploratory; independent
original 40-run trace custody and blinded human validation remain pending.
