# Original versus recovered common-evaluator source-policy comparison

**Status: retrospective source-only evaluation-validity audit; not a new measurement.**

The first historical workflow ran the treatment matrix and attempted the common post-hoc support evaluator. The September 13 evaluator-only recovery resumed using 37 retained evaluator records and required the three missing identities P6V/main-02, P6V/main-08, P6V/main-10. These are *requirements encoded in the historical recovery workflow*, not independently authenticated original archive contents.

The evaluator-recovery source was modified after the original treatment commit. It is therefore important not to assert that the two executable scripts were byte-identical just because both were described as a "common evaluator."

Run in a full-history checkout without credentials or any model/network calls:

    python -m scripts.audit_historical_common_evaluator_policy

The verifier pins Git ancestry and the exact 22 historical Git blobs for the original/recovery evaluator scripts, their launch workflows, prompt generator and normalizer. It parses historical evaluator source as Python AST **without importing or running it**. It checks shared calls to the same prompt generator, the same model-selection expression, the same 120-second request timeout and the same score normalizer, along with the workflow-declared model gpt-5.6-terra, temperature 1 and 12-claim cap. The historical prompt-generator and normalizer blobs are byte-identical across these two revisions.

It additionally checks the **entire source bytes in both historical revisions** for seven execution/accounting dependencies: the OpenAI chat adapter, provider-usage tracker, environment configuration, evaluator-cost estimator, frozen dated pricing table, and both Python requirements files. Both historical workflows must explicitly install those requirements. The independently pinned Git blobs are compared and SHA-256 fingerprints retained; the requirements source pins `openai==0.27.10`. This closes a source-provenance gap: identical top-level evaluator calls alone did not establish whether their transport, usage recording, temperature configuration, or cost-accounting implementations had drifted. These **source dependencies did not drift** in the pinned historical commits; this does **not** establish which wheels were installed, that the provider served an identical model, that any API call executed as declared, or that historical costs were empirically authenticated.

**Material, explicit difference:** The original evaluator rejected empty retrieved-evidence context. The recovery evaluator added a zero-successful-source sentinel that forbids outside knowledge, while continuing to reject missing saved evidence if the trace claimed successful sources. Thus the **input admissibility policy changed**, even though the prompt/normalization components and evaluator-call shape are shared. Without independently authenticated original traces and reports it is not valid to claim which recovered cells took the sentinel path, that the original 37 measurements were all correctly loaded, or that all 40 ran under an entirely identical executable.

The existing full-history historical-source CI records the audit result with explicit false provenance/validation flags. Failure signals a source-interpretation problem, not an invitation to rerun evaluations or change numerical outcomes.

**Scientific boundary:** The five-task pilot is diagnostic. The frozen ten-task automated analysis has a post-collection statistical-plan qualification, unresolved fixed-order treatment/time-position confounding, and missing original report/trace custody. This retrospective source comparison is exploratory provenance documentation, not a new causal or confirmatory analysis. It cannot authenticate provider model behavior, historic execution, report source integrity, common scoring for every cell, or genuine human validation. The frozen automated inputs, original analysis results and human rubric remain unchanged.
