"""Checkpoint + auto-resume batch grading after server restart."""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.batch_progress_store import clear_assignment_progress, persist_assignment_progress
from app.project_intelligence.submission_intake import INTAKE_IGNORE_DIR_NAMES

_CHECKPOINT_DIR = Path(os.getenv("BATCH_CHECKPOINT_DIR", "uploads/runtime/batch_checkpoints"))
STUDENTS_DIR = Path(os.getenv("STUDENTS_DIR", "uploads/students"))


def checkpoint_path(batch_id: int) -> Path:
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return _CHECKPOINT_DIR / f"batch_{batch_id}.json"


def save_batch_checkpoint(batch_id: int, payload: Dict[str, Any]) -> None:
    data = {**payload, "version": 1, "saved_at": time.time()}
    tmp = checkpoint_path(batch_id).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(checkpoint_path(batch_id))


def _checkpoint_paths_for_batch(batch_id: int) -> List[Path]:
    base = checkpoint_path(batch_id)
    paused = base.parent / f"{base.name}.paused"
    paths: List[Path] = []
    if base.is_file():
        paths.append(base)
    if paused.is_file():
        paths.append(paused)
    return paths


def restore_paused_checkpoint_files() -> int:
    """Re-activate checkpoints renamed to *.json.paused during manual ops."""
    if not _CHECKPOINT_DIR.is_dir():
        return 0
    restored = 0
    for paused in _CHECKPOINT_DIR.glob("batch_*.json.paused"):
        active = paused.parent / paused.name.replace(".paused", "")
        if active.is_file():
            continue
        try:
            paused.rename(active)
            restored += 1
        except OSError:
            continue
    if restored:
        print(f"✅ [BATCH-CHECKPOINT] restored {restored} paused checkpoint file(s)")
    return restored


def load_batch_checkpoint(batch_id: int) -> Optional[Dict[str, Any]]:
    for path in _checkpoint_paths_for_batch(batch_id):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("batch_id"):
                return data
        except Exception:
            continue
    return None


def delete_batch_checkpoint(batch_id: int) -> None:
    for path in _checkpoint_paths_for_batch(batch_id):
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
    try:
        checkpoint_path(batch_id).unlink(missing_ok=True)
    except Exception:
        pass


def batch_has_extracted_student_work(batch_id: int) -> bool:
    """True when uploads were already extracted to disk (no re-upload needed)."""
    for root in (STUDENTS_DIR / f"bx{batch_id}", staging_dir_for_batch(batch_id)):
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() not in (".tmp", ".partial"):
                return True
    return False


def batch_is_resumable_after_restart(batch_id: int) -> bool:
    if load_batch_checkpoint(batch_id):
        return True
    if staging_has_files(batch_id):
        return True
    if batch_has_extracted_student_work(batch_id):
        return True
    return False


def _bump_sqlite_autoincrement(db: Any, table_name: str, at_least: int) -> None:
    """Keep SQLite autoincrement above an explicitly inserted primary key."""
    try:
        bind = db.get_bind()
        if bind is None or bind.dialect.name != "sqlite":
            return
        from sqlalchemy import text

        row = db.execute(
            text("SELECT seq FROM sqlite_sequence WHERE name = :name"),
            {"name": table_name},
        ).fetchone()
        current = int(row[0]) if row else 0
        if at_least > current:
            if row:
                db.execute(
                    text("UPDATE sqlite_sequence SET seq = :seq WHERE name = :name"),
                    {"seq": at_least, "name": table_name},
                )
            else:
                db.execute(
                    text("INSERT INTO sqlite_sequence (name, seq) VALUES (:name, :seq)"),
                    {"name": table_name, "seq": at_least},
                )
    except Exception:
        pass


