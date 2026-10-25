# Direct agreement-helper row integrity

The frozen human-evaluation workflow computes inter-annotator agreement on
normalized **blinded** rating rows before opening the coordinator treatment key.
The canonical CSV ingestion gate already validates the complete rubric schema,
explanatory notes, and blinding. The separately reusable
`freeze_human_eval_ratings.build_agreement(rows)` helper previously accepted
incomplete dictionaries, interpreting missing rubric dimensions as blank
ratings, or ignored extra treatment-label columns. Direct research-notebook
callers could thus publish plausible but incomplete agreement diagnostics
without passing the canonical freeze importer.

The direct helper now requires exact `RATING_FIELDS` keys, textual normalized
fields and trimmed nonempty pseudonyms/blind IDs. The same frozen 1–5-or-blank
score parser still governs the scores. Endpoint scores (1 or 5) and missing
dimensions require explanatory notes. Notes must display an actual explanation,
remain inert under the existing spreadsheet-formula audit, and pass the shared
treatment-blinding audit. Extra treatment or source columns fail closed instead
of being silently discarded. The canonical freeze process continues to validate
and independently verify the input files before calling this helper.

Synthetic regressions show that missing score columns, omitted notes columns,
extra unblinding columns, typed non-text scores, whitespace-alias identities,
unexplained endpoints/missingness, and unsafe notes are rejected; ordinary
explained ratings retain the same pairwise agreement and missingness semantics.

**Research boundaries:** This is a validity guard for direct pre-unblinding
agreement helper calls, **not** a new statistic, outcome, rating, or source of
authenticity. It does not prove independent human identity or human participation.
No real annotations are created. It does not modify the frozen pilot,
confirmatory, exploratory, or human-validation analyses and cannot replace the
full packet, assignment, submission, freeze, or unblinding verification gates.
