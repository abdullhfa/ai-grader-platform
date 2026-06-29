"""
Evidence Fingerprint v1 — canonical hash of evidence used in grading decisions.

Pairs with ``decision_provenance.bundle_hash`` for full reproducibility:

    bundle_hash  → which rules
    evidence_hash → which evidence
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

FINGERPRINT_VERSION = "v1"
_EMPTY = "0000000000000000000000000000000000000000000000000000000000000000"


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _sha256_payload(obj: Any) -> str:
    return hashlib.sha256(_stable_json(obj).encode("utf-8")).hexdigest()


def _hash_file_bytes(path: str) -> str:
    try:
        p = Path(path)
        if p.is_file() and p.stat().st_size <= 8_000_000:
            return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        pass
    return ""


def compute_word_hash(
    *,
    student_text: Optional[str] = None,
    content_fingerprint: Optional[Dict[str, Any]] = None,
) -> str:
    fp = content_fingerprint or {}
    if fp.get("content_hash"):
        return str(fp["content_hash"])
    if student_text and student_text.strip():
        return _sha256_text(student_text.strip())
    return _EMPTY


def compute_source_code_hash(inventory: Optional[Dict[str, Any]]) -> str:
    inv = inventory or {}
    rows: List[Dict[str, Any]] = []
    for block_key in ("source_code", "source_code_artifacts"):
        block = inv.get(block_key) or {}
        for f in block.get("files") or []:
            if not isinstance(f, dict):
                continue
            name = str(f.get("name") or "")
            if not name:
                continue
            path = str(f.get("path") or "")
            content_h = _hash_file_bytes(path) if path else ""
            rows.append(
                {
                    "name": name,
                    "ext": str(f.get("ext") or ""),
                    "size_bytes": int(f.get("size_bytes") or 0),
                    "source_kind": str(f.get("source_kind") or ""),
                    "content_hash": content_h or None,
                }
            )
    if not rows and inv.get("has_source_code_artifacts"):
        rows.append({"flag": "has_source_code_artifacts"})
    rows.sort(key=lambda r: str(r.get("name") or r.get("flag") or ""))
    return _sha256_payload(rows) if rows else _EMPTY


def compute_visual_hash(
    *,
    visual_summary: Optional[Dict[str, Any]] = None,
    inventory: Optional[Dict[str, Any]] = None,
) -> str:
    """Hash vision evidence **used in decision** (not merely found)."""
    ves = visual_summary or (inventory or {}).get("visual_evidence_summary") or {}
    emb = (inventory or {}).get("embedded_screenshots") or {}

    batches: List[Dict[str, Any]] = []
    for b in ves.get("vision_batches") or []:
        if not isinstance(b, dict):
            continue
        if int(b.get("analyzed") or 0) <= 0:
            continue
        batches.append(
            {
                "lane": b.get("lane") or "unknown",
                "submitted": int(b.get("submitted") or 0),
                "analyzed": int(b.get("analyzed") or 0),
            }
        )
    batches.sort(key=lambda x: (str(x.get("lane")), x.get("submitted", 0)))

    payload = {
        "images_used_in_decision": int(
            ves.get("images_used_in_decision")
            or emb.get("images_used_in_decision")
            or 0
        ),
        "images_analyzed": int(ves.get("images_analyzed") or emb.get("vision_analyzed_count") or 0),
        "vision_completed": bool(ves.get("vision_completed")),
        "vision_batches_used": batches,
    }
    if payload["images_used_in_decision"] <= 0 and payload["images_analyzed"] <= 0:
        return _EMPTY
    return _sha256_payload(payload)


def compute_video_hash(
    *,
    visual_summary: Optional[Dict[str, Any]] = None,
    video_keyframe_meta: Optional[Dict[str, Any]] = None,
) -> str:
    ves = visual_summary or {}
    meta = video_keyframe_meta or {}
    used = int(ves.get("video_keyframes_used_in_decision") or 0)
    analyzed = int(ves.get("video_keyframes_analyzed") or meta.get("frames_extracted") or 0)
    if used <= 0 and analyzed <= 0 and not meta.get("sources"):
        return _EMPTY

    sources = []
    for s in meta.get("sources") or []:
        if not isinstance(s, dict):
            continue
        sources.append(
            {
                "label": str(s.get("label") or ""),
                "frames": int(s.get("frames") or 0),
            }
        )
    sources.sort(key=lambda x: x.get("label") or "")

    payload = {
        "video_keyframes_used_in_decision": used,
        "video_keyframes_analyzed": analyzed,
        "videos_found": int(ves.get("video_keyframes_found") or meta.get("videos_found") or 0),
        "sources": sources,
        "method": str(meta.get("method") or ""),
    }
    return _sha256_payload(payload)


def compute_evidence_hash(
    *,
    word_hash: str,
    source_code_hash: str,
    visual_hash: str,
    video_hash: str,
) -> str:
    return _sha256_payload(
        {
            "version": FINGERPRINT_VERSION,
            "word_hash": word_hash or _EMPTY,
            "source_code_hash": source_code_hash or _EMPTY,
            "visual_hash": visual_hash or _EMPTY,
            "video_hash": video_hash or _EMPTY,
        }
    )


def build_evidence_fingerprint(
    *,
    student_text: Optional[str] = None,
    content_fingerprint: Optional[Dict[str, Any]] = None,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    visual_evidence_summary: Optional[Dict[str, Any]] = None,
    video_keyframe_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    inv = artifact_inventory or {}
    ves = visual_evidence_summary or inv.get("visual_evidence_summary") or {}
    vk_meta = video_keyframe_meta or inv.get("basic_video_keyframes_meta") or {}

    word_hash = compute_word_hash(
        student_text=student_text,
        content_fingerprint=content_fingerprint,
    )
    source_code_hash = compute_source_code_hash(inv)
    visual_hash = compute_visual_hash(visual_summary=ves, inventory=inv)
    video_hash = compute_video_hash(visual_summary=ves, video_keyframe_meta=vk_meta)
    evidence_hash = compute_evidence_hash(
        word_hash=word_hash,
        source_code_hash=source_code_hash,
        visual_hash=visual_hash,
        video_hash=video_hash,
    )

    return {
        "version": FINGERPRINT_VERSION,
        "word_hash": word_hash,
        "source_code_hash": source_code_hash,
        "visual_hash": visual_hash,
        "video_hash": video_hash,
        "evidence_hash": evidence_hash,
    }


def copy_fingerprint(fingerprint: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return dict(fingerprint or {})


def fingerprint_from_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not payload:
        return build_evidence_fingerprint()
    fp = payload.get("evidence_fingerprint")
    if isinstance(fp, dict) and fp.get("evidence_hash"):
        return fp
    inv = payload.get("artifact_inventory")
    if isinstance(inv, dict):
        inv_fp = inv.get("evidence_fingerprint")
        if isinstance(inv_fp, dict) and inv_fp.get("evidence_hash"):
            return inv_fp
    gdm = payload.get("grade_display_metrics")
    if isinstance(gdm, dict):
        gdm_fp = gdm.get("evidence_fingerprint")
        if isinstance(gdm_fp, dict) and gdm_fp.get("evidence_hash"):
            return gdm_fp
    return build_evidence_fingerprint(
        student_text=payload.get("student_text"),
        content_fingerprint=payload.get("content_fingerprint"),
        artifact_inventory=inv if isinstance(inv, dict) else None,
        visual_evidence_summary=payload.get("visual_evidence_summary"),
        video_keyframe_meta=payload.get("basic_video_keyframes_meta"),
    )


def classify_reproducibility_drift(
    *,
    bundle_hash_a: str,
    bundle_hash_b: str,
    evidence_hash_a: str,
    evidence_hash_b: str,
) -> str:
    """
    A: same bundle + same evidence → decision must match
    B: same bundle + different evidence → student changed submission
    C: different bundle + same evidence → rules/mode changed
    D: both differ → rules and evidence changed
    """
    same_bundle = bool(bundle_hash_a and bundle_hash_a == bundle_hash_b)
    same_evidence = bool(evidence_hash_a and evidence_hash_a == evidence_hash_b)
    if same_bundle and same_evidence:
        return "A_rules_and_evidence_stable"
    if same_bundle and not same_evidence:
        return "B_evidence_changed"
    if not same_bundle and same_evidence:
        return "C_rules_changed"
    return "D_rules_and_evidence_changed"


def attach_evidence_fingerprint(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attach unified evidence_fingerprint to grading_result + inventory."""
    inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
    if not grading_result.get("evidence_fingerprint"):
        grading_result["evidence_fingerprint"] = build_evidence_fingerprint(
            student_text=grading_result.get("student_text"),
            content_fingerprint=grading_result.get("content_fingerprint"),
            artifact_inventory=inv if isinstance(inv, dict) else None,
            visual_evidence_summary=grading_result.get("visual_evidence_summary"),
            video_keyframe_meta=grading_result.get("basic_video_keyframes_meta"),
        )
    fp = copy_fingerprint(grading_result["evidence_fingerprint"])
    grading_result["evidence_fingerprint"] = fp

    if isinstance(inv, dict):
        inv["evidence_fingerprint"] = copy_fingerprint(fp)
        if grading_result.get("basic_video_keyframes_meta"):
            inv["basic_video_keyframes_meta"] = grading_result["basic_video_keyframes_meta"]

    snap_inv = grading_result.get("artifact_inventory")
    if isinstance(snap_inv, dict) and snap_inv is not inv:
        snap_inv["evidence_fingerprint"] = copy_fingerprint(fp)

    gdm = grading_result.get("grade_display_metrics")
    if isinstance(gdm, dict):
        gdm["evidence_fingerprint"] = copy_fingerprint(fp)

    er = grading_result.get("evidence_registry")
    if isinstance(er, dict):
        er["evidence_fingerprint"] = copy_fingerprint(fp)

    prov = grading_result.get("decision_provenance")
    if isinstance(prov, dict):
        prov["evidence_hash"] = fp.get("evidence_hash")

    return grading_result
