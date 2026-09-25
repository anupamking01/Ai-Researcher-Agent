# Human-evaluation analysis output verification

This implementation note covers the publication boundary for
`scripts/analyze_human_eval.py`. It does not change the frozen human-evaluation
rubric, assignment plan, treatment-level estimands, bootstrap settings, or the
automated confirmatory analysis.

## Why this gate exists

The human-validation analysis has two manuscript-facing representations:
`analysis.json` is canonical machine-readable output and `analysis.md` is a
deterministic view of that JSON. Without an explicit publication check, a manual
edit, partial copy, or later source-code drift could make a result bundle look
valid while no longer representing the analysis that produced it.

The analysis command now writes a third file, `analysis_manifest.json`, last.
That manifest SHA-256-binds:

- `analysis.json`;
- `analysis.md`;
- `scripts/human_eval_analysis_core.py`;
- `scripts/analyze_human_eval.py`.

The command then verifies the persisted bundle before printing its success
message.

## Independent verification

From the repository revision that produced an analysis bundle, run:

```bash
python -m scripts.verify_human_eval_analysis_outputs \
  --output-root outputs/human_eval/analysis-v1
```

Verification fails closed when:

- canonical JSON or Markdown is missing, malformed, or a symbolic link;
- Markdown is not byte-for-byte the deterministic rendering of canonical JSON;
- either output no longer matches its recorded byte count or SHA-256;
- the current analysis core or renderer source bytes do not match the generating
  implementation recorded in the manifest;
- result identity fields attempt to relabel human validation as automated
  confirmatory analysis, claim generated human ratings, claim treatment reruns,
  or add undeclared human-validation hypothesis tests.

A successful receipt is a publication-integrity check, not a new scientific
result.

## Archive and checkout rule

Keep the analysis bundle together with the exact repository commit that produced
it. Because implementation hashes are checked, verifying an old bundle from a
newer checkout may intentionally fail after analysis code changes. Check out the
recorded generating commit and rerun the verifier instead of rewriting the old
manifest.

`analysis_manifest.json` is written last, so a missing manifest means the bundle
must not be treated as successfully published. The output directory remains
create-only; interrupted or failed attempts are preserved for inspection and a
new versioned output path should be used for a retry.

## Limits

This gate detects output/renderer drift and binds the implementation source. It
does not prove that annotators were independent humans, replace the earlier
packet/freeze verification gates, or make multiple filesystem writes an atomic
transaction. The upstream human-analysis code still verifies and snapshots the
blinded and coordinator artifacts before treatment-level analysis. Real blinded
ratings remain required before any human-quality finding can be reported.