def ensure_batch_row_from_checkpoint(
    checkpoint: Dict[str, Any],
    db: Any,
) -> Optional[Any]:
    """
    Recreate a BatchGrading row when checkpoint / extracted files exist but the DB
    row was wiped (admin delete, partial migration) so resume can continue.
    """
    from app.models import Assignment, BatchGrading, BatchStatus

    batch_id = int(checkpoint.get("batch_id") or 0)
    assignment_id = int(checkpoint.get("assignment_id") or 0)
    if not batch_id or not assignment_id:
        return None

    existing = (
        db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
    )
    if existing is not None:
        return existing

    if not batch_is_resumable_after_restart(batch_id):
        return None

    assignment = (
        db.query(Assignment).filter(Assignment.id == assignment_id).first()
    )
    if assignment is None:
        return None

    student_files = list(checkpoint.get("student_files") or [])
    cached_results = list(checkpoint.get("cached_results") or [])
    total = max(len(student_files) + len(cached_results), 1)

    user_id = int(checkpoint.get("user_id") or 0)
    if not user_id:
        user_id = int(getattr(assignment, "created_by", 0) or 0)
    if not user_id:
        return None

    batch = BatchGrading(
        id=batch_id,
        assignment_id=assignment_id,
        batch_name=str(checkpoint.get("batch_name") or f"Batch {batch_id}"),
        total_students=total,
        processed_students=0,
        status=BatchStatus.PROCESSING,
        created_by=user_id,
    )
    db.add(batch)
    db.flush()
    _bump_sqlite_autoincrement(db, "batch_gradings", batch_id)
    db.commit()
    db.refresh(batch)
    print(
        f"✅ [BATCH-RECOVERY] recreated batch_gradings row id={batch_id} "
        f"assignment={assignment_id} from checkpoint"
    )
    return batch


