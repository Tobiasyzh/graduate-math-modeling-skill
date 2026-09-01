"""Plot an actual CSV as SVG/PNG with explicit axes and source provenance.

Requires matplotlib. Source CSV is read locally and is never uploaded.
"""
from pathlib import Path
from hashlib import sha256
import argparse
import csv
import json
import io
import math
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="New output prefix, without extension")
    parser.add_argument("--kind", choices=["line", "scatter", "bar"], required=True)
    parser.add_argument("--x", required=True)
    parser.add_argument("--y", required=True)
    parser.add_argument("--group")
    parser.add_argument("--error")
    parser.add_argument("--error-label")
    parser.add_argument("--xlabel", required=True)
    parser.add_argument("--ylabel", required=True)
    args = parser.parse_args()
    if args.error and not args.error_label:
        parser.error("Explain error bars with --error-label (SD, SE, CI half-width, etc.)")
    targets = [Path(str(args.out) + ext) for ext in [".svg", ".png", ".source.json"]]
    if any(p.exists() for p in targets):
        parser.error("Output exists; use a new prefix")
    source_bytes = args.input.read_bytes()
    with io.StringIO(source_bytes.decode("utf-8-sig"), newline="") as handle:
        reader = csv.DictReader(handle)
        required = [v for v in [args.x, args.y, args.group, args.error] if v]
        if any(c not in (reader.fieldnames or []) for c in required):
            parser.error(f"CSV must contain columns: {required}")
        rows = list(reader)
    if not rows:
        parser.error("No data rows")
    groups = {}
    for row in rows:
        key = row[args.group] if args.group else args.y
        groups.setdefault(key, []).append(row)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        parser.error("matplotlib is not installed in this Python; use an available plotting environment")
    plt.rcParams.update({"font.size": 10, "svg.fonttype": "none", "pdf.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]})
    colors = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#333333"]
    fig, ax = plt.subplots(figsize=(6.4, 4.0), layout="constrained")
    categories = list(dict.fromkeys(row[args.x] for row in rows)) if args.kind == "bar" else []
    for i, (label, records) in enumerate(groups.items()):
        ys = [float(r[args.y]) for r in records]
        es = [float(r[args.error]) for r in records] if args.error else None
        if not all(math.isfinite(v) for v in ys + (es or [])) or (es and min(es) < 0):
            parser.error("Y/error values must be finite; errors must be nonnegative")
        color = colors[i % len(colors)]
        if args.kind == "bar":
            names = [r[args.x] for r in records]
            if len(set(names)) != len(names):
                parser.error("Duplicate categories in a series: aggregate explicitly before plotting")
            width = 0.8 / len(groups)
            xs = [categories.index(r[args.x]) - 0.4 + width / 2 + i * width for r in records]
            ax.bar(xs, ys, width=width, label=label, color=color, yerr=es, capsize=3 if es else 0)
        else:
            xs = [float(r[args.x]) for r in records]
            if not all(math.isfinite(v) for v in xs):
                parser.error("X values must be finite")
            if args.kind == "line" and any(b < a for a, b in zip(xs, xs[1:])):
                parser.error("Line X must be ordered within each series; order the CSV explicitly")
            line_styles = ["-o", "--s", "-.^", ":D", "-v", "--P", "-.X"]
            ax.errorbar(xs, ys, yerr=es, fmt=line_styles[i % len(line_styles)] if args.kind == "line" else "o",
                        markerfacecolor="white", markeredgewidth=1,
                        markersize=4, linewidth=1.5, label=label, color=color, capsize=3 if es else 0)
    if args.kind == "bar":
        ax.set_xticks(range(len(categories)), categories)
        ax.axhline(0, color="#666666", linewidth=0.6)
    ax.set(xlabel=args.xlabel, ylabel=args.ylabel)
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)
    if args.group:
        ax.legend(frameon=False)
    if args.error_label:
        ax.set_title("Error bars: " + args.error_label, fontsize=9)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(targets[0])
    fig.savefig(targets[1], dpi=300)
    plt.close(fig)
    source = {"input": str(args.input.resolve()), "sha256": sha256(source_bytes).hexdigest(),
              "rows": len(rows), "kind": args.kind, "x": args.x, "y": args.y,
              "group": args.group, "error": args.error, "error_label": args.error_label,
              "xlabel": args.xlabel, "ylabel": args.ylabel,
              "note": "Actual CSV values plotted; visual inspection of exported image still required."}
    targets[2].write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
    for path in targets:
        print(path.resolve())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
