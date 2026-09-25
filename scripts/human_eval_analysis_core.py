"""Core offline analysis for frozen human ratings."""
import hashlib, json, statistics
from pathlib import Path
from scripts import analyze_main_study as stats
from scripts import build_human_eval_packet as packet
from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as blind_verify
from scripts import verify_human_eval_packet as map_verify

ROOT=Path(__file__).resolve().parents[1]
PACKET_ROOT=ROOT/"outputs"/"human_eval"; FREEZE_ROOT=PACKET_ROOT/"frozen-v1"
PLAN=ROOT/"paper"/"HUMAN_EVAL_ANALYSIS_PLAN.md"; TASKS=packet.DEFAULT_TASK_MANIFEST
DIMS=freeze.SCORE_FIELDS; VARIANTS=packet.EXPECTED_VARIANTS
CONTRASTS=(("D3","D6","D6_minus_D3_retrieval_depth"),("D6","P6","P6_minus_D6_planning"),("P6","P6V","P6V_minus_P6_verification"))
SEED=20260925


def fingerprint(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError(f"missing regular file: {path}")
    data=path.read_bytes(); return {"path":path.name,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}


def score(row,field):
    value=str(row.get(field) or "").strip(); return int(value) if value else None


def report_scores(rows):
    grouped={}
    for row in rows: grouped.setdefault(row["blind_id"],[]).append(row)
    scores,counts={},{}
    for blind_id,items in grouped.items():
        for field in DIMS:
            values=[v for v in (score(row,field) for row in items) if v is not None]
            scores[(blind_id,field)]=statistics.mean(values) if values else None; counts[(blind_id,field)]=len(values)
    return scores,counts


def _empty_pair():
    return {"n_pairs":0,"left_mean":None,"right_mean":None,"mean_difference":None,"median_difference":None,
            "bootstrap_95pct_ci_mean_difference":None,"paired_dz":None,"positive_tasks":0,"negative_tasks":0,
            "tied_tasks":0,"task_differences":{}}


def analyze(rating_paths,*,freeze_root=FREEZE_ROOT,packet_root=PACKET_ROOT,packet_path=freeze.DEFAULT_PACKET,
            protocol_path=freeze.DEFAULT_PROTOCOL,assignment_plan_path=freeze.DEFAULT_ASSIGNMENT_PLAN,
            analysis_plan_path=PLAN,task_manifest_path=TASKS,repo_root=ROOT):
    """Verify blind snapshot first, then read treatment identity."""
    rating_paths=[Path(p) for p in rating_paths]; freeze_root=Path(freeze_root); packet_root=Path(packet_root)
    packet_path=Path(packet_path); task_manifest_path=Path(task_manifest_path)
    blinded=blind_verify.verify_frozen_snapshot(rating_paths,freeze_root=freeze_root,packet_path=packet_path,
        protocol_path=Path(protocol_path),assignment_plan_path=Path(assignment_plan_path))
    if blinded.get("n_annotators")!=2 or blinded.get("requires_predeclared_multi_rater_statistic"):
        raise ValueError("analysis plan requires exactly two annotators before unblinding")
    mapped=map_verify.verify_packet(output_root=packet_root,task_manifest_path=task_manifest_path,repo_root=Path(repo_root))
    manifest=packet._load_task_manifest(task_manifest_path); tasks=sorted(manifest["tasks"])
    blind_ids=freeze._packet_blind_ids(packet_path)
    rows,_=freeze._load_ratings([freeze_root/"frozen_ratings.csv"],allowed_blind_ids=set(blind_ids))
    map_rows=map_verify._read_csv((packet_root/"blinding_key.csv").read_bytes(),fields=map_verify.KEY_FIELDS,label="blinding_key.csv")
    mapping={r["blind_id"].strip():r for r in map_rows}
    if set(mapping)!=set(blind_ids) or {r["blind_id"] for r in rows}!=set(blind_ids): raise ValueError("blind-ID coverage mismatch")
    cells={(r["variant_id"].strip(),r["task_id"].strip()):r["blind_id"].strip() for r in map_rows}
    if set(cells)!={(v,t) for v in VARIANTS for t in tasks}: raise ValueError("incomplete treatment/task mapping")
    scores,counts=report_scores(rows); variant_of={b:r["variant_id"].strip() for b,r in mapping.items()}
    summaries={}
    for variant in VARIANTS:
        summaries[variant]={}
        for field in DIMS:
            observed=[scores[(cells[(variant,t)],field)] for t in tasks]; observed=[v for v in observed if v is not None]
            dist={str(i):0 for i in range(1,6)}
            for row in rows:
                value=score(row,field)
                if variant_of[row["blind_id"]]==variant and value is not None: dist[str(value)]+=1
            summaries[variant][field]={"n_reports_total":len(tasks),"n_reports_scored":len(observed),
                "n_raw_scores":sum(counts[(cells[(variant,t)],field)] for t in tasks),
                "mean_report_score":statistics.mean(observed) if observed else None,
                "median_report_score":statistics.median(observed) if observed else None,"raw_score_distribution":dist}
    contrasts={}
    for ci,(left,right,name) in enumerate(CONTRASTS):
        contrasts[name]={}
        for di,field in enumerate(DIMS):
            complete=[t for t in tasks if scores[(cells[(left,t)],field)] is not None and scores[(cells[(right,t)],field)] is not None]
            if complete:
                result=stats._paired_summary([scores[(cells[(left,t)],field)] for t in complete],
                    [scores[(cells[(right,t)],field)] for t in complete],seed=SEED+ci*100+di,exact_p=False)
                result["task_differences"]=dict(zip(complete,result["task_differences"]))
            else: result=_empty_pair()
            result["task_ids_included"]=complete; result["missing_pair_tasks"]=[t for t in tasks if t not in complete]; contrasts[name][field]=result
    agreement=json.loads((freeze_root/"agreement.json").read_text(encoding="utf-8"))
    prov={name:fingerprint(path) for name,path in {"analysis_plan":analysis_plan_path,"task_manifest":task_manifest_path,
        "packet_manifest":packet_root/"manifest.json","treatment_mapping":packet_root/"blinding_key.csv",
        "freeze_manifest":freeze_root/"freeze_manifest.json","frozen_ratings":freeze_root/"frozen_ratings.csv",
        "pre_unblinding_agreement":freeze_root/"agreement.json"}.items()}
    return {"schema_version":1,"study_id":"budget-main-v1","task_set_id":manifest["task_set_id"],"status":"human_validation_analysis",
        "analysis_scope":"complementary_not_main_confirmatory","human_ratings_generated":False,"treatment_outputs_rerun":False,
        "n_tasks":len(tasks),"task_ids":tasks,"variants":list(VARIANTS),"dimensions":list(DIMS),
        "report_score_aggregation":"mean_observed_rater_scores_per_report_dimension","bootstrap_seed":SEED,
        "bootstrap_draws":stats.BOOTSTRAP_DRAWS,"hypothesis_tests":"none_predeclared_for_human_validation",
        "verification":{"blinded_freeze":blinded,"packet_and_mapping":mapped},"provenance":prov,
        "pre_unblinding_agreement":agreement,"variant_summary":summaries,"paired_contrasts":contrasts}
