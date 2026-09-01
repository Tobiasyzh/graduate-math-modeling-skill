"""Record/check exact file hashes; never upload or claim official acceptance."""
from pathlib import Path
from hashlib import md5, sha256
import argparse
import sys

from common import load_json, safe_path, utc_now, write_json


def hashes(root, relative):
    path = safe_path(root, relative)
    if not path.is_file():
        raise ValueError(f"Missing file: {relative}")
    md5_hash, sha_hash = md5(usedforsecurity=False), sha256()
    with path.open("rb") as handle:
        prefix = handle.read(5)
        if path.suffix.lower() == ".pdf" and prefix != b"%PDF-":
            raise ValueError(f"Not a PDF signature: {relative}")
        md5_hash.update(prefix)
        sha_hash.update(prefix)
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            md5_hash.update(block)
            sha_hash.update(block)
    return {"path": path.relative_to(Path(root).resolve()).as_posix(), "bytes": path.stat().st_size,
            "md5": md5_hash.hexdigest(), "sha256": sha_hash.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--out", default="checks/submission_manifest.json")
    parser.add_argument("--verify", help="Existing project-relative manifest to compare, without changing it")
    args = parser.parse_args()
    root = args.directory.resolve()
    if args.verify:
        if args.file:
            parser.error("Use --verify or --file, not both")
        manifest = load_json(safe_path(root, args.verify))
        if manifest.get("schema_version") != 1 or not manifest.get("files"):
            raise ValueError("Invalid or empty submission manifest")
        changed = []
        for entry in manifest["files"]:
            try:
                actual = hashes(root, entry["path"])
                if any(actual[key] != entry[key] for key in ["md5", "sha256", "bytes"]):
                    changed.append(entry["path"])
            except (OSError, ValueError, KeyError) as exc:
                changed.append(str(exc))
        if changed:
            print("CHANGED/MISSING: " + "; ".join(changed))
            return 1
        print("Exact bytes unchanged. This is not an official submission receipt.")
        return 0
    if not args.file:
        parser.error("Provide one or more --file paths")
    dest = safe_path(root, args.out)
    if dest.exists():
        parser.error("Manifest already exists; never overwrite a frozen manifest")
    files = [hashes(root, name) for name in dict.fromkeys(args.file)]
    write_json(dest, {"schema_version": 1, "created_at": utc_now(), "files": files,
                     "note": "Local exact-file snapshot, not filesystem locking or official submission. Recheck with the prescribed official tool and keep the platform receipt."})
    print(f"Manifest: {dest}")
    for entry in files:
        print(f"{entry['path']}  MD5={entry['md5']}  SHA256={entry['sha256']}")
    print("Files are not write-protected. Verify this manifest immediately before upload.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
