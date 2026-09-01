"""Create a new modeling workspace without overwriting an existing project."""
from pathlib import Path
import argparse
import sys

from common import utc_now, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--name", default="Modeling project")
    parser.add_argument("--mode", choices=["practice", "competition", "postmortem"], default="practice")
    parser.add_argument("--language", choices=["python", "matlab"], default="python")
    parser.add_argument("--competition", default="unspecified")
    parser.add_argument("--year", type=int)
    args = parser.parse_args()
    root = args.directory.resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        parser.error("Destination must be absent or empty; adapt an existing project manually.")
    root.mkdir(parents=True, exist_ok=True)
    for relative in ["data/raw", "data/processed", "src", "models", "results", "figures", "paper", "runs", "checks"]:
        (root / relative).mkdir(parents=True, exist_ok=True)
    reviews = {key: {"status": "pending", "evidence": [], "notes": ""} for key in
               ["rule_compliance", "model_validity", "data_leakage", "numerical_validation",
                "citations", "visual_inspection", "anonymity", "ai_disclosure", "human_understanding"]}
    write_json(root / "project.json", {
        "schema_version": 1, "name": args.name, "created_at": utc_now(),
        "mode": args.mode, "language": args.language,
        "competition": {"name": args.competition, "year": args.year,
                        "rules_status": "unknown", "ai_policy": "unknown", "ai_scope_notes": "",
                        "rule_sources": [], "deadlines": {}, "template_verified": False},
        "questions": [], "reviews": reviews,
    })
    for name in ["claims.json", "sources.json"]:
        write_json(root / name, [])
    (root / "ai_usage.jsonl").write_text("", encoding="utf-8")
    (root / "STATUS.md").write_text(
        "# 当前状态\n\n项目已初始化，尚无已验证结果。\n\n"
        "## 接下来\n\n核验题面、附件与活动状态；逐项登记project.json中的questions。\n\n"
        "## 决策与待解决问题\n\n记录决定、依据、受影响任务和下一步；不保存敏感凭据。\n",
        encoding="utf-8")
    template = Path(__file__).resolve().parents[1] / "assets" / "manuscript-outline.md"
    if template.is_file():
        (root / "paper" / "outline.md").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Created: {root}")
    print("No results, rule approvals, or review passes have been fabricated.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
