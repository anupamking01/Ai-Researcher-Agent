# Prospective VERA run artifact continuity (offline, recorded evidence only)

**Scope: a separately designed future counterbalanced replication, never the historical September 2026 pilot or fixed-order main study.** This optional offline verification layer does not execute agents, call evaluators, compute scientific effects, score reports, create human ratings, or recover lost historical evidence.

## Gap and interpretation

The existing schedule verifier reconstructs the ten-task treatment order from a prospective manifest. The chronology verifier checks that a **self-reported** forty-cell execution ledger follows this order, including failed, timed-out, cancelled, and unattempted cells. Neither verifies that the recorded run identifiers have corresponding local traces and reports. A coherent execution log could pass even when its purported output files are absent, replaced, or assigned to different run IDs.

The new read-only scripts/verify_prospective_run_artifacts.py gate independently recomputes both prior checks, then verifies candidate **local artifact bytes** against an exact forty-cell inventory. Each attempted run must have a nonempty UTF-8 JSON trace; every completed run must also have a nonempty report. Failed, cancelled and timed-out runs must retain a trace but may have no report. Unattempted suffix cells must declare null for run ID, trace and report. Nothing is silently removed from the denominator.

A pass establishes *internal agreement* between the supplied prospective manifest, plan, recorded chronology, inventory fingerprints, trace identity, **exact task-question fingerprint**, **self-reported intervention controls**, UTC interval fields, and local report bytes. A trace with a valid run ID but a fingerprint for a different research question now fails, even when the candidate inventory has been rehashed. This guards against a ledger with rewritten start/end times being paired with retained traces that still record the original interval. These clock claims remain self-reported; equal strings do not prove provider execution or trustworthy real-world timing. It **does not** prove that the trace reflects an actual model call, the provider supplied its contents, sources were fetched, a report is correct, or an experiment or human validation was independently authenticated. A coordinator can rewrite all candidate files consistently. Independently retained pre-run/post-run digests are needed for stronger custody, and additional provider-bound evidence is needed for independent execution authentication. Do not use a passing receipt to promote pilot observations to confirmatory findings or to publish claims of completed replication.

## Evidence index schema v1

Keep the exact original prospective task manifest, its originally frozen schedule receipt, unchanged execution ledger, candidate artifact directory, and index JSON. The index is a UTF-8 JSON object with exactly schema_version (integer 1), classification (the exact literal shown below), task_set_id, execution_log_sha256 (SHA-256 of exact execution-ledger bytes), and cells (exactly forty entries in execution order).

Illustrative first cell only (the complete index **must** include all forty cells):

    {
      "schema_version": 1,
      "classification": "prospective_replication_local_artifact_continuity_only",
      "task_set_id": "new-independent-2027",
      "execution_log_sha256": "<sha256 of original execution log bytes>",
      "cells": [
        {
          "task_id": "<first task ID from the frozen plan>",
          "variant": "<first assigned arm>",
          "run_id": "run-00",
          "status": "completed",
          "trace": {
            "path": "traces/run-00.json",
            "size_bytes": 248,
            "sha256": "<sha256 of trace bytes>"
          },
          "report": {
            "path": "reports/run-00.md",
            "size_bytes": 4096,
            "sha256": "<sha256 of report bytes>"
          }
        }
      ]
    }

Each inventory row has exactly task_id, variant, run_id, status, trace, report. The first four fields must match the corresponding independently verified chronology row **with identical JSON types**; for unattempted cells the run ID, trace and report must all be JSON null. File fingerprints use exactly path, size_bytes (positive JSON integer), and lowercase SHA-256. Paths are safe relative paths beneath the nominated artifact root with no traversal, aliases, symbolic links or hardlinks; distinct artifacts cannot reuse a path or underlying inode. The verifier holds one descriptor for the root directory across all reads and fails if the root directory metadata or the pathname's underlying inode changes before completion. This prevents a verifier run from silently accepting an interleaved collection of individually hash-valid artifacts from a replaced root directory. It is not an atomic snapshot of every nested directory and does not independently authenticate source files. Each file is limited to 2 MiB; all referenced artifacts together are limited to 16 MiB. The index itself is limited to 256 KiB.

