# Annotator distribution: whole-verification-window custody

**Scope:** Offline research-integrity safeguard. No ratings, treatment runs, or
statistical results are produced or changed.

The standalone `verify_annotator_bundle` previously captured and verified each
of its four annotator-facing files independently. A prior file could change
after it had been read, while a later manifest or guide was being validated,
and the verifier could still emit a successful receipt containing the earlier
captured bytes. In particular, a same-byte path replacement could leave the
manifest SHA-256 unchanged while invalidating the live pathname identity.

The verifier now records the bundle-root and four artifact identities before
the first content read; these signatures include device/inode, file type,
size, nanosecond modification and change times. After all existing schema,
blinding, fingerprint and ordering checks succeed, it revisits the exact
four-file inventory and root identity, independently recaptures every input
using the existing 64 MiB bounded regular-file reader, compares bytes with
the original capture, and repeats identity checks before issuing success.
Unexpected late artifacts, changes to previously read files, and directory
replacement fail closed.

This intentionally strengthens the **standalone annotator distribution
verification receipt** rather than redesigning the already completed packet,
freeze, export, or coordinator-source binding milestones. Export and
source-bound verification invoke the same standalone verifier for their
captured distributions.

The synthetic tests exercise unchanged inputs, same-byte packet replacement
after its capture, late instruction edits, template edits, late undeclared
files, and same-byte bundle root replacement. Run:

```bash
python -m pytest -q tests/test_human_eval_annotator_bundle_contract.py
python -m pytest -q tests/test_human_eval_annotator_export.py tests/test_human_eval_annotator_export_capture_bounds.py
```

**Limitations:** These checks detect observable changes during a verification
window. They do not create an atomic multi-file filesystem snapshot, detect
changes that leave no observable difference, prove historical authenticity,
validate actual annotator identities, or substitute for genuine independent
blinded ratings and agreement analysis. Existing pilot/confirmatory/exploratory
separation remains unchanged.
