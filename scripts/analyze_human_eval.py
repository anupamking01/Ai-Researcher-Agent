"""Run the frozen complementary human-evaluation analysis offline."""
import argparse
import json
from pathlib import Path

from scripts import human_eval_analysis_core as core

OUTPUT_ROOT = core.PACKET_ROOT / "analysis-v1"


def render_markdown(payload):
    def fmt(value):
        return "NA" if value is None else f"{value:.3f}"

    lines = [
        "# Human-evaluation analysis",
        "",
        "Complementary validation; not part of the automated confirmatory p-value family.",
        "",
        "| Dimension | D3 | D6 | P6 | P6V |",
        "|---|---:|---:|---:|---:|",
    ]
    for field in core.DIMS:
        means = [
            fmt(payload["variant_summary"][variant][field]["mean_report_score"])
            for variant in core.VARIANTS
        ]
        lines.append(f"| {field} | " + " | ".join(means) + " |")
    lines += [
        "",
        "Missing scores are not imputed. "
        "No human-validation null-hypothesis p-values are computed.",
        "",
    ]
    return "\n".join(lines)


def write_bundle(payload, output_root):
    output_root = Path(output_root)
    try:
        output_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError(
            f"refusing to overwrite human-analysis output: {output_root}"
        ) from exc
    (output_root / "analysis.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "analysis.md").write_text(
        render_markdown(payload),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ratings", nargs="+", type=Path)
    parser.add_argument("--freeze-root", type=Path, default=core.FREEZE_ROOT)
    parser.add_argument("--packet-root", type=Path, default=core.PACKET_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--analysis-plan", type=Path, default=core.PLAN)
    parser.add_argument("--task-manifest", type=Path, default=core.TASKS)
    args = parser.parse_args()
    try:
        payload = core.analyze(
            args.ratings,
            freeze_root=args.freeze_root,
            packet_root=args.packet_root,
            analysis_plan_path=args.analysis_plan,
            task_manifest_path=args.task_manifest,
        )
        write_bundle(payload, args.output_root)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL ANALYSIS: FAIL: {exc}") from exc
    print(json.dumps(payload, indent=2, sort_keys=True))
    print("HUMAN EVAL ANALYSIS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
