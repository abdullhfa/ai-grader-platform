"""
Synthetic PNG/MP4 fixtures → build_project_profile + evidence_layer + OCR snapshot.

Usage (repo root):
  python -m app.calibration.mini_validation_ocr.run_mini_validation_ocr

Requires: Pillow; pytesseract + Tesseract on PATH for real OCR. Observation-only.
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


def _write_text_png(path: Path, text: str, size: tuple[int, int] = (360, 120)) -> None:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", size, (28, 28, 40))
    dr = ImageDraw.Draw(im)
    dr.text((16, 40), text, fill=(255, 255, 255))
    im.save(path, format="PNG")


def _write_blank_png(path: Path) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 100), (10, 10, 10)).save(path, format="PNG")


def _write_noise_png(path: Path) -> None:
    try:
        import numpy as np
    except ImportError:
        _write_blank_png(path)
        return
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(42)
    arr = rng.randint(0, 256, (120, 200, 3), dtype=np.uint8)
    Image.fromarray(arr).save(path, format="PNG")


def _prepare_case(case_dir: Path, cid: str) -> None:
    g = case_dir / "gameplay"
    if cid == "case_a_frame_ui_score":
        _write_text_png(g / "hud_score.png", "Score: 100")
    elif cid == "case_b_blank_frame":
        _write_blank_png(g / "blank_screen.png")
    elif cid == "case_c_noisy_frame":
        _write_noise_png(g / "noise.png")
    elif cid == "case_d_ocr_no_logs":
        _write_text_png(g / "note.png", "Qwfp Zxcv Asdf", size=(320, 100))
        _ensure_case_video(case_dir, "clip.mp4", 8)
    elif cid == "case_e_ocr_log_screenshot_window":
        _write_text_png(g / "capture_1s.png", "Health: 99  Score: 5")
        log = g / "runtime.log"
        g.mkdir(parents=True, exist_ok=True)
        log.write_text("t=0.8 OnCollisionEnter demo\n", encoding="utf-8")
        _ensure_case_video(case_dir, "gameplay.mp4", 10)
        for stale in g.glob("*.png"):
            if stale.name != "capture_1s.png":
                try:
                    stale.unlink()
                except OSError:
                    pass


def _collect_files(case_dir: Path) -> List[str]:
    return [str(p.resolve()) for p in sorted(case_dir.rglob("*")) if p.is_file()]


def _compact(profile: Dict[str, Any], evidence_layer: Dict[str, Any]) -> Dict[str, Any]:
    rt = profile.get("runtime_evidence") or {}
    ta = evidence_layer.get("temporal_alignment") or {}
    ocr_items = [x for x in (rt.get("ocr_evidence_items") or []) if isinstance(x, dict)]
    return {
        "ocr": {
            "extractor_version": rt.get("ocr_extractor_version"),
            "item_count": len(ocr_items),
            "presence_flags": rt.get("ocr_presence_flags") or [],
            "noise_flags": rt.get("ocr_noise_flags") or [],
            "sample_raw": [(x.get("source"), (x.get("raw_text") or "")[:80]) for x in ocr_items[:3]],
        },
        "temporal_groups_head": (ta.get("temporal_groups") or [])[:4],
        "temporal_reasoning": (ta.get("temporal_reasoning") or {}).get("reasoning") or [],
        "runtime_counts": {
            "screenshots": len((rt.get("screenshot_candidates") or [])),
            "logs": len((rt.get("log_files") or [])),
            "video_frames": rt.get("video_frame_count"),
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
        case_dir.mkdir(parents=True, exist_ok=True)
        _prepare_case(case_dir, cid)
        paths = _collect_files(case_dir)
        profile = build_project_profile(paths)
        el = build_evidence_layer_from_profile(profile)
        snap = _compact(profile, el)
        cases_out.append({**entry, "actual_behavior": json.dumps(snap, ensure_ascii=False, indent=2)})

    return {
        "run_purpose": template.get("run_purpose", ""),
        "cases": cases_out,
        "note": "If Tesseract missing, expect ocr_engine_unavailable noise flags.",
    }


def main() -> None:
    out = run_all()
    root = Path(__file__).resolve().parent
    out_path = root / "mini_validation_ocr_last_run.json"
    if out_path.is_file():
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        prev_by_id = {c.get("case_id"): c for c in (prev.get("cases") or [])}
        for c in out["cases"]:
            pid = c.get("case_id")
            old = prev_by_id.get(pid) if isinstance(prev_by_id, dict) else None
            if isinstance(old, dict):
                for key in ("observed_friction", "unexpected_result", "ocr_observation_notes"):
                    if old.get(key):
                        c[key] = old[key]
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
