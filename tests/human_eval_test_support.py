"""Synthetic fixture helpers for human-evaluation tests."""

import csv
from pathlib import Path

from scripts import freeze_human_eval_ratings as freeze


def write_valid_annotator_attestations(
    path: Path,
    annotator_ids,
) -> Path:
    """Write protocol-valid synthetic attestations for pseudonymous test IDs."""
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(freeze.ANNOTATOR_ATTESTATION_FIELDS),
        )
        writer.writeheader()
        for annotator_id in annotator_ids:
            writer.writerow(
                {
                    "annotator_id": annotator_id,
                    "eligibility_decided_before_report_access": "true",
                    "treatment_identity_unseen_during_scoring": "true",
                    "scored_independently": "true",
                    "human_only_scoring": "true",
                    "generated_or_selected_treatment_reports": "false",
                    "material_conflicts_resolved_before_assignment": "true",
                }
            )
    return path
