"""Small, dependency-free helpers for local modeling evidence tools."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import math
import re
import tempfile


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path):
    def reject(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=reject)
    def check(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite JSON number")
        if isinstance(value, dict):
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(data)
    return data


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=path.name + ".",
                                         suffix=".tmp", encoding="utf-8", newline="\n", delete=False) as handle:
            temp = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def safe_path(root, relative):
    """Evidence paths must be relative and remain inside the project after resolve."""
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError(f"Expected nonempty project-relative path: {relative!r}")
    # Reject Windows drive/UNC syntax even if this skill runs on POSIX.
    if re.match(r"^[A-Za-z]:", relative) or relative.startswith(("\\", "/")):
        raise ValueError(f"Absolute path is not allowed: {relative!r}")
    path = (root / relative.replace("\\", "/")).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError(f"Path leaves project: {relative!r}")
    return path


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise ValueError("ID must contain 1–80 ASCII letters, numbers, '_' or '-'.")
    return value


def fingerprint(root, relative):
    path = safe_path(root, relative)
    if not path.is_file():
        raise ValueError(f"Missing file: {relative}")
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": path.relative_to(Path(root).resolve()).as_posix(),
            "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def finite_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def metric_value(data, dotted_key):
    if not isinstance(dotted_key, str) or not dotted_key:
        raise ValueError("Metric key is required")
    for key in dotted_key.split("."):
        if not isinstance(data, dict) or key not in data:
            raise ValueError(f"Unknown metric: {dotted_key}")
        data = data[key]
    if not finite_number(data):
        raise ValueError(f"Metric must be a finite number: {dotted_key}")
    return data
