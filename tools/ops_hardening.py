#!/usr/bin/env python3
"""Operational hardening — temp cleanup, stale sessions, health sweep."""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNTIME_SESSIONS = ROOT / "uploads" / "runtime_sessions"
TEMP_DIRS = [ROOT / "uploads" / "tmp", ROOT / "uploads" / "sandbox_temp"]


def cleanup_stale_runtime_sessions(*, max_age_hours: int = 72, dry_run: bool = False) -> dict:
    """Remove runtime session workspaces older than max_age_hours."""
    removed = 0
    freed_bytes = 0
    if not RUNTIME_SESSIONS.is_dir():
        return {"removed": 0, "freed_bytes": 0}

    cutoff = time.time() - (max_age_hours * 3600)
    for submission_dir in RUNTIME_SESSIONS.iterdir():
        if not submission_dir.is_dir():
            continue
        for session_dir in submission_dir.iterdir():
            if not session_dir.is_dir():
                continue
            try:
                mtime = session_dir.stat().st_mtime
            except OSError:
                continue
            if mtime >= cutoff:
                continue
            size = sum(f.stat().st_size for f in session_dir.rglob("*") if f.is_file())
            if not dry_run:
                shutil.rmtree(session_dir, ignore_errors=True)
            removed += 1
            freed_bytes += size
    return {"removed": removed, "freed_bytes": freed_bytes, "max_age_hours": max_age_hours}


def cleanup_temp_dirs(*, dry_run: bool = False) -> dict:
    removed = 0
    for td in TEMP_DIRS:
        if not td.is_dir():
            continue
        for child in td.iterdir():
            if not dry_run:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            removed += 1
    return {"temp_entries_removed": removed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Operational cleanup for ship mode")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-age-hours", type=int, default=72)
    args = parser.parse_args()

    print("Operational hardening sweep\n")
    sessions = cleanup_stale_runtime_sessions(max_age_hours=args.max_age_hours, dry_run=args.dry_run)
    temps = cleanup_temp_dirs(dry_run=args.dry_run)
    print(f"Sessions removed: {sessions['removed']} ({sessions['freed_bytes']} bytes)")
    print(f"Temp entries removed: {temps['temp_entries_removed']}")
    if args.dry_run:
        print("(dry-run — no files deleted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
