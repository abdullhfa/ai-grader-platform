"""
Generate tiny synthetic MP4s per case (if missing) and snapshot temporal_alignment.

Usage (repo root):
  python -m app.calibration.mini_validation_temporal.run_mini_validation_temporal

Observation-only; does not assert pass/fail.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _write_synthetic_mp4(path: Path, n_frames: int, label: str = "") -> bool:
    try:
        import numpy as np
        import cv2
    except ImportError:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, 5.0, (320, 240))
    if not writer.isOpened():
        return False
    try:
        for i in range(max(1, n_frames)):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            v = (i * 17 + hash(label) % 40) % 255
            frame[:, :] = (v, (v + 40) % 255, (v + 80) % 255)
            writer.write(frame)
        return True
    finally:
        writer.release()


def _ensure_case_video(case_dir: Path, basename: str, frames: int) -> Path | None:
    mp4 = case_dir / "gameplay" / basename
    if mp4.is_file() and mp4.stat().st_size > 100:
        return mp4
    if _write_synthetic_mp4(mp4, frames, basename):
        return mp4
    return None


def _ensure_case_e_screenshot(case_dir: Path) -> None:
    gplay = case_dir / "gameplay"
    if gplay.is_dir():
        for stale in gplay.glob("*.png"):
            if stale.name != "capture_1s.png":
                try:
                    stale.unlink()
                except OSError:
                    pass
    shot = case_dir / "gameplay" / "capture_1s.png"
    if shot.is_file() and shot.stat().st_size > 50:
        return
    try:
        import numpy as np
        import cv2
    except ImportError:
        return
    shot.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(shot), np.zeros((8, 8, 3), dtype=np.uint8))


def _collect_files(case_dir: Path) -> List[str]:
    return [str(p.resolve()) for p in sorted(case_dir.rglob("*")) if p.is_file()]


def _compact(profile: Dict[str, Any], evidence_layer: Dict[str, Any]) -> Dict[str, Any]:
    ta = evidence_layer.get("temporal_alignment") or {}
    return {
        "temporal_alignment": {
            "version": ta.get("version"),
            "window_seconds": ta.get("window_seconds"),
            "temporal_alignment_strength": ta.get("temporal_alignment_strength"),
            "temporal_event_count": len(ta.get("temporal_events") or []),
            "temporal_groups": ta.get("temporal_groups") or [],
            "temporal_alignment_conflicts": ta.get("temporal_alignment_conflicts") or [],
            "temporal_reasoning": ta.get("temporal_reasoning") or {},
        },
        "runtime_evidence_counts": {
            "video_frames": (profile.get("runtime_evidence") or {}).get("video_frame_count"),
            "screenshots": len(((profile.get("runtime_evidence") or {}).get("screenshot_candidates") or [])),
            "logs": len(((profile.get("runtime_evidence") or {}).get("log_files") or [])),
        },
    }


def run_all() -> Dict[str, Any]:
    root = Path(__file__).resolve().parent
    template = json.loads((root / "expected_cases.json").read_text(encoding="utf-8"))

    from app.project_intelligence.evidence_schema import build_evidence_layer_from_profile
    from app.project_intelligence.project_profile import build_project_profile

    cases_out: List[Dict[str, Any]] = []
    for entry in template.get("cases") or []:
        cid = str(entry.get("case_id") or "")
        case_dir = root / "cases" / cid
        if not case_dir.is_dir():
            cases_out.append(
                {**entry, "actual_behavior": json.dumps({"error": f"missing {case_dir}"})}
            )
            continue

        err_extra: str | None = None
        if cid in (
            "case_a_frame_log_close",
            "case_b_frame_far_from_log",
            "case_c_video_no_runtime_activity",
            "case_e_frame_screenshot_log_same_window",
        ):
            vp = _ensure_case_video(case_dir, "gameplay.mp4", frames=12)
            if not vp:
                err_extra = "no_mp4_opencv_or_write_failed"
        if cid == "case_e_frame_screenshot_log_same_window":
            _ensure_case_e_screenshot(case_dir)

        paths = _collect_files(case_dir)
        profile = build_project_profile(paths)
        evidence_layer = build_evidence_layer_from_profile(profile)
        snap = _compact(profile, evidence_layer)
        if err_extra:
            snap["fixture_note"] = err_extra
        merged = {**entry, "actual_behavior": json.dumps(snap, ensure_ascii=False, indent=2)}
        cases_out.append(merged)

    return {
        "run_purpose": template.get("run_purpose", ""),
        "cases": cases_out,
        "note": "Human-review temporal_observation_notes; thresholds are fixed (5s window).",
    }


def main() -> None:
    out = run_all()
    root = Path(__file__).resolve().parent
    out_path = root / "mini_validation_temporal_last_run.json"
    if out_path.is_file():
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        prev_by_id = {c.get("case_id"): c for c in (prev.get("cases") or [])}
        for c in out["cases"]:
            pid = c.get("case_id")
            old = prev_by_id.get(pid) if isinstance(prev_by_id, dict) else None
            if isinstance(old, dict):
                for key in ("observed_friction", "unexpected_result", "temporal_observation_notes"):
                    if old.get(key):
                        c[key] = old[key]
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