A prospective trace JSON object must include at least these exact, correctly typed event-identifying keys, matching the original ledger: task_id, variant, run_id, status, started_at_utc and finished_at_utc. Both UTC timestamp fields must be strings exactly equal to the verified execution ledger's corresponding event timestamps, including their original UTC representation. An attempted trace lacking either clock field, or giving conflicting clocks even with otherwise matching run identity and valid artifact hashes, fails closed. It must also contain **task_question_sha256**, the lowercase SHA-256 of the exact UTF-8 bytes of its task's original question string from the frozen prospective manifest, plus report_sha256, whose value is the lowercase SHA-256 of the corresponding indexed report or JSON null when no report is indexed. Do not normalize or paraphrase the question before hashing it. Missing, non-string, or mismatched question fingerprints fail even when the trace and inventory are consistently rehashed. This is a **self-reported source-question binding**: it cannot prove which prompt was actually sent to any model or independently authenticate an execution. Each attempted trace must also include an exact **treatment_controls** JSON object with exactly three factors: planning_mode (string), source_budget (integer, not boolean/float), and verification_mode (string). Their values are checked against the frozen prospective intervention contract in scripts/plan_counterbalanced_replication.py:

| Arm | planning_mode | source_budget | verification_mode |
| --- | --- | ---: | --- |
| D3 | direct | 3 | none |
| D6 | direct | 6 | none |
| P6 | planner | 6 | none |
| P6V | planner | 6 | verify |

An otherwise correctly indexed P6V trace claiming verification_mode=none, or a P6 trace claiming direct planning, fails even when its source bytes and index hash have been rewritten consistently. Regression tests cross-check the frozen values with logic.experiment.ExperimentConfig.from_variant. These are **self-reported control settings only**: the checker cannot prove which settings actually ran. It does not attest other parameters such as model versions, prompt revisions, timeouts, concurrency, or search multipliers, which must be retained separately before making any intervention-fidelity claim. Historical trace formats are unchanged.

Other trace fields may hold legitimate provenance or failure details and are not used for outcome scoring. Duplicate JSON keys, malformed UTF-8 and nonstandard numeric constants are rejected. This is a **new prospective trace envelope contract**; historical VERA traces must not be silently reclassified to satisfy it.

For a recorded failure, timeout or cancellation, require the trace even when no report exists. A failed attempt that genuinely produced no trace cannot pass this stronger artifact-custody check: preserve the incomplete ledger and explicitly report the provenance gap, rather than fabricate a trace. For an unattempted cell, never create a fake run ID or placeholder trace. A full forty-cell confirmatory dataset cannot be inferred from a partial or failed ledger.

## Read-only verification

    python -m scripts.verify_prospective_run_artifacts \
      --task-manifest /path/to/frozen-future-tasks.json \
      --plan-file /path/to/original-future-plan.json \
      --execution-log /path/to/original-execution-log.json \
      --evidence-index /path/to/recorded-local-index.json \
      --artifact-root /path/to/candidate-original-traces-and-reports \
      --expected-task-manifest-sha256 <independently-retained-prerun-value> \
      --expected-plan-file-sha256 <independently-retained-prerun-value> \
      --expected-execution-log-sha256 <independently-retained-postrun-value> \
      --expected-evidence-index-sha256 <independently-retained-postrun-value>

All four expected SHA-256 options are optional. The verifier reports separately which were provided and matched. Self-computed values from the candidate files must **not** be called independently preserved. Successful checks print only a compact status/digest/count receipt; no report text, token content, source URLs, annotator identities or experimental measurements are printed or written. An invalid candidate fails closed. There are no model/network calls, and the verifier never mutates the source files.

For stronger external trust, independently preserve the prospective manifest and plan hashes **before** execution and execution-log and index hashes **after** each finalized capture. These timestamps and custodian identities must be established outside this script. Verify provider-bound run receipts, original retrieval provenance and model/experiment traces separately before treating any candidate artifacts as authenticated science.

## Research gate separation

The **diagnostic pilot** remains diagnostic, the original **frozen automated confirmatory** analysis remains tied to its historical outputs and original fixed execution order, and any **exploratory** sensitivity or cost-quality investigations remain exploratory. The new prospective plan and this artifact auditor are **methodology only**, with no future measurements generated. Authentic **human validation** is still blocked until the original treatment traces/reports are independently recovered and two eligible blinded annotators are selected.

As of the audit performed for this change, the historical treatment and evaluator-recovery workflows continue to expose zero downloadable GitHub Actions artifacts, although the separately preserved canonical automated-analysis ZIP remains available. This prospective continuity check does **not** repair that source-custody break or retroactively remove the 2026 time-order confound.
