"""
Inventory and quick-scan BTEC Unit 8 game samples under uploads/تجربة.

Usage:
  python scripts/calibrate_tajriba_samples.py
  python scripts/calibrate_tajriba_samples.py --student "العاب"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo root = parent of scripts/
REPO = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO.parent / "uploads" / "تجربة"


def _scan_folder(folder: Path) -> dict:
    from app.game_engine_signatures import detect_engine_from_text, has_runnable_game_project

    files: list[Path] = [p for p in folder.rglob("*") if p.is_file()]
    rel_paths = [str(p.relative_to(folder)).replace("\\", "/") for p in files]
    joined = "\n".join(rel_paths[:500])

    exts: dict[str, int] = {}
    for p in files:
        ext = p.suffix.lower() or "(noext)"
        exts[ext] = exts.get(ext, 0) + 1

    flags = {
        "scratch": any(p.suffix.lower() in (".sb3", ".sb2") for p in files),
        "godot": any(p.name == "project.godot" for p in files),
        "unity": any(p.suffix.lower() == ".unity" or "assets/" in str(p).lower() for p in files),
        "gamemaker": any(p.suffix.lower() in (".yyp", ".gml", ".yy") for p in files),
        "exe": any(p.suffix.lower() == ".exe" for p in files),
        "word": any(p.suffix.lower() in (".docx", ".doc") for p in files),
        "pdf": any(p.suffix.lower() == ".pdf" for p in files),
        "pptx": any(p.suffix.lower() in (".pptx", ".ppt") for p in files),
    }

    return {
        "path": str(folder),
        "file_count": len(files),
        "top_extensions": dict(sorted(exts.items(), key=lambda x: -x[1])[:10]),
        "engines_detected": detect_engine_from_text(joined),
        "runnable_game": has_runnable_game_project(joined),
        "flags": flags,
        "sample_files": rel_paths[:12],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan uploads/تجربة game unit samples")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--student", type=str, default="", help="Subfolder name filter")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root: Path = args.root
    if not root.is_dir():
        print(f"Not found: {root}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(REPO))

    rows: list[dict] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if args.student and args.student not in entry.name:
            continue
        try:
            rows.append({"name": entry.name, **_scan_folder(entry)})
        except Exception as exc:
            rows.append({"name": entry.name, "error": str(exc)})

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(f"Root: {root}\n")
        for r in rows:
            if r.get("error"):
                print(f"- {r['name']}: ERROR {r['error']}")
                continue
            eng = r.get("engines_detected") or "—"
            fl = r.get("flags") or {}
            tags = [k for k, v in fl.items() if v]
            print(f"- {r['name']}")
            print(f"    files={r['file_count']} engine={eng} tags={', '.join(tags) or '—'}")
            if r.get("sample_files"):
                print(f"    sample: {r['sample_files'][0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
