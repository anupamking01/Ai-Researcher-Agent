"""Core offline analysis for frozen human ratings.

The analysis snapshots every blinded artifact before pre-unblinding verification,
then snapshots treatment-mapping artifacts only after that blinded gate passes.
Verification and downstream analysis therefore consume the same captured bytes,
so an editor save cannot change the analyzed revision after it was verified.
"""
import hashlib
import json
import math
import random
import statistics
import tempfile
from pathlib import Path

from scripts import build_human_eval_packet as packet
from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as blind_verify
from scripts import verify_human_eval_packet as map_verify

ROOT = Path(__file__).resolve().parents[1]
PACKET_ROOT = ROOT / "outputs" / "human_eval"
FREEZE_ROOT = PACKET_ROOT / "frozen-v1"
PLAN = ROOT / "paper" / "HUMAN_EVAL_ANALYSIS_PLAN.md"
TASKS = packet.DEFAULT_TASK_MANIFEST
DIMS = freeze.SCORE_FIELDS
VARIANTS = packet.EXPECTED_VARIANTS
CONTRASTS = (
    ("D3", "D6", "D6_minus_D3_retrieval_depth"),
    ("D6", "P6", "P6_minus_D6_planning"),
    ("P6", "P6V", "P6V_minus_P6_verification"),
)
SEED = 20260925
BOOTSTRAP_DRAWS = 20_000


