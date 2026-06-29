"""Audit batch grades against full.rar submission artifacts."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import PurePosixPath

import rarfile

from app.btec_grade_resolution import determine_grade_level
from app.database import SessionLocal
from app import models

RAR_PATH = r"d:\تجربة\GAME B&C\full.rar"

# Map DB student_name prefix -> RAR top folder (when names differ slightly)
FOLDER_ALIASES = {
    "abd": "العاب عبدارحمن بني مصطفى",
    "أيهم": "ايهم عتوم العاب",
    "محمد عبد المعطي": "تطوير الالعاب محمد عبد المعطي نوفل",
    "محمد قاسم": "تطوير الالعاب محمد قاسم نوفل",
    "حذيفه": "حذيفة صبيحي العاب",
}

DOC_EXT = {".doc", ".docx", ".pdf", ".odt", ".rtf"}
CODE_EXT = {".gd", ".gml", ".cs", ".py", ".java", ".cpp", ".js", ".ts", ".lua"}
EXEC_EXT = {".exe", ".apk", ".pck", ".zip", ".html", ".htm"}
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def match_folder(student_name: str, tops: set[str]) -> str | None:
    name = student_name.strip()
    if name in tops:
        return name
    for key, folder in FOLDER_ALIASES.items():
        if key.lower() in _norm(name) and folder in tops:
            return folder
    # fuzzy: first 12 chars overlap
    n = _norm(name)
    for t in tops:
        tn = _norm(t)
        if n[:15] in tn or tn[:15] in n:
            return t
    return None


def build_rar_index(rf: rarfile.RarFile) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for info in rf.infolist():
        if not info.filename.startswith("full/"):
            continue
        rel = info.filename[5:]
        if not rel or rel.endswith("/"):
            continue
        folder = rel.split("/")[0]
        index[folder].append(rel)
    return index


def scan_rar_folder(files: list[str]) -> dict:
    stats: Counter = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    for rel in files:
        if not rel or rel.endswith("/"):
            continue
        ext = PurePosixPath(rel).suffix.lower()
        stats[ext or "(noext)"] += 1
        key = ext or "(noext)"
        if len(samples[key]) < 3:
            samples[key].append(rel.split("/")[-1])
    flags = {
        "has_doc": sum(stats[e] for e in stats if e in DOC_EXT),
        "has_code": sum(stats[e] for e in stats if e in CODE_EXT),
        "has_exe": sum(stats[e] for e in stats if e in EXEC_EXT),
        "has_video": sum(stats[e] for e in stats if e in VIDEO_EXT),
        "has_images": sum(stats[e] for e in stats if e in IMAGE_EXT),
        "total_files": sum(stats.values()),
        "top_exts": stats.most_common(8),
    }
    return {"flags": flags, "samples": dict(samples)}


def short_level(lv: str) -> str:
    lv = (lv or "").strip().upper()
    return lv.split(".")[-1] if "." in lv else lv


def audit_submission(snap: dict) -> dict:
    crit = snap.get("criteria_results") or []
    achieved = [short_level(r.get("criteria_level", "")) for r in crit if r.get("achieved")]
    failed = [
        (
            r.get("criteria_level"),
            r.get("verdict_status"),
            (r.get("feedback") or r.get("reasoning") or "")[:120],
        )
        for r in crit
        if not r.get("achieved")
    ]
    inv = snap.get("artifact_inventory") or {}
    return {
        "grade": snap.get("grade_level"),
        "pct": snap.get("percentage"),
        "achieved": achieved,
        "failed": failed,
        "achieved_n": len(achieved),
        "total_n": len(crit),
        "computed_grade": determine_grade_level(crit),
        "has_doc": bool((inv.get("documentation") or {}).get("files")),
        "has_code": bool((inv.get("source_code") or {}).get("files")) or inv.get("has_source_code_artifacts"),
        "has_exe": bool((inv.get("executable_artifacts") or {}).get("files")),
        "vision_images": int((snap.get("visual_evidence_summary") or {}).get("images_analyzed") or 0),
    }


def main() -> None:
    batch_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    rf = rarfile.RarFile(RAR_PATH)
    rar_index = build_rar_index(rf)
    tops = set(rar_index.keys())

    db = SessionLocal()
    subs = (
        db.query(models.Submission)
        .filter(models.Submission.batch_id == batch_id)
        .order_by(models.Submission.id)
        .all()
    )

    print(f"# Audit batch {batch_id} — {len(subs)} students\n")
    for s in subs:
        gs = (
            db.query(models.GradingSummary)
            .filter(models.GradingSummary.submission_id == s.id)
            .first()
        )
        snap = json.loads(s.grading_snapshot_json) if s.grading_snapshot_json else {}
        audit = audit_submission(snap)
        folder = match_folder(s.student_name, tops)
        rar = scan_rar_folder(rar_index[folder]) if folder and folder in rar_index else None

        print("=" * 90)
        print(f"## {s.id}. {s.student_name}")
        print(f"   Grade: {gs.grade_level if gs else '?'} | {gs.percentage if gs else '?'}% | computed={audit['computed_grade']}")
        print(f"   Criteria: {audit['achieved_n']}/{audit['total_n']} achieved → {', '.join(audit['achieved'])}")
        if folder and rar:
            f = rar["flags"]
            print(f"   RAR folder: {folder}")
            print(
                f"   Artifacts: files={f['total_files']} doc={f['has_doc']} code={f['has_code']} "
                f"exe={f['has_exe']} video={f['has_video']} images={f['has_images']}"
            )
            print(f"   Top types: {f['top_exts']}")
        else:
            print("   RAR folder: NOT MATCHED")

        print(f"   Snapshot inventory: doc={audit['has_doc']} code={audit['has_code']} exe={audit['has_exe']} vision={audit['vision_images']}")
        print("   FAILED criteria:")
        for lv, vs, fb in audit["failed"]:
            print(f"     - {lv} [{vs}]: {fb}")

        # Verdict
        if audit["computed_grade"] != (gs.grade_level or "U")[0]:
            print("   ⚠ GRADE MISMATCH: summary vs criteria recompute")
        elif audit["achieved_n"] >= 7 and audit["computed_grade"] == "U":
            print("   ⚠ REVIEW: high achievement count but U (likely P5/P6 runtime gates)")
        elif audit["achieved_n"] <= 3:
            print("   ✓ U appears justified (very low achievement)")
        elif audit["achieved_n"] <= 5:
            print("   ✓ U appears justified (major gaps)")
        else:
            print("   ? U with strong static evidence — verify P5/P6 failures are real")
        print()

    db.close()


if __name__ == "__main__":
    main()
