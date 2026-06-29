"""
Raw OCR on runtime screenshots and sampled video frames (presence only).

No semantics, scene understanding, or gameplay inference — text extraction for
pipeline / diagnostics only. Requires Tesseract on PATH (see pytesseract docs).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .temporal_alignment import parse_timestamp_from_screenshot_path

OCR_EXTRACTOR_VERSION = "1.0"
MAX_OCR_TARGETS = 28
MAX_RAW_TEXT_STORE = 12_000
MIN_UI_ALNUM = 6

_UI_KEYWORDS = re.compile(
    r"\b(score|menu|hud|health|level|paused|pause|fps|lives|wave|coin|points?|"
    r"ammo|inventory|unity|debug|time|timer|loading|settings|quit|play)\b",
    re.I,
)


def _try_import_ocr() -> Tuple[Any, Any]:
    try:
        import pytesseract  # type: ignore
        from PIL import Image

        return pytesseract, Image
    except ImportError:
        return None, None


def _alnum_ratio(text: str) -> float:
    if not text:
        return 0.0
    a = sum(1 for c in text if c.isalnum())
    return float(a) / float(max(len(text), 1))


def _looks_like_ui_text(text: str) -> bool:
    t = text.strip()
    if len(t) < MIN_UI_ALNUM:
        return False
    if _UI_KEYWORDS.search(t):
        return True
    if re.search(r"\d", t) and re.search(r"[a-zA-Z]{2,}", t) and ":" in t:
        return True
    return _alnum_ratio(t) >= 0.35 and len(t) >= 10


def _low_text_density(text: str) -> bool:
    s = (text or "").strip()
    if len(s) < 2:
        return True
    if len(s) < 4 and not re.search(r"\d", s):
        return True
    return _alnum_ratio(s) < 0.12 and len(s) < 30


def _run_ocr_on_file(
    pytesseract: Any, Image: Any, path: Path
) -> Tuple[str, Optional[str]]:
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            raw = pytesseract.image_to_string(im, lang="eng", config="--psm 6")
        return ((raw or "").strip(), None)
    except Exception as exc:  # noqa: BLE001 — surface as noise, not crash
        return ("", str(exc)[:200])


def _gather_targets(runtime_evidence: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Ordered list of image paths to OCR with timestamps and display source."""
    out: List[Dict[str, Any]] = []
    max_v = 0.0
    for it in runtime_evidence.get("video_evidence_items") or []:
        if isinstance(it, dict):
            try:
                max_v = max(max_v, float(it.get("timestamp_seconds") or 0.0))
            except (TypeError, ValueError):
                continue

    for idx, row in enumerate(runtime_evidence.get("screenshot_candidates") or []):
        if not isinstance(row, dict):
            continue
        pth = row.get("path")
        base = str(row.get("basename") or "")
        if not pth:
            continue
        path = Path(str(pth))
        ts = parse_timestamp_from_screenshot_path(str(pth), base)
        if ts is None:
            ts = max_v + 40.0 + float(idx) * 5.0
        out.append(
            {
                "path": path,
                "timestamp_seconds": float(ts),
                "source": base or path.name,
                "kind": "screenshot",
            }
        )

    for row in runtime_evidence.get("video_evidence_items") or []:
        if not isinstance(row, dict):
            continue
        fp = row.get("frame_path")
        if not fp:
            continue
        path = Path(str(fp))
        try:
            ts = float(row.get("timestamp_seconds"))
        except (TypeError, ValueError):
            continue
        src = row.get("source")
        display = path.name
        if src:
            display = f"{src}:{path.name}"
        out.append(
            {
                "path": path,
                "timestamp_seconds": ts,
                "source": display,
                "kind": "video_frame",
            }
        )

    return out[:MAX_OCR_TARGETS]


def _dedupe_noise_flags(flags: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: set = set()
    out: List[Dict[str, str]] = []
    for f in flags:
        key = (f.get("flag"), f.get("detail"))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def extract_runtime_ocr_evidence(runtime_evidence: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Run OCR on screenshots and video frames already listed in runtime_evidence.

    Returns a dict to merge into runtime_evidence:
      ocr_evidence_items, ocr_presence_flags, ocr_noise_flags
    """
    presence: List[Dict[str, str]] = []
    noise: List[Dict[str, str]] = []
    items: List[Dict[str, Any]] = []

    if not isinstance(runtime_evidence, dict):
        return {
            "ocr_evidence_items": [],
            "ocr_presence_flags": [],
            "ocr_noise_flags": [{"flag": "ocr_engine_unavailable", "detail": "invalid_runtime_evidence"}],
            "ocr_extractor_version": OCR_EXTRACTOR_VERSION,
        }

    pytesseract, Image = _try_import_ocr()
    if pytesseract is None or Image is None:
        return {
            "ocr_evidence_items": [],
            "ocr_presence_flags": [],
            "ocr_noise_flags": [{"flag": "ocr_engine_unavailable", "detail": "pytesseract_or_pillow_import"}],
            "ocr_extractor_version": OCR_EXTRACTOR_VERSION,
        }

    tcmd = os.environ.get("TESSERACT_CMD", "").strip()
    if tcmd:
        pytesseract.pytesseract.tesseract_cmd = tcmd

    targets = _gather_targets(runtime_evidence)
    if not targets:
        return {
            "ocr_evidence_items": [],
            "ocr_presence_flags": [],
            "ocr_noise_flags": [],
            "ocr_extractor_version": OCR_EXTRACTOR_VERSION,
        }

    engine_errors = 0
    any_ui = False
    low_density_hits = 0

    for t in targets:
        path: Path = t["path"]
        if not path.is_file():
            engine_errors += 1
            continue
        try:
            if path.stat().st_size > 25_000_000:
                noise.append({"flag": "ocr_skipped_large_image", "detail": path.name[:80]})
                continue
        except OSError:
            engine_errors += 1
            continue

        raw, err = _run_ocr_on_file(pytesseract, Image, path)
        if err:
            engine_errors += 1
            noise.append({"flag": "ocr_read_failed", "detail": err[:120]})
            continue

        if _low_text_density(raw):
            low_density_hits += 1
        if _looks_like_ui_text(raw):
            any_ui = True

        items.append(
            {
                "evidence_type": "ocr_text",
                "source": t["source"],
                "timestamp_seconds": round(float(t["timestamp_seconds"]), 4),
                "raw_text": raw[:MAX_RAW_TEXT_STORE],
                "kind": t.get("kind"),
                "image_path": str(path.resolve()),
            }
        )

    if any_ui:
        presence.append({"flag": "ui_text_detected"})
    if not items and targets and engine_errors >= len(targets):
        noise.append({"flag": "ocr_engine_unavailable", "detail": "all_targets_failed"})
    elif low_density_hits > 0 and len(items) > 0:
        noise.append({"flag": "ocr_low_text_density", "detail": str(low_density_hits)})

    log_files = runtime_evidence.get("log_files") or []
    if items and isinstance(log_files, list) and len(log_files) == 0:
        noise.append({"flag": "ocr_text_without_runtime_context", "detail": "no_log_files"})

    return {
        "ocr_evidence_items": items,
        "ocr_presence_flags": presence,
        "ocr_noise_flags": _dedupe_noise_flags(noise),
        "ocr_extractor_version": OCR_EXTRACTOR_VERSION,
    }
