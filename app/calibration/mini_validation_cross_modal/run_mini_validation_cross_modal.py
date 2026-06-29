"""
Build cross-modal observation fixtures and snapshot cross_modal_corroboration.

Usage (repo root):
  python -m app.calibration.mini_validation_cross_modal.run_mini_validation_cross_modal
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


def _write_text_png(path: Path, text: str) -> None:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (360, 100), (22, 22, 30))
    dr = ImageDraw.Draw(im)
    dr.text((12, 36), text, fill=(255, 255, 240))
    im.save(path, format="PNG")


def _collect_files(case_dir: Path) -> List[str]:
    return [str(p.resolve()) for p in sorted(case_dir.rglob("*")) if p.is_file()]


def _write_blank_png(path: Path, w: int = 200, h: int = 100) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), (14, 14, 14)).save(path, format="PNG")


def _prepare_case(case_dir: Path, cid: str) -> None:
    g = case_dir / "gameplay"
    g.mkdir(parents=True, exist_ok=True)
    if cid == "case_a_log_ocr_frame_window":
        _write_synthetic_mp4(g / "gameplay.mp4", 10, cid)
        _write_text_png(g / "capture_1s.png", "Score: 10  Health: 100")
        (g / "runtime.log").write_text("t=0.75 OnCollisionEnter ok\n", encoding="utf-8")
    elif cid == "case_b_screenshot_only_weak":
        _write_text_png(g / "hud_only.png", "Menu — Pause")
    elif cid == "case_c_video_only":
        _write_synthetic_mp4(g / "clip.mp4", 12, cid)
    elif cid == "case_d_logs_only":
        (g / "runtime.log").write_text(
            "t=1.0 line\n" "t=10.0 OnCollisionEnter x\n" "t=25.0 OnCollisionEnter y\n",
            encoding="utf-8",
        )
    elif cid == "case_e_modalities_split_windows":
        _write_synthetic_mp4(g / "gameplay.mp4", 8, cid)
        _write_blank_png(g / "hud_8000s.png", 220, 90)
        (g / "runtime.log").write_text("t=9999.0 OnCollisionEnter far\n", encoding="utf-8")


def _compact(el: Dict[str, Any]) -> Dict[str, Any]:
    cm = el.get("cross_modal_corroboration") or {}
    return {
        "cross_modal_windows": cm.get("cross_modal_windows") or [],
        "cross_modal_reasoning": cm.get("cross_modal_reasoning") or {},
        "cross_modal_noise_flags": cm.get("cross_modal_noise_flags") or [],
        "cross_modal_diversity_score": cm.get("cross_modal_diversity_score"),
        "runtime_corroboration_reference": cm.get("runtime_corroboration_reference") or {},
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
        prof = build_project_profile(paths)
        el = build_evidence_layer_from_profile(prof)
        snap = _compact(el)
        cases_out.append({**entry, "actual_behavior": json.dumps(snap, ensure_ascii=False, indent=2)})

    return {
        "run_purpose": template.get("run_purpose", ""),
        "cases": cases_out,
        "note": "Cross-modal is observation-only; does not affect achieved.",
    }


def main() -> None:
    out = run_all()
    root = Path(__file__).resolve().parent
    out_path = root / "mini_validation_cross_modal_last_run.json"
    if out_path.is_file():
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        prev_by_id = {c.get("case_id"): c for c in (prev.get("cases") or [])}
        for c in out["cases"]:
            pid = c.get("case_id")
            old = prev_by_id.get(pid) if isinstance(prev_by_id, dict) else None
            if isinstance(old, dict):
                for key in ("observed_friction", "unexpected_result", "cross_modal_notes"):
                    if old.get(key):
                        c[key] = old[key]
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
