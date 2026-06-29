"""
Generate tiny synthetic MP4s and run project_profile + evidence_layer.

Usage (repo root):
  python -m app.calibration.mini_validation_video.run_mini_validation_video

Requires OpenCV (or ffmpeg for extraction after write). Observation-only.
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
            # Slight change per frame so encoders do not collapse stream oddly
            v = (i * 17 + hash(label) % 40) % 255
            frame[:, :] = (v, (v + 40) % 255, (v + 80) % 255)
            writer.write(frame)
        return True
    finally:
        writer.release()


def _ensure_case_video(case_dir: Path, basename: str, frames: int) -> Path | None:
    mp4 = case_dir / basename
    if mp4.is_file() and mp4.stat().st_size > 100:
        return mp4
    if _write_synthetic_mp4(mp4, frames, basename):
        return mp4
    return None


def _unity_stub(case_dir: Path, with_collision: bool) -> None:
    ps = case_dir / "ProjectSettings"
    assets = case_dir / "Assets"
    ps.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    (ps / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.0f1\n", encoding="utf-8")
    if with_collision:
        body = "using UnityEngine;\npublic class G : MonoBehaviour { void OnCollisionEnter(Collision c) {}}\n"
    else:
        body = "using UnityEngine;\npublic class G : MonoBehaviour { void Update() {}}\n"
    (assets / "Game.cs").write_text(body, encoding="utf-8")


def _collect_files(case_dir: Path) -> List[str]:
    return [str(p.resolve()) for p in sorted(case_dir.rglob("*")) if p.is_file()]


def _compact(profile: Dict[str, Any], evidence_layer: Dict[str, Any]) -> Dict[str, Any]:
    rt = profile.get("runtime_evidence") or {}
    rc = evidence_layer.get("runtime_corroboration") or {}
    return {
        "video_frame_count": rt.get("video_frame_count"),
        "video_metadata": rt.get("video_metadata"),
        "video_noise_flags": rt.get("video_noise_flags"),
        "video_extraction_errors": rt.get("video_extraction_errors"),
        "corroboration_by_system_sample": {
            k: {
                "modalities": (v or {}).get("corroboration_modalities"),
                "weighted": (v or {}).get("weighted_corroboration_score"),
                "reasoning_tail": ((v or {}).get("corroboration_reasoning") or [])[-4:],
                "noise": (v or {}).get("corroboration_noise_flags"),
            }
            for k, v in (rc.get("by_system") or {}).items()
            if isinstance(v, dict)
        },
        "evidence_video_items": len(
            [i for i in (evidence_layer.get("items") or []) if i.get("evidence_type") == "video_frame"]
        ),
    }


def run_all() -> Dict[str, Any]:
    root = Path(__file__).resolve().parent
    template = json.loads((root / "expected_cases.json").read_text(encoding="utf-8"))
    cases_dir = root / "cases"

    from app.project_intelligence.evidence_schema import build_evidence_layer_from_profile
    from app.project_intelligence.project_profile import build_project_profile

    out_cases: List[Dict[str, Any]] = []

    setups = [
        ("case_a_gameplay_video", "gameplay_capture.mp4", 45, True),
        ("case_b_menu_only_video", "menu_screen.mp4", 30, True),
        ("case_c_static_video", "static_run.mp4", 40, True),
        ("case_d_very_short_video", "short_clip.mp4", 2, True),
        ("case_e_video_no_other_runtime", "orphan_video.mp4", 25, False),
    ]

    meta_by_id = {t[0]: t for t in setups}

    for entry in template.get("cases") or []:
        cid = entry.get("case_id") or ""
        tup = meta_by_id.get(cid)
        if not tup:
            out_cases.append({**entry, "actual_behavior": json.dumps({"error": "unknown case"})})
            continue
        _, name, nfr, collision = tup
        cdir = cases_dir / cid
        _unity_stub(cdir, collision)
        _ensure_case_video(cdir, name, nfr)
        paths = _collect_files(cdir)
        if not paths:
            out_cases.append({**entry, "actual_behavior": json.dumps({"error": "no files"})})
            continue
        prof = build_project_profile(paths)
        el = build_evidence_layer_from_profile(prof)
        snap = _compact(prof, el)
        out_cases.append({**entry, "actual_behavior": json.dumps(snap, ensure_ascii=False, indent=2)})

    return {"run_purpose": template.get("run_purpose", ""), "cases": out_cases}


def main() -> None:
    data = run_all()
    out_path = Path(__file__).resolve().parent / "mini_validation_video_last_run.json"
    if out_path.is_file():
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        prev_map = {c.get("case_id"): c for c in (prev.get("cases") or [])}
        for c in data["cases"]:
            old = prev_map.get(c.get("case_id"))
            if isinstance(old, dict):
                for k in ("observed_friction", "corroboration_observation_notes"):
                    if old.get(k):
                        c[k] = old[k]
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
