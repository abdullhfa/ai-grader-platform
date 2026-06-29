"""
Build tiny gameplay folders + optional synthetic OCR rows → ui_token_correlation.

Usage (repo root):
  python -m app.calibration.mini_validation_ui_tokens.run_mini_validation_ui_tokens
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _write_text_png(path: Path, text: str) -> None:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (280, 90), (16, 18, 22))
    ImageDraw.Draw(im).text((12, 32), text, fill=(250, 250, 245))
    im.save(path, format="PNG")


def _collect_files(case_dir: Path) -> List[str]:
    return [str(p.resolve()) for p in sorted(case_dir.rglob("*")) if p.is_file()]


def _prepare_fs(case_dir: Path, cid: str) -> None:
    g = case_dir / "gameplay"
    g.mkdir(parents=True, exist_ok=True)
    log = g / "runtime.log"
    if cid == "case_a_score_ocr_log_overlap":
        log.write_text("t=1.0 score update +10\n", encoding="utf-8")
        _write_text_png(g / "hud.png", "Score: 100")
    elif cid == "case_b_inventory_ocr_only":
        _write_text_png(g / "inv.png", "Open inventory here")
    elif cid == "case_c_health_log_only":
        log.write_text("t=2.0 hp changed to 50\n", encoding="utf-8")
    elif cid == "case_d_pause_menu_only":
        _write_text_png(g / "menu.png", "Pause Menu")
    elif cid == "case_e_score_split_time":
        log.write_text("t=0.5 score update initial\n", encoding="utf-8")
        _write_text_png(g / "board_12000s.png", "Score: 999")


def _synthetic_ocr_rows(cid: str) -> List[Dict[str, Any]]:
    if cid == "case_a_score_ocr_log_overlap":
        return [
            {
                "evidence_type": "ocr_text",
                "raw_text": "Score: 100",
                "timestamp_seconds": 1.05,
                "source": "hud.png",
                "image_path": str(Path("synthetic") / "hud.png"),
            }
        ]
    if cid == "case_b_inventory_ocr_only":
        return [
            {
                "evidence_type": "ocr_text",
                "raw_text": "inventory screen",
                "timestamp_seconds": 40.0,
                "source": "inv.png",
                "image_path": str(Path("synthetic") / "inv.png"),
            }
        ]
    if cid == "case_d_pause_menu_only":
        return [
            {
                "evidence_type": "ocr_text",
                "raw_text": "Pause Menu",
                "timestamp_seconds": 12.0,
                "source": "menu.png",
                "image_path": str(Path("synthetic") / "menu.png"),
            }
        ]
    if cid == "case_e_score_split_time":
        return [
            {
                "evidence_type": "ocr_text",
                "raw_text": "Final Score: 999",
                "timestamp_seconds": 12000.0,
                "source": "board_12000s.png",
                "image_path": str(Path("synthetic") / "board.png"),
            }
        ]
    return []


def _inject_synthetic_ocr(profile: Dict[str, Any], cid: str) -> None:
    rows = _synthetic_ocr_rows(cid)
    if not rows:
        return
    rt = profile.get("runtime_evidence")
    if not isinstance(rt, dict):
        return
    existing = [x for x in (rt.get("ocr_evidence_items") or []) if isinstance(x, dict)]
    rt["ocr_evidence_items"] = existing + rows


def _compact(profile: Dict[str, Any]) -> Dict[str, Any]:
    ut = profile.get("ui_token_correlation") or {}
    return {
        "token_correlation_groups": ut.get("token_correlation_groups") or [],
        "token_noise_flags": ut.get("token_noise_flags") or [],
        "token_reasoning": ut.get("token_reasoning") or {},
        "window_seconds": ut.get("window_seconds"),
    }


def run_all() -> Dict[str, Any]:
    root = Path(__file__).resolve().parent
    template = json.loads((root / "expected_cases.json").read_text(encoding="utf-8"))

    from app.project_intelligence.project_profile import build_project_profile
    from app.project_intelligence.ui_token_correlation import build_ui_token_correlation

    cases_out: List[Dict[str, Any]] = []
    for entry in template.get("cases") or []:
        cid = str(entry.get("case_id") or "")
        case_dir = root / "cases" / cid
        case_dir.mkdir(parents=True, exist_ok=True)
        _prepare_fs(case_dir, cid)
        paths = _collect_files(case_dir)
        profile = build_project_profile(paths)
        _inject_synthetic_ocr(profile, cid)
        profile["ui_token_correlation"] = build_ui_token_correlation(profile)
        snap = _compact(profile)
        cases_out.append({**entry, "actual_behavior": json.dumps(snap, ensure_ascii=False, indent=2)})

    return {
        "run_purpose": template.get("run_purpose", ""),
        "cases": cases_out,
        "note": "Synthetic OCR rows fill gaps when Tesseract is unavailable.",
    }


def main() -> None:
    out = run_all()
    root = Path(__file__).resolve().parent
    out_path = root / "mini_validation_ui_tokens_last_run.json"
    if out_path.is_file():
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        prev_by_id = {c.get("case_id"): c for c in (prev.get("cases") or [])}
        for c in out["cases"]:
            pid = c.get("case_id")
            old = prev_by_id.get(pid) if isinstance(prev_by_id, dict) else None
            if isinstance(old, dict):
                for key in ("observed_friction", "unexpected_result", "ui_token_notes"):
                    if old.get(key):
                        c[key] = old[key]
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
