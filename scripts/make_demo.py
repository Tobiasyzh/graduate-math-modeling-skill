"""Create and actually run the bundled synthetic example in a new directory."""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys

from common import load_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--plot", action="store_true", help="Also run matplotlib plot generation")
    args = parser.parse_args()
    root = args.directory.resolve()
    skill = Path(__file__).resolve().parents[1]
    scripts = skill / "scripts"

    def call(script, *arguments):
        subprocess.run([sys.executable, str(scripts / script), *map(str, arguments)], check=True)

    call("init_project.py", root, "--name", "合成资源分配练习", "--mode", "practice")
    for source, target in [("items.csv", "data/raw/items.csv"), ("config.json", "config.json"),
                           ("solve_allocation.py", "src/solve_allocation.py")]:
        shutil.copyfile(skill / "assets/demo" / source, root / target)
    call("run_experiment.py", "--project", root, "--id", "demo-01", "--seed", 42,
         "--input", "data/raw/items.csv", "--input", "config.json", "--source", "src/solve_allocation.py",
         "--output", "results/demo-01/sensitivity.csv", "--metrics", "results/demo-01/metrics.json",
         "--", sys.executable, "src/solve_allocation.py")
    metrics = load_json(root / "results/demo-01/metrics.json")
    project = load_json(root / "project.json")
    project["questions"] = [
        {"id": "Q1", "requirement": "预算6下比较可行贪心解与完整枚举最优解",
         "depends_on": [], "status": "verified", "run_ids": ["demo-01"],
         "artifacts": ["results/demo-01/metrics.json"]},
        {"id": "Q2", "requirement": "检查给定七种预算下的收益与资源使用",
         "depends_on": ["Q1"], "status": "verified", "run_ids": ["demo-01"],
         "artifacts": ["results/demo-01/sensitivity.csv"]}]
    claims = []
    for cid, label, metric in [("C1", "完整枚举的最优收益", "exact.benefit"),
                                ("C2", "单位收益比贪心的收益", "greedy.benefit")]:
        method, field = metric.split(".")
        value = metrics[method][field]
        claims.append({"id": cid, "question_id": "Q1", "kind": "numeric", "run_id": "demo-01",
                       "metric": metric, "value": value, "unit": "benefit_points",
                       "text": f"{label}为{value}收益点", "scope": "合成3项目、预算6的单一实例"})
    if args.plot:
        shutil.copyfile(scripts / "plot_results.py", root / "src/plot_results.py")
        call("run_experiment.py", "--project", root, "--id", "plot-01", "--seed", 42,
             "--input", "results/demo-01/sensitivity.csv", "--source", "src/plot_results.py",
             "--output", "figures/budget-benefit.svg", "--output", "figures/budget-benefit.png",
             "--output", "figures/budget-benefit.source.json", "--", sys.executable,
             "src/plot_results.py", "--input", "results/demo-01/sensitivity.csv", "--out", "figures/budget-benefit",
             "--kind", "line", "--x", "budget", "--y", "benefit", "--group", "method",
             "--xlabel", "Budget (resource units)", "--ylabel", "Benefit (points)")
        project["questions"][1]["run_ids"].append("plot-01")
        project["questions"][1]["artifacts"].append("figures/budget-benefit.png")
    write_json(root / "project.json", project)
    write_json(root / "claims.json", claims)
    (root / "paper/result-note.md").write_text(
        "# 合成教学结果，非真实赛题论文\n\n"
        f"预算为6资源单位时，完整枚举得到收益{metrics['exact']['benefit']}点，选择"
        f"{'、'.join(metrics['exact']['selected'])}。按单位收益比依次选择的基线得到"
        f"{metrics['greedy']['benefit']}点。枚举检查了全部{metrics['exact']['all_subsets']}种二元组合，"
        "因此能在此离散可行域内确认最优；这个结论不能推广为贪心总是较差或枚举适合大规模。\n\n"
        "敏感性CSV记录各预算的实际计算值；图中连线只辅助读图，不代表未计算预算的插值最优值。"
        "如果生成了图，仍须查看导出图检查标签和可读性。"
        "不存在统计重复，因此不绘制或声称置信区间。本例未完成正式比赛规则、AI声明和人工终审。\n",
        encoding="utf-8")
    (root / "STATUS.md").write_text(
        "# 当前状态\n\n合成例题已实际求解，结果和声明绑定。手工检查、AI活动日志与正式交稿审计尚未完成。\n\n"
        "复跑到新的目录；本例不覆盖真实题面、不证明竞赛表现。\n", encoding="utf-8")
    call("audit_project.py", root, "--stage", "draft", "--output", "checks/draft-01.json")
    print(f"Demo complete: {root}; human/contest reviews intentionally remain pending.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
