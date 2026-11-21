# Saved exploratory joint-missingness result replay

The shared-arm human-missingness auditor prints JSON to stdout after the
independent source-human-analysis verification gate. Previously, a copied or
edited JSON report had no dedicated read-only replay check before citation or
downstream use. This optional verifier closes that **derived-output custody**
gap without inventing new ratings or changing frozen analyses.

Once authentic, source-verified human inputs exist, run the producer and save
its stdout **outside** the frozen human-analysis/freeze/packet directories:

```bash
python -m scripts.audit_human_eval_joint_missingness_bounds \
  --output-root outputs/human_eval/analysis-v1 \
  --freeze-root outputs/human_eval/frozen-v1 \
  --packet-root outputs/human_eval > joint-bounds-exploratory.json

python -m scripts.verify_human_eval_joint_missingness_artifact \
  --report joint-bounds-exploratory.json \
  --output-root outputs/human_eval/analysis-v1 \
  --freeze-root outputs/human_eval/frozen-v1 \
  --packet-root outputs/human_eval > joint-bounds-replay-receipt.json
```

The verifier first reruns the existing **independent upstream human-analysis
recomputation** and its source-byte check, *before* reading the saved
exploratory report. It recomputes the shared-arm sensitivity JSON with the
**same current implementation**, captures the saved file through the
bounded regular-file/no-symlink/hardlink/ancestor-custody reader, rejects
duplicate JSON keys and nonfinite values, and compares exact canonical
JSON values and types (including bool versus int). It tolerates whitespace
and object-key ordering differences, but rejects altered bounds, stale source
hashes, changed claims, missing fields and extra fields. The receipt binds
the captured original report SHA-256, its canonical JSON hash, and the
source-verified human-analysis SHA-256.

**Interpretation limits:** This is deterministic *same-implementation*
result replay, **not an independent mathematical re-derivation** of the
sensitivity algorithm or independent attestation of runner/storage trust.
The SHA-256 receipt describes the bytes observed at verification time; it
does not freeze the file after that observation. Consumers should pin the
repository commit implementing the auditor and verifier alongside the receipt.
Direct synthetic helper invocations do not establish evidence provenance.

The verifier never calls a model/provider, reruns a treatment/evaluator,
recreates human ratings, changes the source analysis, or publishes
confirmatory findings. The five-task pilot is diagnostic, historic automated
designated-primary inference has post-collection plan-timing, fixed-order,
and evaluator-comparability limitations, and retrospective missingness
bounds remain exploratory. Actual human validation still requires original
report/trace authentication, verified blinded distribution, eligible
independent annotators, real scores, agreement, and reconciliation.

As of 16 November 2026, original historical treatment run
`34620917346` and evaluator-recovery run `34783525480` exposed **zero
accessible Actions artifacts** each. The verifier is therefore tested only
with synthetic fixtures; there is no authentic saved human-sensitivity
report to certify yet.
