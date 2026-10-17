"""Extract the dataset archive into the git-ignored data/raw directory.

The archive is untrusted data: members are only written, never executed, and paths that would escape
the target directory are rejected.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def safe_target(root: Path, member: str) -> Path:
    base = root.resolve()
    target = (base / member).resolve()
    if base not in target.parents:
        raise ValueError(f"unsafe archive member path: {member!r}")
    return target


def extract(archive: Path, dest: Path, skip_prefixes: tuple[str, ...] = ()) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    written = 0
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir() or any(info.filename.startswith(p) for p in skip_prefixes):
                continue
            target = safe_target(dest, info.filename)
            if target.exists() and target.stat().st_size == info.file_size:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                while chunk := src.read(1 << 20):
                    out.write(chunk)
            written += 1
    return written


def find_archive() -> Path:
    candidates = sorted(REPO_ROOT.glob("rakathon-dataset-*.zip"))
    if not candidates:
        raise SystemExit("Dataset archive not found in the repository root")
    return candidates[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=None)
    parser.add_argument("--dest", type=Path, default=REPO_ROOT / "data" / "raw")
    parser.add_argument(
        "--skip-ndjson",
        action="store_true",
        help="skip the very large combined fhir/bundles*.ndjson files (per-patient JSON is enough)",
    )
    args = parser.parse_args()
    archive = args.archive or find_archive()
    skip = ("fhir/bundles",) if args.skip_ndjson else ()
    count = extract(archive, args.dest, skip)
    print(f"extracted {count} files to {args.dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
