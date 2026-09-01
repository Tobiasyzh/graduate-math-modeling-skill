"""Synthetic binary allocation example, exact enumeration vs ratio greedy.

Pure Python; intentionally tiny. Enumeration is a verification baseline, not a
scalable solver. No fitted models, invented measurements or third-party data.
"""
from pathlib import Path
from fractions import Fraction
from itertools import product
import csv
import json
import os


def read_inputs():
    with Path("data/raw/items.csv").open(encoding="utf-8-sig", newline="") as handle:
        items = [{"item": r["item"], "cost": int(r["cost"]), "benefit": int(r["benefit"])}
                 for r in csv.DictReader(handle)]
    config = json.loads(Path("config.json").read_text(encoding="utf-8"))
    if not 1 <= len(items) <= 18:
        raise ValueError("Demo enumeration supports 1–18 items only")
    if len({r["item"] for r in items}) != len(items):
        raise ValueError("Item IDs must be unique")
    if any(r["cost"] <= 0 or r["benefit"] < 0 for r in items):
        raise ValueError("Positive integer costs and nonnegative integer benefits required")
    budgets = [config["budget"]] + config["sensitivity_budgets"]
    if any(type(b) is not int or b < 0 for b in budgets):
        raise ValueError("Budgets must be nonnegative integers")
    return items, config


def summarize(items, chosen, budget):
    # Independent recomputation from IDs, rather than trusting solver counters.
    if len(chosen) != len(set(chosen)) or not set(chosen) <= {r["item"] for r in items}:
        raise ValueError("Invalid binary selection")
    cost = sum(r["cost"] for r in items if r["item"] in chosen)
    benefit = sum(r["benefit"] for r in items if r["item"] in chosen)
    if cost > budget:
        raise ValueError("Infeasible solution")
    return {"selected": chosen, "cost": cost, "benefit": benefit,
            "budget": budget, "feasible": True, "budget_slack": budget - cost}


def exact(items, budget):
    best, evaluated = None, 0
    for bits in product([0, 1], repeat=len(items)):
        evaluated += 1
        if sum(r["cost"] * b for r, b in zip(items, bits)) > budget:
            continue
        candidate = summarize(items, [r["item"] for r, b in zip(items, bits) if b], budget)
        if best is None or candidate["benefit"] > best["benefit"]:
            best = candidate
    best.update({"subsets_evaluated": evaluated, "all_subsets": 2 ** len(items),
                 "status": "optimal_by_complete_enumeration", "upper_bound": best["benefit"]})
    return best


def greedy(items, budget):
    remaining, chosen = budget, []
    for r in sorted(items, key=lambda r: (-Fraction(r["benefit"], r["cost"]), r["item"])):
        if r["cost"] <= remaining:
            chosen.append(r["item"])
            remaining -= r["cost"]
    result = summarize(items, chosen, budget)
    result["status"] = "feasible_heuristic"
    return result


def main():
    items, config = read_inputs()
    optimum, baseline = exact(items, config["budget"]), greedy(items, config["budget"])
    metrics = {"data_status": config["data_status"], "deterministic": True,
               "recorded_seed": int(os.environ.get("MODELING_SEED", "0")),
               "seed_note": "No random operation in this deterministic solver",
               "exact": optimum, "greedy": baseline,
               "benefit_gain": optimum["benefit"] - baseline["benefit"],
               "relative_gain_percent": 100 * (optimum["benefit"] - baseline["benefit"]) / baseline["benefit"]
                                        if baseline["benefit"] else None}
    dest = Path("results/demo-01")
    dest.mkdir(parents=True, exist_ok=True)
    with (dest / "sensitivity.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["budget", "method", "benefit", "cost"])
        writer.writeheader()
        for budget in sorted(set(config["sensitivity_budgets"])):
            for name, solver in [("Exact", exact), ("Greedy", greedy)]:
                result = solver(items, budget)
                writer.writerow({"budget": budget, "method": name,
                                 "benefit": result["benefit"], "cost": result["cost"]})
    with (dest / "metrics.json").open("x", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
