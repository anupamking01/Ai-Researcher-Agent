# Diagnostic pilot launch: unambiguous task source and finite temperature

The diagnostic pilot runner previously loaded its task JSON with Python's
permissive `json.loads`. A repeated top-level `task_set_id` or nested
`id`/`question` key would silently take the **last** occurrence. A frozen
task source could consequently appear to define a different experiment
without failing launch preflight. Nonstandard `NaN`/`Infinity` and
overflowing floating literals in unrelated task metadata were also accepted.
Separately, the runner's environment preflight accepted strings such as
`TEMPERATURE=NaN` and `TEMPERATURE=1e309`, which could create a
nonportable, nonfinite experimental manifest.

## Safeguard

`scripts/run_pilot.py` now uses the same ambiguity-rejecting object loader
as the **independent postrun artifact validator**. The pre-dispatch task
manifest check rejects duplicate JSON keys at any depth, nonstandard numeric
constants, nonfinite floating-point literals, malformed/undecodable JSON,
and non-object top-level documents. It then applies the existing complete
task-plan identity checks **before** any optional task filter.

The explicit environment preflight also requires a **finite** parsed
`TEMPERATURE` value before loading the agent or publishing the pilot
manifest. It does not invent a new temperature range or alter the
preexisting valid model/provider configuration contract. Neither safeguard
normalizes, chooses, or repairs an ambiguous task.

## Offline regression

```sh
python -m pytest -q tests/test_pilot_launch_source_integrity.py
python -m pytest -q tests/test_pilot_plan_identity.py tests/test_pilot_workspace_custody.py
```

Synthetic tests cover duplicate manifest and nested task keys, nonfinite
numeric literals, malformed JSON, UTF-8 errors, valid original five-task
source, invalid temperature, and rejection before any model/provider use or
output publication. They do not make live API requests.

This is **prospective launch reproducibility**, not retrospective
authentication of the original pilot or main-study inputs. The five-task
pilot remains diagnostic. The frozen ten-task automated results remain
methodologically qualified (including analysis-plan timing and execution
order). Retrospective sensitivity checks remain exploratory, and genuine
blinded human evaluations remain pending. Recovering original treatment
reports and traces with independent provenance is still the blocking gate
for source-verified human-evaluation distribution.
