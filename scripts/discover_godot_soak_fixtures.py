"""Discover Godot student exe for soak fixture #2 (strategy C)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = Path(__file__).resolve().parent / "godot_soak_fixtures.json"
STUDENTS = ROOT / "uploads" / "students"
SKIP_NAME_PARTS = ("connection", "network", "server")


def _is_godot_folder(folder: Path) -> bool:
    if any(folder.rglob("*.gd")):
        return True
    if any(folder.rglob("project.godot")):
        return True
    return False


def discover_student_exe() -> Path | None:
    if not STUDENTS.is_dir():
        return None
    candidates: list[tuple[int, Path]] = []
    for exe in STUDENTS.rglob("*.exe"):
        low = str(exe).lower()
        if any(s in low for s in SKIP_NAME_PARTS):
            continue
        folder = exe.parent
        score = 0
        if _is_godot_folder(folder):
            score += 10
        if "p_03" in exe.name.lower():
            score += 1
        candidates.append((score, exe))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (-t[0], str(t[1])))
    best = candidates[0][1]
    submission_50_exe = STUDENTS / "bx72" / "Ahmad Bakr Hatem Abu Shaira TF(77644)  هدف (ب+ج)" / "P_03.exe"
    if best.resolve() == submission_50_exe.resolve() and len(candidates) > 1:
        return candidates[1][1]
    if best.resolve() == submission_50_exe.resolve():
        return None
    return best


def main() -> None:
    data = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    found = discover_student_exe()
    for fx in data.get("fixtures") or []:
        if fx.get("id") != "student_godot_2":
            continue
        if found and found.is_file():
            fx["path"] = str(found.relative_to(ROOT)).replace("\\", "/")
            fx["pending"] = False
            fx["notes"] = f"Discovered: {found.name}"
        else:
            fx["path"] = None
            fx["pending"] = True
            fx["notes"] = "No second student Godot exe on disk — DoD B blocked until upload"
    FIXTURES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if found:
        print(f"\nDiscovered student_godot_2: {found}")
    else:
        print("\nNo second student Godot exe found (submission 50 excluded).")
        sys.exit(0)


if __name__ == "__main__":
    main()
