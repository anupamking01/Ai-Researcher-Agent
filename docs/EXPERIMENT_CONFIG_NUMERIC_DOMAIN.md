# Prospective experimental resource-config integrity

## Motivation

VERA's treatment definition measures scheduled browsing-call budgets as **counts**, not continuous quantities. In the runtime configuration, comparisons such as `source_budget <= 0` and `max_concurrent_browses <= 0` previously allowed booleans and fractional positive numbers. Similarly, `browse_timeout_seconds <= 0` allowed `NaN`, because comparisons against it return false, and `Infinity` was accepted. The standalone source-budget allocator also accepted nonintegral arguments. Such inputs can silently undermine the intended budget and timeout envelope in prospective/pilot runs.

## Guardrail

`ExperimentConfig` now requires positive **exact Python integers** (excluding `bool`) for `source_budget`, `search_candidate_multiplier` and `max_concurrent_browses`. Browser and run timeouts must be positive, finite built-in integers or floats (excluding `bool`, strings, infinity, NaN and values that cannot be represented as finite runtime numbers). `allocate_source_budgets` requires nonnegative exact integer total budgets and query counts before calculating any allocation. Zero-query behavior remains unchanged.

These checks reject inconsistent declarations **before a treatment run begins**; they do not impose new maximum budgets, alter budget allocation, silently coerce fractional quantities, fill failed observations or rerun an evaluator. Existing frozen configurations D3=3, D6=6, P6=6 and P6V=6 and valid run traces are unaffected.

## Validation and scientific boundaries

`tests/test_experiment_config_numeric_guards.py` provides synthetic, offline adversarial and valid-boundary coverage for all affected fields and allocation inputs, including booleans, fractional values, NaN, infinities and overflow-sized timeout integers. Existing tests cover canonical allocations and runtime flows. No treatment, common evaluator, pilot, confirmatory analysis, exploratory audit result, or human rating is recomputed by these tests.

This is a **prospective configuration-domain integrity safeguard**. It cannot retroactively establish that historical runs used particular timeouts; established manifests/traces and provenance remain the authoritative evidence. Frozen automated confirmatory claims, separate post-hoc exploratory analyses, diagnostic pilot results and pending human validation must remain distinct.
