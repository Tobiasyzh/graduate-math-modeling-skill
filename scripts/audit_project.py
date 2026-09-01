"""Audit declared local evidence, not scientific quality or award prospects."""
from pathlib import Path
from datetime import datetime
import argparse
import json
import math
import sys

from common import finite_number, fingerprint, load_json, metric_value, safe_path, valid_id, utc_now


def audit(root, stage="draft"):
    root = Path(root).resolve()
    issues, checked_runs = [], {}

    def add(level, code, message):
        issues.append({"level": level, "code": code, "message": message})

    def incomplete(code, message):
        add("error" if stage == "submission" else "warning", code, message)

    def sequence(value, context):
        if not isinstance(value, list):
            add("error", "field_type", f"{context}: expected a list")
            return []
        return value

    def mapping(value, context):
        if not isinstance(value, dict):
            add("error", "field_type", f"{context}: expected an object")
            return {}
        return value

    def read(relative, expected_type):
        try:
            value = load_json(safe_path(root, relative))
            if not isinstance(value, expected_type):
                raise ValueError(f"Expected {expected_type.__name__}")
            return value
        except (ValueError, OSError) as exc:
            add("error", "invalid_file", f"{relative}: {exc}")
            return expected_type()

    def check_artifact(relative, context):
        try:
            path = safe_path(root, relative)
            if not path.is_file():
                raise ValueError("file does not exist")
        except (ValueError, OSError) as exc:
            add("error", "missing_artifact", f"{context}: {relative}: {exc}")

    def check_run(run_id):
        try:
            valid_id(run_id)
        except ValueError as exc:
            add("error", "invalid_run_id", str(exc))
            return {}
        if run_id in checked_runs:
            return checked_runs[run_id]
        run = read(f"runs/{run_id}/run.json", dict)
        checked_runs[run_id] = run
        if run.get("id") != run_id:
            add("error", "run_id_mismatch", run_id)
        if run.get("status") != "completed" or run.get("exit_code") != 0:
            add("error", "failed_run", f"{run_id}: not a completed successful run")
        if not run.get("sources") or not run.get("outputs"):
            add("error", "run_provenance", f"{run_id}: missing source/output fingerprints")
        recorded_outputs = {v.get("path") for v in sequence(run.get("outputs", []), f"{run_id}.outputs")
                            if isinstance(v, dict) and isinstance(v.get("path"), str)}
        for declared in sequence(run.get("declared_outputs", []), f"{run_id}.declared_outputs"):
            if not isinstance(declared, str):
                add("error", "field_type", f"{run_id}: output path must be a string")
                continue
            if declared not in recorded_outputs:
                add("error", "run_output_missing", f"{run_id}: {declared}")
        for kind in ["inputs", "sources", "outputs"]:
            for entry in sequence(run.get(kind, []), f"{run_id}.{kind}"):
                try:
                    current = fingerprint(root, entry["path"])
                    if current["sha256"] != entry["sha256"]:
                        add("error", "stale_evidence", f"{run_id}: {kind}: {entry['path']}")
                except (KeyError, TypeError, ValueError, OSError) as exc:
                    add("error", "invalid_fingerprint", f"{run_id}: {kind}: {exc}")
        if run.get("metrics_path") and not isinstance(run["metrics_path"], str):
            add("error", "field_type", f"{run_id}.metrics_path must be a string")
        elif run.get("metrics_path"):
            if run["metrics_path"] not in recorded_outputs:
                add("error", "unbound_metrics", f"{run_id}: metrics lack an output fingerprint")
            actual_metrics = read(run["metrics_path"], dict)
            if actual_metrics != run.get("metrics"):
                add("error", "metrics_mismatch", f"{run_id}: recorded metrics differ from actual file")
        return run

    project = read("project.json", dict)
    if project.get("schema_version") != 1:
        add("error", "schema_version", "Expected project schema_version=1")
    if project.get("mode") not in ["practice", "competition", "postmortem"]:
        add("error", "mode", "Unknown project mode")
    questions = project.get("questions", [])
    if not isinstance(questions, list):
        add("error", "questions_type", "questions must be a list")
        questions = []
    if not questions:
        incomplete("no_questions", "No question requirements have been recorded")
    qids = set()
    for q in questions:
        if not isinstance(q, dict) or not isinstance(q.get("id"), str) or not q.get("id") or q.get("id") in qids:
            add("error", "question_id", "Missing/duplicate question ID")
            continue
        qids.add(q["id"])
        if not q.get("requirement"):
            incomplete("question_requirement", q["id"])
        if q.get("status") != "verified":
            incomplete("question_incomplete", f"{q['id']}: {q.get('status', 'missing')}")
        if q.get("status") == "verified" and not q.get("run_ids") and not q.get("proof_artifact"):
            add("error", "unsupported_question", f"{q['id']}: no run or proof artifact")
        for run_id in sequence(q.get("run_ids", []), f"{q['id']}.run_ids"):
            check_run(run_id)
        for path in sequence(q.get("artifacts", []), f"{q['id']}.artifacts"):
            check_artifact(path, q["id"])
        if q.get("proof_artifact"):
            check_artifact(q["proof_artifact"], q["id"])
    for q in questions:
        if isinstance(q, dict):
            for dependency in sequence(q.get("depends_on", []), "question.depends_on"):
                if not isinstance(dependency, str) or dependency not in qids or dependency == q.get("id"):
                    add("error", "question_dependency", f"{q.get('id')}: {dependency}")

    claims = read("claims.json", list)
    seen_claims = set()
    for claim in claims:
        if not isinstance(claim, dict):
            add("error", "claim_type", "Claim must be an object")
            continue
        cid = claim.get("id", "")
        if not isinstance(cid, str) or not cid or cid in seen_claims:
            add("error", "claim_id", "Missing/duplicate claim ID")
            continue
        seen_claims.add(cid)
        if not isinstance(claim.get("question_id"), str) or claim.get("question_id") not in qids:
            add("error", "claim_question", f"{cid}: unknown question")
        if not claim.get("text") or not claim.get("scope"):
            incomplete("claim_context", f"{cid}: needs text and scope")
        if claim.get("kind") == "numeric":
            run = check_run(claim.get("run_id", ""))
            try:
                actual = metric_value(run.get("metrics", {}), claim.get("metric"))
                if not finite_number(claim.get("value")) or not math.isclose(actual, claim["value"], rel_tol=1e-9, abs_tol=1e-12):
                    add("error", "claim_value", f"{cid}: value differs from recorded raw metric {actual}")
                if not claim.get("unit"):
                    incomplete("claim_unit", f"{cid}: use a real unit or 'dimensionless'")
            except (ValueError, TypeError, KeyError) as exc:
                add("error", "claim_metric", f"{cid}: {exc}")
        elif claim.get("kind") in ["derived", "qualitative"]:
            if not claim.get("evidence"):
                add("error", "claim_evidence", f"{cid}: needs a derivation/evidence file")
            for path in sequence(claim.get("evidence", []), f"{cid}.evidence"):
                check_artifact(path, cid)
        else:
            add("error", "claim_kind", f"{cid}: use numeric, derived or qualitative")
    if stage != "analysis" and not claims:
        incomplete("no_claims", "No evidence-backed manuscript claims recorded")

    sources = read("sources.json", list)
    source_ids = set()
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("id"), str) or not source.get("id") or source.get("id") in source_ids:
            add("error", "source_id", "Missing/duplicate source ID")
            continue
        source_ids.add(source["id"])
        if source.get("cited") and (source.get("verification") != "verified" or not source.get("locator")):
            incomplete("unverified_citation", source["id"])

    competition = mapping(project.get("competition", {}), "competition")
    if project.get("mode") == "competition":
        if competition.get("rules_status") != "current_verified" or not competition.get("rule_sources"):
            incomplete("rules_unverified", "Current contest rules/source records required")
        if competition.get("ai_policy") not in ["permitted", "restricted"] or not competition.get("ai_scope_notes"):
            incomplete("ai_scope", "AI scope unknown/prohibited or activity limits undocumented")
        if stage != "analysis" and competition.get("template_verified") is not True:
            incomplete("template_unverified", "Current official formatting has not been verified")

    if stage == "submission":
        required_reviews = ["rule_compliance", "model_validity", "data_leakage", "numerical_validation",
                            "citations", "visual_inspection", "anonymity", "ai_disclosure", "human_understanding"]
        reviews = mapping(project.get("reviews", {}), "reviews")
        for name in required_reviews:
            item = mapping(reviews.get(name, {}), f"reviews.{name}")
            if item.get("status") not in ["passed", "not_applicable"] or not item.get("notes"):
                add("error", "manual_review", f"{name}: unfinished, failed or unexplained")
            if item.get("status") == "passed" and not item.get("evidence"):
                add("error", "manual_review_evidence", f"{name}: no recorded evidence")
            for path in sequence(item.get("evidence", []), f"reviews.{name}.evidence"):
                check_artifact(path, f"reviews.{name}")
        ai_path = root / "ai_usage.jsonl"
        if not ai_path.is_file() or not ai_path.read_text(encoding="utf-8-sig").strip():
            add("error", "ai_log", "AI activity record is empty; record actual use and review disclosure")
        else:
            for line_number, line in enumerate(ai_path.read_text(encoding="utf-8-sig").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        raise ValueError("expected an object")
                    timestamp = datetime.fromisoformat(item.get("time", "").replace("Z", "+00:00"))
                    if timestamp.utcoffset() is None:
                        raise ValueError("time requires a UTC offset")
                    if not item.get("purpose"):
                        raise ValueError("purpose required")
                    if item.get("used", True) is False:
                        if not item.get("verification"):
                            raise ValueError("non-use record needs verification/scope explanation")
                        continue
                    if item.get("used", True) is not True:
                        raise ValueError("used must be boolean")
                    for key in ["tool", "verification"]:
                        if not item.get(key):
                            raise ValueError(f"{key} required")
                    if not isinstance(item.get("adopted"), bool):
                        raise ValueError("adopted must be boolean")
                    for key in ["input_refs", "output_refs"]:
                        if not isinstance(item.get(key), list):
                            raise ValueError(f"{key} must be a list")
                except (ValueError, TypeError, AttributeError) as exc:
                    add("error", "ai_log_format", f"line {line_number}: {exc}")

    errors = sum(x["level"] == "error" for x in issues)
    warnings = sum(x["level"] == "warning" for x in issues)
    return {"schema_version": 1, "checked_at": utc_now(), "stage": stage,
            "status": "fail" if errors else "review" if warnings else "pass",
            "errors": errors, "warnings": warnings, "questions": len(questions),
            "claims": len(claims), "checked_runs": sorted(checked_runs), "issues": issues,
            "limitations": "Checks only declared files/fields. Does not prove mathematics, no leakage, true human contributions, citation validity, visual quality, contest eligibility, or award potential."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--stage", choices=["analysis", "draft", "submission"], default="draft")
    parser.add_argument("--output", help="Optional new project-relative JSON report")
    args = parser.parse_args()
    report = audit(args.directory, args.stage)
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        path = safe_path(args.directory, args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    print(payload)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