def fingerprint(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing regular file: {path}")
    data = path.read_bytes()
    return {
        "path": path.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _snapshot_file(source, destination, *, label):
    """Read one regular file once and persist exactly those bytes in scratch space."""
    source = Path(source)
    destination = Path(destination)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"{label} must be a regular file: {source}")
    content = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def _snapshot_raw_ratings(rating_paths, root):
    snapshots = []
    for index, path in enumerate(rating_paths, start=1):
        path = Path(path)
        destination = Path(root) / f"{index:04d}" / path.name
        snapshots.append(_snapshot_file(path, destination, label=f"raw rating input {index}"))
    return snapshots


def score(row, field):
    value = str(row.get(field) or "").strip()
    return int(value) if value else None


def _percentile(sorted_values, q):
    if not sorted_values:
        raise ValueError("percentile requires values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    weight = pos - lo
    return sorted_values[lo] * (1.0 - weight) + sorted_values[hi] * weight


def _bootstrap_mean_ci(diffs, *, seed):
    rng = random.Random(seed)
    n = len(diffs)
    draws = [
        statistics.mean([diffs[rng.randrange(n)] for _ in range(n)])
        for _ in range(BOOTSTRAP_DRAWS)
    ]
    draws.sort()
    return [_percentile(draws, 0.025), _percentile(draws, 0.975)]


def _paired_summary(left, right, *, seed):
    if len(left) != len(right) or not left:
        raise ValueError("paired vectors must be non-empty and equal length")
    diffs = [b - a for a, b in zip(left, right)]
    sd = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
    return {
        "n_pairs": len(diffs),
        "left_mean": statistics.mean(left),
        "right_mean": statistics.mean(right),
        "mean_difference": statistics.mean(diffs),
        "median_difference": statistics.median(diffs),
        "bootstrap_95pct_ci_mean_difference": _bootstrap_mean_ci(diffs, seed=seed),
        "paired_dz": (statistics.mean(diffs) / sd) if sd > 0 else None,
        "positive_tasks": sum(d > 0 for d in diffs),
        "negative_tasks": sum(d < 0 for d in diffs),
        "tied_tasks": sum(d == 0 for d in diffs),
        "task_differences": diffs,
    }


def report_scores(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["blind_id"], []).append(row)
    scores, counts = {}, {}
    for blind_id, items in grouped.items():
        for field in DIMS:
            values = [v for v in (score(row, field) for row in items) if v is not None]
            scores[(blind_id, field)] = statistics.mean(values) if values else None
            counts[(blind_id, field)] = len(values)
    return scores, counts


def _empty_pair():
    return {
        "n_pairs": 0,
        "left_mean": None,
        "right_mean": None,
        "mean_difference": None,
        "median_difference": None,
        "bootstrap_95pct_ci_mean_difference": None,
        "paired_dz": None,
        "positive_tasks": 0,
        "negative_tasks": 0,
        "tied_tasks": 0,
        "task_differences": {},
    }


def analyze(
    rating_paths,
    *,
    freeze_root=FREEZE_ROOT,
    packet_root=PACKET_ROOT,
    packet_path=freeze.DEFAULT_PACKET,
    protocol_path=freeze.DEFAULT_PROTOCOL,
    assignment_plan_path=freeze.DEFAULT_ASSIGNMENT_PLAN,
    analysis_plan_path=PLAN,
    task_manifest_path=TASKS,
    repo_root=ROOT,
):
    """Verify captured blinded bytes first, then capture and verify treatment identity."""
    rating_paths = [Path(path) for path in rating_paths]
    freeze_root = Path(freeze_root)
    packet_root = Path(packet_root)
    packet_path = Path(packet_path)
    protocol_path = Path(protocol_path)
    assignment_plan_path = Path(assignment_plan_path)
    analysis_plan_path = Path(analysis_plan_path)
    task_manifest_path = Path(task_manifest_path)
    repo_root = Path(repo_root)

    if freeze_root.is_symlink() or not freeze_root.is_dir():
        raise ValueError(f"freeze root must be a regular directory: {freeze_root}")
    if packet_root.is_symlink() or not packet_root.is_dir():
        raise ValueError(f"human-evaluation output root must be a regular directory: {packet_root}")

    with tempfile.TemporaryDirectory(prefix="vera-human-analysis-") as scratch_name:
        scratch = Path(scratch_name)

        # Capture the blinded side before any verifier is called. Human scores,
        # agreement, packet IDs, and frozen provenance below are the exact bytes
        # that both verification and analysis will use.
        blind_root = scratch / "blinded"
        blind_freeze = blind_root / "freeze"
        blind_packet = _snapshot_file(
            packet_path,
            blind_root / "packet" / packet_path.name,
            label="blinded packet",
        )
        blind_protocol = _snapshot_file(
            protocol_path,
            blind_root / "protocol" / protocol_path.name,
            label="human-evaluation protocol",
        )
        blind_assignment = _snapshot_file(
            assignment_plan_path,
            blind_root / "assignment" / assignment_plan_path.name,
            label="human-evaluation assignment plan",
        )
        blind_analysis_plan = _snapshot_file(
            analysis_plan_path,
            blind_root / "analysis_plan" / analysis_plan_path.name,
            label="human-evaluation analysis plan",
        )
        for filename in ("freeze_manifest.json", "frozen_ratings.csv", "agreement.json"):
            _snapshot_file(
                freeze_root / filename,
                blind_freeze / filename,
                label=f"blinded freeze {filename}",
            )
        blind_rating_paths = _snapshot_raw_ratings(rating_paths, blind_root / "raw_ratings")

        blinded = blind_verify.verify_frozen_snapshot(
            blind_rating_paths,
            freeze_root=blind_freeze,
            packet_path=blind_packet,
            protocol_path=blind_protocol,
            assignment_plan_path=blind_assignment,
        )
        if (
            blinded.get("n_annotators") != 2
            or blinded.get("requires_predeclared_multi_rater_statistic")
        ):
            raise ValueError("analysis plan requires exactly two annotators before unblinding")

        # Only after the blinded gate passes may treatment identity be read.
        mapping_root = scratch / "mapping"
        mapping_root.mkdir(parents=True)
        mapping_packet = mapping_root / "packet.jsonl"
        mapping_packet.write_bytes(blind_packet.read_bytes())
        mapping_manifest = _snapshot_file(
            packet_root / "manifest.json",
            mapping_root / "manifest.json",
            label="human-evaluation packet manifest",
        )
        mapping_key = _snapshot_file(
            packet_root / "blinding_key.csv",
            mapping_root / "blinding_key.csv",
            label="coordinator blinding key",
        )
        _snapshot_file(
            packet_root / "ratings_template.csv",
            mapping_root / "ratings_template.csv",
            label="human-evaluation ratings template",
        )
        mapping_tasks = _snapshot_file(
            task_manifest_path,
            scratch / "task_manifest" / task_manifest_path.name,
            label="frozen task manifest",
        )

        mapped = map_verify.verify_packet(
            output_root=mapping_root,
            task_manifest_path=mapping_tasks,
            repo_root=repo_root,
        )

        manifest = packet._load_task_manifest(mapping_tasks)
        tasks = sorted(manifest["tasks"])
        blind_ids = freeze._packet_blind_ids(blind_packet)
        frozen_ratings_path = blind_freeze / "frozen_ratings.csv"
        rows, _ = freeze._load_ratings(
            [frozen_ratings_path],
            allowed_blind_ids=set(blind_ids),
        )
        map_rows = map_verify._read_csv(
            mapping_key.read_bytes(),
            fields=map_verify.KEY_FIELDS,
            label="blinding_key.csv",
        )
        mapping = {row["blind_id"].strip(): row for row in map_rows}
        if set(mapping) != set(blind_ids) or {row["blind_id"] for row in rows} != set(blind_ids):
            raise ValueError("blind-ID coverage mismatch")

        cells = {
            (row["variant_id"].strip(), row["task_id"].strip()): row["blind_id"].strip()
            for row in map_rows
        }
        if set(cells) != {(variant, task_id) for variant in VARIANTS for task_id in tasks}:
            raise ValueError("incomplete treatment/task mapping")

        scores, counts = report_scores(rows)
        variant_of = {
            blind_id: row["variant_id"].strip()
            for blind_id, row in mapping.items()
        }
        summaries = {}
        for variant in VARIANTS:
            summaries[variant] = {}
            for field in DIMS:
                observed = [scores[(cells[(variant, task_id)], field)] for task_id in tasks]
                observed = [value for value in observed if value is not None]
                dist = {str(i): 0 for i in range(1, 6)}
                for row in rows:
                    value = score(row, field)
                    if variant_of[row["blind_id"]] == variant and value is not None:
                        dist[str(value)] += 1
                summaries[variant][field] = {
                    "n_reports_total": len(tasks),
                    "n_reports_scored": len(observed),
                    "n_raw_scores": sum(
                        counts[(cells[(variant, task_id)], field)]
                        for task_id in tasks
                    ),
                    "mean_report_score": statistics.mean(observed) if observed else None,
                    "median_report_score": statistics.median(observed) if observed else None,
                    "raw_score_distribution": dist,
                }

        contrasts = {}
        for contrast_index, (left, right, name) in enumerate(CONTRASTS):
            contrasts[name] = {}
            for dimension_index, field in enumerate(DIMS):
                complete = [
                    task_id
                    for task_id in tasks
                    if scores[(cells[(left, task_id)], field)] is not None
                    and scores[(cells[(right, task_id)], field)] is not None
                ]
                if complete:
                    result = _paired_summary(
                        [scores[(cells[(left, task_id)], field)] for task_id in complete],
                        [scores[(cells[(right, task_id)], field)] for task_id in complete],
                        seed=SEED + contrast_index * 100 + dimension_index,
                    )
                    result["task_differences"] = dict(
                        zip(complete, result["task_differences"])
                    )
                else:
                    result = _empty_pair()
                result["task_ids_included"] = complete
                result["missing_pair_tasks"] = [
                    task_id for task_id in tasks if task_id not in complete
                ]
                contrasts[name][field] = result

        agreement_path = blind_freeze / "agreement.json"
        agreement = json.loads(agreement_path.read_text(encoding="utf-8"))
        provenance = {
            name: fingerprint(path)
            for name, path in {
                "analysis_plan": blind_analysis_plan,
                "task_manifest": mapping_tasks,
                "packet_manifest": mapping_manifest,
                "treatment_mapping": mapping_key,
                "freeze_manifest": blind_freeze / "freeze_manifest.json",
                "frozen_ratings": frozen_ratings_path,
                "pre_unblinding_agreement": agreement_path,
            }.items()
        }

        return {
            "schema_version": 1,
            "study_id": "budget-main-v1",
            "task_set_id": manifest["task_set_id"],
            "status": "human_validation_analysis",
            "analysis_scope": "complementary_not_main_confirmatory",
            "human_ratings_generated": False,
            "treatment_outputs_rerun": False,
            "n_tasks": len(tasks),
            "task_ids": tasks,
            "variants": list(VARIANTS),
            "dimensions": list(DIMS),
            "report_score_aggregation": "mean_observed_rater_scores_per_report_dimension",
            "bootstrap_seed": SEED,
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "hypothesis_tests": "none_predeclared_for_human_validation",
            "verification": {
                "blinded_freeze": blinded,
                "packet_and_mapping": mapped,
                "analysis_inputs_snapshot_bound": True,
            },
            "provenance": provenance,
            "pre_unblinding_agreement": agreement,
            "variant_summary": summaries,
            "paired_contrasts": contrasts,
        }