def list_resumable_checkpoints() -> List[Dict[str, Any]]:
    """Active checkpoints only — *.paused are superseded and must not auto-resume."""
    if not _CHECKPOINT_DIR.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for path in _CHECKPOINT_DIR.glob("batch_*.json"):
        if path.name.endswith(".tmp") or path.name.endswith(".paused"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            bid = int(data.get("batch_id") or 0) if isinstance(data, dict) else 0
            if bid and bid not in seen:
                seen.add(bid)
                out.append(data)
        except Exception:
            continue
    return out


def delete_superseded_checkpoints_for_assignment(
    assignment_id: int,
    *,
    keep_batch_id: int | None = None,
) -> int:
    """Remove old PRO checkpoints when a newer upload replaces them."""
    if not _CHECKPOINT_DIR.is_dir():
        return 0
    removed = 0
    for path in sorted(_CHECKPOINT_DIR.glob("batch_*.json*")):
        if path.name.endswith(".tmp"):
            continue
        try:
            ck = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(ck, dict):
            continue
        if int(ck.get("assignment_id") or 0) != (assignment_id):
            continue
        bid = int(ck.get("batch_id") or 0)
        if keep_batch_id is not None and bid == (keep_batch_id):
            continue
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue
        delete_batch_checkpoint(bid)
    return removed


def staging_dir_for_batch(batch_id: int) -> Path:
    return STUDENTS_DIR / f"batch_{batch_id}_upload"


def staging_has_files(batch_id: int) -> bool:
    root = staging_dir_for_batch(batch_id)
    if not root.is_dir():
        return False
    for p in root.rglob("*"):
        if p.is_file():
            return True
    return False


def clear_staging_for_batch(batch_id: int) -> bool:
    """Remove staged/extracted files so cancelled batches are not auto-resumed."""
    import shutil

    cleared = False
    for root in (staging_dir_for_batch(batch_id), STUDENTS_DIR / f"bx{batch_id}"):
        if not root.is_dir():
            continue
        try:
            shutil.rmtree(root, ignore_errors=True)
            cleared = True
        except Exception:
            pass
    return cleared


def clear_staging_for_assignment(assignment_id: int, db: Any) -> int:
    """Clear staged files for all batches tied to an assignment."""
    from app.models import BatchGrading

    cleared = 0
    batches = (
        db.query(BatchGrading)
        .filter(BatchGrading.assignment_id == assignment_id)
        .order_by(BatchGrading.id.desc())
        .limit(12)
        .all()
    )
    for batch in batches:
        if clear_staging_for_batch(int(batch.id)):
            cleared += 1
    return cleared


async def _extract_staged_zip_or_rar(
    *,
    archive_path: Path,
    batch_id: int,
    grading_mode: str,
    single_student_archive: bool,
) -> tuple[list, list[str], dict[str, list[str]]]:
    """Lightweight archive intake for resume (single-archive uploads)."""
    import asyncio as _asyncio

    from app.archive_extraction_utils import (
        archive_extract_timeout_seconds,
        consolidate_archive_student_results,
        force_single_student_archive_result,
        max_archive_extract_files,
        selective_extract_rar,
        selective_extract_zip,
    )

    extract_dir = STUDENTS_DIR / f"bx{batch_id}"
    extract_dir.mkdir(parents=True, exist_ok=True)
    skip = frozenset(INTAKE_IGNORE_DIR_NAMES)
    _ALL_EXTENSIONS = (
        ".docx", ".pdf", ".doc", ".pptx", ".pptx", ".xlsx", ".xls",
        ".py", ".java", ".cs", ".cpp", ".c", ".js", ".ts", ".html",
        ".gd", ".gml", ".lua", ".exe", ".pck", ".x86_64", ".apk",
        ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".webm",
        ".png", ".jpg", ".jpeg", ".gif", ".webp",
        ".zip", ".rar",
    )
    ext = archive_path.suffix.lower()
    timeout = archive_extract_timeout_seconds(grading_mode)
    if ext == ".zip":
        extracted, display = await _asyncio.to_thread(
            selective_extract_zip,
            str(archive_path),
            extract_dir,
            skip_dir_names=skip,
            gradable_extensions=_ALL_EXTENSIONS,
            grading_mode=grading_mode,
            max_extract_files=max_archive_extract_files(grading_mode),
        )
    elif ext == ".rar":
        extracted, display = await _asyncio.to_thread(
            selective_extract_rar,
            str(archive_path),
            extract_dir,
            skip_dir_names=skip,
            gradable_extensions=_ALL_EXTENSIONS,
            grading_mode=grading_mode,
            max_extract_files=max_archive_extract_files(grading_mode),
        )
    else:
        return [], [], {}

    if not extracted:
        return [], display, {}

    from app.archive_extraction_utils import materialize_nested_zip_game_executables

    nested_runtime = materialize_nested_zip_game_executables(
        extract_dir, grading_mode=grading_mode
    )
    for rel_key, disk in nested_runtime:
        extracted.append((rel_key, disk))
        display.append(rel_key)

    rows: list = []
    tops: set[str] = set()
    for arc_path, disk in extracted:
        parts = Path(arc_path.replace("\\", "/")).parts
        if len(parts) == 1:
            rows.append((Path(arc_path).stem, disk, [disk], [arc_path]))
        else:
            tops.add(parts[0])
    if tops:
        folder_files: dict[str, list] = {}
        for arc_path, disk in extracted:
            parts = Path(arc_path.replace("\\", "/")).parts
            key = parts[0] if len(parts) >= 2 else "__root__"
            folder_files.setdefault(key, []).append((key, disk, arc_path))
        for folder_name, files_in_folder in folder_files.items():
            if folder_name == "__root__":
                continue
            best_path = str(files_in_folder[0][1])
            rows.append((
                folder_name,
                best_path,
                [str(x[1]) for x in files_in_folder],
                [str(x[2]) for x in files_in_folder],
            ))

    archive_files = consolidate_archive_student_results(rows)
    if single_student_archive and len(archive_files) > 1:
        archive_files = force_single_student_archive_result(
            archive_files, archive_name=archive_path.name
        )
        merged_name = str(archive_files[0][0]) if archive_files else ""
        student_map = {merged_name: [Path(p).name for p in display]} if merged_name else {}
    else:
        student_map = {}
        for entry in archive_files:
            name = str(entry[0])
            student_map.setdefault(name, [Path(p).name for p in display[:20]])

    _ = timeout  # reserved for outer wait_for wrapper
    return archive_files, display, student_map


async def resume_batch_from_checkpoint(
    checkpoint: Dict[str, Any],
    batch_progress: dict,
) -> bool:
    from app.database import SessionLocal
    from app.models import Assignment, BatchGrading, BatchStatus, GradingCriteria

    batch_id = int(checkpoint["batch_id"])
    assignment_id = int(checkpoint["assignment_id"])
    stage = str(checkpoint.get("stage") or "grading")

    db = SessionLocal()
    try:
        batch = db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
        if not batch:
            batch = ensure_batch_row_from_checkpoint(checkpoint, db)
        if not batch:
            delete_batch_checkpoint(batch_id)
            return False
        status = batch.status.value if hasattr(batch.status, "value") else str(batch.status)
        if status not in (BatchStatus.PROCESSING.value, BatchStatus.PENDING.value):
            if status == BatchStatus.FAILED.value and batch_is_resumable_after_restart(
                batch_id
            ):
                batch.status = BatchStatus.PROCESSING  # type: ignore[assignment]
                batch.failure_message = None  # type: ignore[assignment]
                db.commit()
            else:
                delete_batch_checkpoint(batch_id)
                return False

        assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
        if not assignment:
            return False

        criteria_rows = (
            db.query(GradingCriteria)
            .filter(GradingCriteria.assignment_id == assignment_id)
            .all()
        )
        grading_criteria = []
        for c in criteria_rows:
            kp_raw = c.key_points
            try:
                key_points = json.loads(str(kp_raw)) if kp_raw else []
            except Exception:
                key_points = []
            grading_criteria.append(
                {
                    "criteria_level": c.criteria_level,
                    "criteria_name": c.criteria_name,
                    "criteria_description": c.criteria_description,
                    "key_points": key_points,
                }
            )
        reference_solution = json.loads(str(assignment.reference_solution_json))

        student_files: List[Dict[str, Any]] = list(checkpoint.get("student_files") or [])
        cached_results: List[Dict[str, Any]] = list(checkpoint.get("cached_results") or [])
        accumulated_archive_files = list(checkpoint.get("accumulated_archive_files") or [])
        accumulated_archive_map = dict(checkpoint.get("accumulated_archive_map") or {})

        if stage == "staged":
            staged = list(checkpoint.get("staged_uploads") or [])
            if not staged and staging_has_files(batch_id):
                root = staging_dir_for_batch(batch_id)
                staged = [
                    {
                        "filename": p.relative_to(root).as_posix(),
                        "path": str(p),
                    }
                    for p in root.rglob("*")
                    if p.is_file()
                ]
            grading_mode = str(checkpoint.get("grading_mode") or "deep")
            single_student = bool(checkpoint.get("single_student_archive"))
            for su in staged:
                file_path = Path(str(su["path"]))
                if not file_path.is_file():
                    continue
                ext = file_path.suffix.lower()
                if ext in (".zip", ".rar"):
                    archive_files, display, amap = await _extract_staged_zip_or_rar(
                        archive_path=file_path,
                        batch_id=batch_id,
                        grading_mode=grading_mode,
                        single_student_archive=single_student,
                    )
                    accumulated_archive_files.extend(Path(p).name for p in display[:500])
                    accumulated_archive_map.update(amap)
                    for entry in archive_files:
                        if len(entry) >= 4:
                            sname, epath, spaths, irel = entry
                        elif len(entry) == 3:
                            sname, epath, spaths = entry
                            irel = []
                        else:
                            sname, epath = entry
                            spaths = [str(epath)]
                            irel = []
                        student_files.append({
                            "name": str(sname),
                            "path": str(epath),
                            "email": "",
                            "student_id": "",
                            "has_code_files": False,
                            "submission_paths": list(spaths),
                            "intake_relative_paths": list(irel or []),
                            "source_archive_path": str(file_path),
                        })
                else:
                    student_files.append({
                        "name": Path(str(su.get("filename") or file_path.name)).stem,
                        "path": str(file_path),
                        "email": "",
                        "student_id": "",
                        "has_code_files": False,
                        "submission_paths": [str(file_path)],
                        "intake_relative_paths": [str(su.get("filename") or file_path.name)],
                    })

        if not student_files and not cached_results:
            return False

        try:
            from app.grading_mode_policy import enrich_student_submission_flags

            for sf in student_files:
                if isinstance(sf, dict):
                    enrich_student_submission_flags(sf)
        except Exception:
            pass

        total_to_grade = len(student_files) + len(cached_results)
        all_names = [r.get("student_name", "") for r in cached_results] + [
            s["name"] for s in student_files
        ]
        from app.grading_mode_policy import grading_mode_display_label

        prog = {
            "completed": len(cached_results),
            "total": total_to_grade,
            "batch_id": batch_id,
            "current_student": "",
            "current_phase": "starting",
            "student_progress": 0.0,
            "percent": max(1, round((len(cached_results) / max(total_to_grade, 1)) * 100)),
            "start_time": time.time(),
            "student_times": [],
            "completed_students": [r.get("student_name", "") for r in cached_results],
            "all_student_names": all_names,
            "archive_all_files": accumulated_archive_files,
            "archive_student_map": accumulated_archive_map,
            "upload_intake": checkpoint.get("batch_intake_manifest"),
            "grading_mode": checkpoint.get("grading_mode") or "deep",
            "grading_mode_label": grading_mode_display_label(
                checkpoint.get("grading_mode") or "deep"
            ),
            "finished": False,
            "failed": False,
            "phase_label": "استئناف التصحيح بعد إعادة تشغيل الخادم...",
        }
        batch_progress[assignment_id] = prog
        persist_assignment_progress(assignment_id, prog)

        batch.total_students = int(total_to_grade)  # type: ignore[assignment]
        db.commit()

        selected_criteria_list = list(checkpoint.get("selected_criteria_list") or [])
        if not selected_criteria_list and checkpoint.get("selected_criteria"):
            selected_criteria_list = [
                s.strip()
                for s in str(checkpoint.get("selected_criteria")).split(",")
                if s.strip()
            ]

        from app.batch_grade_worker import schedule_batch_grading_job

        schedule_batch_grading_job(
            batch_progress=batch_progress,
            assignment_id=assignment_id,
            batch_id=batch_id,
            batch_name=str(checkpoint.get("batch_name") or batch.batch_name),
            student_files=student_files,
            cached_results=cached_results,
            grading_criteria=grading_criteria,
            selected_criteria_list=selected_criteria_list,
            reference_solution=reference_solution,
            batch_intake_manifest=dict(checkpoint.get("batch_intake_manifest") or {}),
            user_id=int(checkpoint.get("user_id") or 0),
            subject_bal_id=checkpoint.get("subject_bal_id"),
            sub_id=checkpoint.get("sub_id"),
            grading_mode=str(checkpoint.get("grading_mode") or "deep"),
            skip_grading_cache=bool(checkpoint.get("skip_grading_cache")),
        )
        return True
    except Exception as exc:
        print(f"❌ [BATCH-RESUME] batch={batch_id} failed: {exc}")
        return False
    finally:
        db.close()


async def _resume_checkpoint_task(
    checkpoint: Dict[str, Any],
    batch_progress: dict,
) -> None:
    """Background resume — must not block HTTP server startup."""
    from app.batch_grade_worker import finalize_stale_processing_batch
    from app.database import SessionLocal
    from app.models import BatchGrading, BatchStatus

    batch_id = int(checkpoint.get("batch_id") or 0)
    if not batch_id:
        return
    ok = await resume_batch_from_checkpoint(checkpoint, batch_progress)
    if ok:
        print(
            f"✅ [BATCH-RESUME] scheduled grading resume for batch {batch_id} "
            f"(stage={checkpoint.get('stage')})"
        )
        return
    db = SessionLocal()
    try:
        batch = db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
        if batch:
            st = batch.status.value if hasattr(batch.status, "value") else str(batch.status)
            if st in (BatchStatus.PROCESSING.value, BatchStatus.PENDING.value):
                finalize_stale_processing_batch(
                    batch,
                    message=(
                        "تعذّر استئناف التصحيح بعد إعادة التشغيل. "
                        "أعد رفع الملف واضغط «بدء التصحيح»."
                    ),
                )
                db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
    delete_batch_checkpoint(batch_id)


async def resume_all_checkpoints_on_startup(batch_progress: dict) -> int:
    """Schedule resume for the latest active batch per assignment (never *.paused)."""
    import asyncio

    from app.database import SessionLocal
    from app.models import BatchGrading, BatchStatus

    scheduled = 0
    by_assignment: Dict[int, Dict[str, Any]] = {}
    db = SessionLocal()
    try:
        for ck in list_resumable_checkpoints():
            batch_id = int(ck.get("batch_id") or 0)
            assignment_id = int(ck.get("assignment_id") or 0)
            if not batch_id or not assignment_id:
                continue
            if ck.get("stage") == "staged" and not staging_has_files(batch_id):
                delete_batch_checkpoint(batch_id)
                continue
            batch = db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
            if batch:
                st = (
                    batch.status.value
                    if hasattr(batch.status, "value")
                    else str(batch.status)
                )
                if st in (BatchStatus.FAILED.value, BatchStatus.COMPLETED.value):
                    delete_batch_checkpoint(batch_id)
                    continue
            prev = by_assignment.get(assignment_id)
            if not prev or batch_id > int(prev.get("batch_id") or 0):
                by_assignment[assignment_id] = ck
        for ck in by_assignment.values():
            batch_id = int(ck.get("batch_id") or 0)
            asyncio.create_task(_resume_checkpoint_task(ck, batch_progress))
            scheduled += 1
            print(
                f"📋 [BATCH-RESUME] queued resume for batch {batch_id} "
                f"(stage={ck.get('stage')})"
            )
    finally:
        db.close()
    return scheduled


def pause_pro_single_student_checkpoints_for_assignment(assignment_id: int) -> int:
    """Pause PRO single-student checkpoints so a fresh upload is not blocked."""
    from app.grading_mode_policy import normalize_grading_mode_choice

    if not _CHECKPOINT_DIR.is_dir():
        return 0
    paused = 0
    for path in sorted(_CHECKPOINT_DIR.glob("batch_*.json")):
        if path.name.endswith(".tmp"):
            continue
        try:
            ck = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(ck, dict):
            continue
        if int(ck.get("assignment_id") or 0) != assignment_id:
            continue
        if normalize_grading_mode_choice(str(ck.get("grading_mode") or "deep")) != "deep":
            continue
        students = list(ck.get("student_files") or [])
        cached = list(ck.get("cached_results") or [])
        if not bool(ck.get("single_student_archive")) and len(students) + len(cached) > 1:
            continue
        bid = int(ck.get("batch_id") or 0)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        paused_path = path.parent / f"{path.name}.paused"
        try:
            paused_path.unlink(missing_ok=True)
        except OSError:
            pass
        if bid:
            delete_batch_checkpoint(bid)
        paused += 1
    return paused


def pause_all_checkpoints_for_assignment(assignment_id: int) -> int:
    """Remove checkpoints for an assignment so a fresh upload is not blocked."""
    if not _CHECKPOINT_DIR.is_dir():
        return 0
    paused = 0
    for path in sorted(_CHECKPOINT_DIR.glob("batch_*.json")):
        if path.name.endswith(".tmp"):
            continue
        try:
            ck = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(ck, dict):
            continue
        if int(ck.get("assignment_id") or 0) != assignment_id:
            continue
        bid = int(ck.get("batch_id") or 0)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        if bid:
            delete_batch_checkpoint(bid)
        paused += 1
    return paused


def batch_ids_with_checkpoints() -> set[int]:
    ids = {int(c["batch_id"]) for c in list_resumable_checkpoints() if c.get("batch_id")}
    if _CHECKPOINT_DIR.is_dir():
        for path in _CHECKPOINT_DIR.glob("batch_*.json*"):
            name = path.name
            if name.endswith(".tmp"):
                continue
            try:
                stem = name.split("_", 1)[1].split(".", 1)[0]
                ids.add(int(stem))
            except (IndexError, ValueError):
                continue
    return ids
