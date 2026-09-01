"""Run a reviewed local command and record actual inputs, outputs and exit status.

Use -- before the command. Does not use a shell, download anything, select models,
or verify scientific validity. Each output path must be new for this run.
"""
from pathlib import Path
import argparse
import importlib.metadata
import math
import os
import platform
import subprocess
import sys
import time

from common import fingerprint, load_json, safe_path, utc_now, valid_id, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--output", action="append", default=[], required=True)
    parser.add_argument("--metrics", help="A new JSON output containing actual metrics")
    parser.add_argument("--timeout-sec", type=float)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Supply the reviewed command after --")
    if not 0 <= args.seed <= 4294967295:
        parser.error("Seed must be between 0 and 4294967295")
    if args.timeout_sec is not None and (not math.isfinite(args.timeout_sec) or args.timeout_sec <= 0):
        parser.error("Timeout must be positive")
    root = args.project.resolve()
    load_json(root / "project.json")
    run_dir = safe_path(root, f"runs/{valid_id(args.id)}")
    if run_dir.exists():
        parser.error("Run ID already exists; choose a new ID")
    inputs = [fingerprint(root, p) for p in args.input]
    sources = [fingerprint(root, p) for p in args.source]
    if not sources:
        parser.error("Declare at least one --source file for traceability")
    if args.metrics:
        args.metrics = safe_path(root, args.metrics).relative_to(root).as_posix()
    output_names = list(dict.fromkeys(safe_path(root, p).relative_to(root).as_posix()
                                    for p in args.output + ([args.metrics] if args.metrics else [])))
    outputs = [safe_path(root, p) for p in output_names]
    for path in outputs:
        if path.exists():
            parser.error(f"Output already exists; use a new output path: {path}")
        if path.is_relative_to(run_dir.resolve()):
            parser.error("Experiment outputs must not overwrite the run's own evidence folder")
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True)
    versions = {}
    for name in ["numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "ortools"]:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    record = {"schema_version": 1, "id": args.id, "status": "running", "started_at": utc_now(),
              "command": command, "cwd": str(root), "seed": args.seed,
              "seed_note": "MODELING_SEED and PYTHONHASHSEED passed; model code must use the seed explicitly.",
              "python": sys.version, "platform": platform.platform(),
              "versions_of_recorder_environment": versions,
              "environment_note": "If command uses another runtime, record that runtime and solver versions separately.",
              "inputs": inputs, "sources": sources, "declared_outputs": output_names,
              "outputs": [], "metrics_path": args.metrics, "metrics": {}, "issues": []}
    write_json(run_dir / "run.json", record)
    env = os.environ.copy()
    env.update({"MODELING_SEED": str(args.seed), "PYTHONHASHSEED": str(args.seed), "PYTHONUTF8": "1"})
    start = time.perf_counter()
    with (run_dir / "stdout.log").open("wb") as stdout, (run_dir / "stderr.log").open("wb") as stderr:
        try:
            result = subprocess.run(command, cwd=root, env=env, stdout=stdout, stderr=stderr,
                                    shell=False, timeout=args.timeout_sec, check=False)
            record["exit_code"] = result.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            record["exit_code"] = None
            record["issues"].append(str(exc))
    record.update({"duration_seconds": time.perf_counter() - start, "finished_at": utc_now()})
    for name in output_names:
        try:
            record["outputs"].append(fingerprint(root, name))
        except (OSError, ValueError) as exc:
            record["issues"].append(str(exc))
    if args.metrics:
        try:
            metrics = load_json(safe_path(root, args.metrics))
            if not isinstance(metrics, dict):
                raise ValueError("Metrics JSON must be an object")
            record["metrics"] = metrics
        except (OSError, ValueError) as exc:
            record["issues"].append(str(exc))
    for entry in inputs + sources:
        try:
            if fingerprint(root, entry["path"])["sha256"] != entry["sha256"]:
                record["issues"].append("Input/source changed during run: " + entry["path"])
        except (OSError, ValueError) as exc:
            record["issues"].append(str(exc))
    record["status"] = "completed" if record["exit_code"] == 0 and not record["issues"] else "failed"
    write_json(run_dir / "run.json", record)
    print(f"{record['status']}: {run_dir / 'run.json'}")
    for issue in record["issues"]:
        print(f"- {issue}")
    return 0 if record["status"] == "completed" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
