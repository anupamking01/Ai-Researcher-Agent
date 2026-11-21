# Noncanonical live-app smoke dispatch and evidence isolation

The `.github/workflows/live-app-smoke.yml` workflow performs paid,
provider-backed FastAPI/WebSocket diagnostics only when a caller explicitly
supplies `smoke_ack=NONCANONICAL_LIVE_SMOKE`. Its first step must reject
an incorrect acknowledgement before checkout, provider credentials, application
startup, or a paid request. Ordinary push/PR regression CI stays offline.

## Preserve authorized in-flight work

GitHub evaluates workflow-level concurrency **before** the first-step
acknowledgement. With `cancel-in-progress: true`, merely dispatching a
second run could cancel an already-running, separately approved live smoke,
even when the new dispatch's acknowledgement was incorrect. The workflow
now retains a per-ref concurrency group with `cancel-in-progress: false`,
so a new dispatch does not terminate an in-flight run. It also retains
read-only repository permissions and does not call the Actions cancellation
API. This protects partial diagnostic evidence and reduces avoidable paid
provider work. **GitHub may still replace pending runs** in the same
concurrency group; the change does not preserve every queued request,
guarantee successful completion, or prevent manual cancellation elsewhere.

Future evidence bundles use the
`noncanonical-diagnostic-live-smoke-<run_id>` artifact name, distinct
from historical treatment, evaluator-recovery, and automated-analysis
artifacts. This naming is prospective labelling, not proof of original
report/trace custody or source authentication. Artifacts retain the
workflow's existing 14-day GitHub retention setting.

## Offline validation

```sh
python -m pytest -q tests/test_live_app_smoke_dispatch_gate.py
```

These synthetic regression tests verify manual-only dispatch, acknowledgement
failure semantics, no in-flight cancellation, read-only credentials, absence
of cancellation steps, and noncanonical archive identity without starting
provider-backed work. GitHub manual dispatch generally requires the workflow
file to be on the default branch; while this change is only on the research
branch, it may not be dispatchable through the Actions UI.

This is **execution and provenance safety**, not a rerun of the diagnostic
five-task pilot, prospective confirmation of September 2026 automated results,
a change to exploratory findings, recovery of missing original 40
reports/traces, or a completed human-evaluation study.
