# Replaying the complete sixteen-shard offline CI evidence set

The ordinary offline test workflow partitions every discovered test module into **sixteen** deterministic, firewalled pytest shards. Each job separately runs an early dependency-free unittest gate. One passing shard, a successful fast lane, or a green pytest transcript from a subsequently cancelled job does **not** constitute a successful complete suite.

For one *completed successful* GitHub Actions run and attempt, obtain both kinds of retained artifacts for **every** shard, N=0...15:

- `vera-offline-tests-shard-N-<run-id>-<attempt>`: the exact test log, receipt, and module inventory. Extract as `/trusted-download/pytest/shard-N/` with filenames `vera-offline-tests.log`, `vera-offline-test-receipt.json`, and `vera-offline-test-modules.txt`.
- `vera-stdlib-evaluation-shard-N-<run-id>-<attempt>`: the pre-install diagnostic log and receipt. Extract as `/trusted-download/early/shard-N/` with filenames `vera-stdlib-evaluation.log` and `vera-stdlib-evaluation-receipt.json`.

Use a clean checkout of the **exact tested Git SHA**. For pull-request runs, GitHub Actions may test an integration merge SHA instead of the PR branch head; select `--event pull_request` and use the actual tested checkout SHA. Supply run identity from the independent GitHub run metadata, *never* from a downloaded receipt.

```bash
python -m scripts.verify_full_ci_shard_set \
  --evidence-root /trusted-download/pytest \
  --early-evidence-root /trusted-download/early \
  --checkout-sha <tested-40-hex-sha> \
  --run-id <run-id> --run-attempt <attempt> --event push
```

The verifier requires all sixteen three-file pytest shard bundles and all sixteen two-file pre-install bundles for the same SHA, event, run and attempt. It independently recomputes the retained full-test success receipts and module selections, verifies that their union covers each source test module exactly once, and replays every retained pre-install diagnostic transcript and receipt against the tracked early-gate source bytes. Any missing/extra shard, mixed run/attempt, altered receipt/log, unexpected bundle entry, or symlinked evidence path fails closed. Directory inventory scans and evidence reads are bounded, with descriptor-relative no-follow ancestor custody checks. The GitHub replay job performs the same check on the downloaded artifacts and retains the resulting combined receipt.

The `--early-evidence-root` argument is optional for **legacy pytest-only** review; its output explicitly says `preinstall_diagnostics: not_replayed`, and must not be presented as the complete combined offline evidence replay.

**Scope and limitations:** These are source-bound *local consistency* checks, not independent attestation of runner honesty, network isolation, actual test execution, artifact-service custody or experimental provenance. A cancelled workflow remains cancelled even if its pytest transcript says `passed`; all sixteen job conclusions and the aggregate replay must succeed. Neither replay reruns treatments/evaluators nor fabricates human data. The five-task pilot remains diagnostic, designated-primary automated analysis is post-collection with fixed-order and evaluator comparability qualifications, and retrospective sensitivities remain exploratory. The original treatment reports/traces, human distribution, actual blinded ratings, agreement and automated-human reconciliation remain independently unresolved.
