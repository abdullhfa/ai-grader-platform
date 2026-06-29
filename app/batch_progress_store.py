"""Persist in-memory batch progress so UI survives server restarts."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

_PROGRESS_DIR = (
    Path(os.getenv("BATCH_PROGRESS_DIR", "uploads/runtime/batch_progress"))
    .resolve()
)


def _path_for_assignment(assignment_id: int) -> Path:
    _PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    return _PROGRESS_DIR / f"assignment_{assignment_id}.json"


def persist_assignment_progress(assignment_id: int, info: Dict[str, Any]) -> None:
    if not isinstance(assignment_id, int) or not isinstance(info, dict):
        return
    try:
        payload = json.loads(json.dumps(info, ensure_ascii=False, default=str))
        dest = _path_for_assignment(assignment_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        for attempt in range(3):
            try:
                os.replace(str(tmp), str(dest))
                return
            except OSError:
                if dest.is_file():
                    try:
                        dest.unlink()
                    except OSError:
                        pass
                if attempt < 2:
                    time.sleep(0.05 * (attempt + 1))
                else:
                    raise
    except Exception as exc:
        print(f"⚠️ [BATCH-PROGRESS] persist failed assignment={assignment_id}: {exc}")


def load_assignment_progress(assignment_id: int) -> Optional[Dict[str, Any]]:
    path = _path_for_assignment(assignment_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def touch_batch_progress(batch_progress: dict, assignment_id: int) -> None:
    """Persist after in-place dict updates (phase callbacks mutate nested fields)."""
    if not isinstance(batch_progress, dict) or not isinstance(assignment_id, int):
        return
    info = batch_progress.get(assignment_id)
    if isinstance(info, dict):
        persist_assignment_progress(assignment_id, info)


def clear_assignment_progress(assignment_id: int) -> None:
    try:
        _path_for_assignment(assignment_id).unlink(missing_ok=True)
    except Exception:
        pass


def _batch_exists_in_db(db: Any, batch_id: Any) -> bool:
    if batch_id is None:
        return True
    try:
        from app.models import BatchGrading

        return (
            db.query(BatchGrading)
            .filter(BatchGrading.id == int(batch_id))
            .first()
            is not None
        )
    except Exception:
        return False


def sanitize_progress_batch_refs(
    assignment_id: int,
    info: Dict[str, Any],
    db: Any,
) -> Dict[str, Any]:
    """
    Drop stale batch_id / final_response when the DB row was deleted (admin wipe, failed save).
    Prevents UI redirect to /batch-results/{ghost_id}.
    """
    if not isinstance(info, dict):
        return info

    bid = info.get("batch_id")
    fr = info.get("final_response") if isinstance(info.get("final_response"), dict) else None
    fr_bid = fr.get("batch_id") if fr else None

    bid_ok = _batch_exists_in_db(db, bid)
    fr_ok = _batch_exists_in_db(db, fr_bid) if fr_bid is not None else True

    if bid_ok and fr_ok:
        return info

    patched = dict(info)

    if bid_ok and not fr_ok:
        patched.pop("final_response", None)
        if patched.get("finished") and fr:
            patched["finished"] = False
            patched["failed"] = False
            patched["error"] = None
            patched["phase_label"] = patched.get("phase_label") or "جاري التصحيح..."
        persist_assignment_progress(assignment_id, patched)
        return patched

    orphan_id = bid if bid is not None else fr_bid
    if not bid_ok and orphan_id is not None:
        try:
            from app.batch_checkpoint import (
                batch_is_resumable_after_restart,
                ensure_batch_row_from_checkpoint,
                load_batch_checkpoint,
            )

            if batch_is_resumable_after_restart(int(orphan_id)):
                ck = load_batch_checkpoint(int(orphan_id))
                if ck and ensure_batch_row_from_checkpoint(ck, db):
                    patched = dict(info)
                    patched["batch_id"] = int(orphan_id)
                    patched.pop("orphan_batch_id", None)
                    patched.pop("final_response", None)
                    patched["finished"] = False
                    patched["failed"] = False
                    patched["error"] = None
                    patched["resuming"] = True
                    patched["current_phase"] = patched.get("current_phase") or "grading"
                    patched["phase_label"] = (
                        "جاري استئناف التصحيح بعد استعادة سجل الدفعة..."
                    )
                    persist_assignment_progress(assignment_id, patched)
                    return patched
        except Exception as exc:
            print(f"⚠️ [BATCH-PROGRESS] checkpoint recovery failed: {exc}")

    patched = dict(info)
    if orphan_id is not None:
        patched["orphan_batch_id"] = int(orphan_id)
    patched.pop("batch_id", None)
    patched.pop("final_response", None)
    if not bid_ok:
        patched["finished"] = True
        patched["failed"] = True
        patched["error"] = (
            patched.get("error")
            or f"الدفعة #{orphan_id} غير موجودة في قاعدة البيانات — أعد التصحيح PRO."
        )
        patched["phase_label"] = "السجل مفقود — أعد الرفع والتصحيح"
    persist_assignment_progress(assignment_id, patched)
    return patched


def reconcile_orphan_batch_id(
    assignment_id: int,
    info: Dict[str, Any],
    *,
    batch_exists: bool,
) -> Dict[str, Any]:
    """
    Progress JSON may reference a batch_id that was never committed to DB.
    Strip it so the UI does not redirect to /batch-results/{missing}.
    """
    bid = info.get("batch_id")
    if not bid or batch_exists:
        return info
    patched = dict(info)
    patched["orphan_batch_id"] = int(bid)
    patched.pop("batch_id", None)
    patched["finished"] = True
    patched["failed"] = True
    patched["error"] = (
        f"الدفعة #{bid} غير موجودة في قاعدة البيانات — أعد التصحيح."
    )
    patched["phase_label"] = "فشل الحفظ — الدفعة غير موجودة في DB"
    persist_assignment_progress(assignment_id, patched)
    return patched


class BatchProgressDict(dict):
    """dict that mirrors batch progress to disk on each assignment update."""

    def __setitem__(self, key: object, value: object) -> None:
        super().__setitem__(key, value)
        if isinstance(key, int) and isinstance(value, dict):
            persist_assignment_progress(key, value)

    def pop(self, key: object, default: Any = None) -> Any:
        result = super().pop(key, default)
        if isinstance(key, int):
            clear_assignment_progress(key)
        return result


def repair_all_persisted_progress_files() -> int:
    """On server startup: fix progress JSON that references deleted batch rows."""
    if not _PROGRESS_DIR.is_dir():
        return 0
    try:
        from app.database import SessionLocal
    except Exception:
        return 0

    db = SessionLocal()
    repaired = 0
    try:
        for path in _PROGRESS_DIR.glob("assignment_*.json"):
            try:
                aid = int(path.stem.split("_", 1)[1])
            except (IndexError, ValueError):
                continue
            data = load_assignment_progress(aid)
            if not data:
                continue
            cleaned = sanitize_progress_batch_refs(aid, data, db)
            if cleaned != data:
                repaired += 1
    finally:
        db.close()
    if repaired:
        print(f"✅ [BATCH-PROGRESS] repaired {repaired} stale progress file(s)")
    return repaired


def hydrate_batch_progress(batch_progress: dict) -> int:
    """Load saved progress files into the live dict (startup)."""
    from app.grading_mode_policy import normalize_grading_mode_choice

    repair_all_persisted_progress_files()

    if not _PROGRESS_DIR.is_dir():
        return 0
    loaded = 0
    skipped_pro_single = 0
    for path in _PROGRESS_DIR.glob("assignment_*.json"):
        try:
            aid = int(path.stem.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        data = load_assignment_progress(aid)
        if not data or data.get("finished"):
            continue
        mode = normalize_grading_mode_choice(str(data.get("grading_mode") or "deep"))
        total = int(data.get("total") or 0)
        # PRO single-student: do not block new uploads on restart (resume uses checkpoints).
        if mode == "deep" and total <= 1:
            clear_assignment_progress(aid)
            skipped_pro_single += 1
            continue
        batch_progress[aid] = data
        loaded += 1
    if skipped_pro_single:
        print(
            f"✅ [BATCH-PROGRESS] skipped {skipped_pro_single} PRO single-student lock(s) on startup"
        )
    if loaded:
        print(f"✅ [BATCH-PROGRESS] restored {loaded} in-progress assignment(s) from disk")
    return loaded
