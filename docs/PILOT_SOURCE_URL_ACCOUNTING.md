# Diagnostic pilot source-URL accounting integrity

The live pilot's source budget counts **distinct scheduled browse URLs**.
Its producer first records a scheduled URL and later places that same URL
in either the successful or failed browse ledger. A cardinality check alone
cannot catch a substituted, duplicated, or contradictory evidence URL:
for example, four success records and two failures can still appear valid
even when one success is not among the six scheduled sources.

`scripts/validate_pilot_artifacts.py` now fails closed unless:

- The three URL collections are actual lists of nonempty, unpadded strings.
- Scheduled URLs are unique; duplicate browsing is not silently treated as
  independent source-budget expenditure.
- Successful and failed URLs form **exactly** the multiset of scheduled URLs;
  a URL cannot disappear, be imported from an unrelated source, or be
  classified both ways.
- The pre-existing source counts, total budget, success requirement, and
  workflow-completion checks also hold.

Order within the outcomes is deliberately not significant: asynchronous
browsing can complete out of schedule order. The check uses exact recorded
strings rather than normalizing/rewriting historical URL identities.

Offline regression reproduction (no model or browser calls):

```sh
python -m pytest -q tests/test_pilot_source_url_accounting.py
```

This change is a **forward-looking diagnostic-pilot artifact safeguard**.
It does not reconstruct unavailable original trace artifacts, authenticate
their custody, revise the preserved five-task pilot records, or alter the
frozen ten-task automated analysis. Pilot results remain diagnostic;
retrospective robustness analyses remain exploratory; prospective
precollection automated preregistration is unestablished; independent blinded
human validation has not occurred.
