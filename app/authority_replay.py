"""
Authority Replay — temporal provenance viewer data builder.

artifact → hint → corroboration → contradiction → authority downgrade → claim boundary
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


_STEP_ORDER = {
    "artifact": 10,
    "hint": 20,
    "corroboration": 30,
    "authority": 40,
    "contradiction": 50,
    "claim_boundary": 60,
    "governance_flag": 70,
}


def build_authority_replay(
    grading_snapshot: Optional[Dict[str, Any]] = None,
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build ordered replay timeline from persisted grading snapshot.
    Does not mutate grades — read-only provenance reconstruction.
    """
    snap = grading_snapshot or {}
    inv = artifact_inventory or snap.get("artifact_inventory") or {}
    graph = snap.get("evidence_trace_graph") or inv.get("evidence_trace_graph") or {}
    claim_flags = snap.get("claim_authority_flags") or {}

    steps: List[Dict[str, Any]] = []
    seq = 0

    def add_step(phase: str, title_ar: str, detail_ar: str, meta: Optional[Dict] = None) -> None:
        nonlocal seq
        seq += 1
        steps.append({
            "seq": seq,
            "phase": phase,
            "title_ar": title_ar,
            "detail_ar": detail_ar,
            "meta": meta or {},
        })

    # ── Phase 1: Artifacts ──
    rt = inv.get("runtime_artifacts") or {}
    for exe in rt.get("executable_files") or []:
        add_step(
            "artifact",
            f"Artifact: {exe.get('name', 'executable')}",
            "ملف تنفيذي مُرصد — presence only، لم يُشغَّل.",
            {"kind": "executable", "name": exe.get("name")},
        )
    for v in inv.get("gameplay_video_inference", {}).get("video_sources") or []:
        add_step(
            "artifact",
            f"Artifact: فيديو {v}",
            "footage مرشّح — L3 advisory.",
            {"kind": "video", "name": v},
        )
    emb = (inv.get("embedded_screenshots") or {}).get("count") or 0
    if emb:
        add_step(
            "artifact",
            f"Artifact: {emb} صورة مضمّنة",
            "embedded screenshots — static visual evidence.",
            {"kind": "embedded_screenshots", "count": emb},
        )
    for src in (inv.get("source_code") or {}).get("files") or []:
        add_step(
            "artifact",
            f"Artifact: كود {src.get('name')}",
            "source code — static inspection only.",
            {"kind": "source_code", "name": src.get("name")},
        )

    # ── Phase 2: Hints ──
    gvi = inv.get("gameplay_video_inference") or {}
    for hint in (gvi.get("video_analysis") or {}).get("runtime_hints") or []:
        add_step(
            "hint",
            f"Hint: {hint.get('hint_type')}",
            str(hint.get("detail") or "runtime hint — possible_runtime_evidence"),
            {
                "confidence": hint.get("confidence"),
                "hint_authority": hint.get("hint_authority"),
                "corroborated_by": hint.get("corroborated_by"),
            },
        )
    for item in (inv.get("screenshot_intelligence") or {}).get("items") or []:
        evs = ", ".join(item.get("possible_evidence") or [])
        add_step(
            "hint",
            f"Hint: screenshot {evs}",
            "استدلال بصري استشاري — ليس verification.",
            {"source": item.get("source"), "confidence": item.get("confidence"), "tier": item.get("tier", "L2")},
        )

    l2l3 = inv.get("l2_l3_corroborative_runtime") or {}
    for shot in l2l3.get("l2_folder_screenshots") or []:
        if not isinstance(shot, dict):
            continue
        add_step(
            "hint",
            f"L2 corroborative: {shot.get('basename', 'screenshot')}",
            "visual runtime activity suggested — criterion authority NOT inferred.",
            {
                "tier": "L2",
                "source": shot.get("source"),
                "authority_ceiling": l2l3.get("authority_ceiling"),
                "not_inferred": shot.get("not_inferred") or [],
            },
        )
    l3 = l2l3.get("l3_video_evidence") or {}
    if (l3.get("videos_detected") or 0) > 0 or (l3.get("frames_sampled") or 0) > 0:
        add_step(
            "hint",
            "L3 temporal video evidence",
            str(l3.get("institutional_label_ar") or "observed runtime activity under limited conditions"),
            {
                "tier": "L3",
                "frames_sampled": l3.get("frames_sampled"),
                "not_inferred": l3.get("not_inferred") or [],
            },
        )
    for amb in l2l3.get("ambiguity_flags") or []:
        if not isinstance(amb, dict):
            continue
        add_step(
            "contradiction",
            f"Ambiguity preserved: {amb.get('flag')}",
            str(amb.get("message_ar") or ""),
            {"severity": "advisory", "effect": "ambiguity_visibility"},
        )

    # ── Phase 3: Corroboration (from hints with corroborated_by) ──
    for hint in (gvi.get("video_analysis") or {}).get("runtime_hints") or []:
        for corr in hint.get("corroborated_by") or []:
            add_step(
                "corroboration",
                f"Corroboration: {corr}",
                f"يدعم hint «{hint.get('hint_type')}» — plausibility ↑، authority ثابتة.",
                {"hint_type": hint.get("hint_type"), "target": corr},
            )

    # ── Phase 4: Authority levels ──
    rt_level = inv.get("runtime_evidence_level") or {}
    add_step(
        "authority",
        f"Authority: runtime L{rt_level.get('level', 0)}",
        str(rt_level.get("label_ar") or rt_level.get("label_en") or ""),
        {"authority": rt_level.get("authority"), "max_auto_level": rt_level.get("max_auto_level", 3)},
    )
    ta = gvi.get("temporal_evidence_authority") or {}
    if ta.get("temporal_authority_level") is not None:
        add_step(
            "authority",
            f"Authority: temporal L{ta.get('temporal_authority_level')}",
            str(ta.get("label_ar") or ta.get("label_en") or ""),
            {"max_claim_authority": ta.get("max_claim_authority")},
        )

    # ── Phase 5: Contradictions (downgrade) ──
    tc = inv.get("temporal_consistency") or {}
    for sig in tc.get("temporal_consistency_signals") or []:
        add_step(
            "contradiction",
            f"Contradiction: {sig.get('code')}",
            str(sig.get("message_ar") or ""),
            {
                "severity": sig.get("severity"),
                "resolution": sig.get("resolution"),
                "effect": "authority_downgrade",
            },
        )
    cross = inv.get("cross_artifact_consistency") or {}
    for amb in cross.get("ambiguities") or []:
        add_step(
            "contradiction",
            f"Ambiguity: {amb.get('code')}",
            str(amb.get("message_ar") or ""),
            {"severity": amb.get("severity"), "effect": "advisory_hold"},
        )

    # ── Phase 6: Claim boundary ──
    mapping = inv.get("authority_mapping") or {}
    allowed = ", ".join(mapping.get("aggregate_allowed_claims_en") or [])[:200]
    forbidden = ", ".join(mapping.get("aggregate_forbidden_claims_en") or [])[:200]
    add_step(
        "claim_boundary",
        "Claim boundary",
        f"ALLOWED: {allowed or '—'} | FORBIDDEN: {forbidden or '—'}",
        {"enforcement_mode": mapping.get("enforcement_mode")},
    )

    # ── Phase 7: Post-grade governance flags ──
    if isinstance(claim_flags, dict):
        for oc in claim_flags.get("overclaims") or []:
            add_step(
                "governance_flag",
                f"Overclaim: {oc.get('criterion')}",
                str(oc.get("sanitized_preview") or "language exceeds authority"),
                {"violations": oc.get("violations"), "kind": "overclaim_drift"},
            )
        for ts in claim_flags.get("temporal_consistency") or []:
            add_step(
                "governance_flag",
                f"Temporal signal: {ts.get('code')}",
                str(ts.get("message_ar") or ""),
                {"severity": ts.get("severity"), "kind": "temporal_consistency_signal"},
            )
    elif isinstance(claim_flags, list):
        for oc in claim_flags:
            add_step(
                "governance_flag",
                f"Overclaim: {oc.get('criterion')}",
                str(oc.get("sanitized_preview") or ""),
                {"violations": oc.get("violations")},
            )

    # Sort by phase order (artifacts first) preserving seq within phase
    steps.sort(key=lambda s: (_STEP_ORDER.get(s.get("phase", ""), 99), s.get("seq", 0)))
    for i, s in enumerate(steps, 1):
        s["display_order"] = i

    return {
        "version": 1,
        "mode": "authority_replay_viewer",
        "governance_freeze": "GOVERNANCE_FREEZE_v1",
        "step_count": len(steps),
        "steps": steps,
        "graph_summary": {
            "nodes": graph.get("node_count", 0),
            "edges": graph.get("edge_count", 0),
            "trace_summary_ar": graph.get("trace_summary_ar", ""),
        },
        "runtime_evidence_level": rt_level.get("level"),
        "has_contradictions": bool(
            (tc.get("temporal_consistency_signals") or [])
            or (cross.get("ambiguities") or [])
        ),
        "note_ar": (
            "Authority Replay — إعادة بناء provenance فقط؛ "
            "لا تعدّل الدرجة ولا تمنح سلطة جديدة."
        ),
    }
