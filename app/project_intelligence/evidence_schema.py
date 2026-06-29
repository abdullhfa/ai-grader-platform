"""
Normalized persistent evidence schema — single internal language for all extractors.

Gemini narrative stays separate; this layer is deterministic / auditable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .cross_modal_corroboration import build_cross_modal_corroboration
from .runtime_corroboration import build_runtime_corroboration
from .temporal_alignment import build_temporal_alignment
from .excel_semantic_extractor import build_spreadsheet_semantic_evidence_items
from .packet_tracer_extractor import build_packet_tracer_evidence_items
from .ui_token_correlation import build_ui_token_correlation

SCHEMA_VERSION = "1.0"


def normalize_unity_system_detection(det: Dict[str, Any]) -> Dict[str, Any]:
    """Map unity_extractor system_detections row → standard evidence record."""
    return {
        "evidence_type": "code_system",
        "engine": "unity",
        "system": det.get("system"),
        "confidence": det.get("confidence"),
        "execution_evidence": det.get("execution_evidence"),
        "evidence_count": det.get("evidence_count"),
        "sources": list(det.get("evidence") or []),
        "criterion_candidates": [],
        "weight": 0.0,
    }


def normalize_pattern_hint(tag: str, engines: List[str]) -> Dict[str, Any]:
    """Legacy regex / multi-engine pattern tag (low certainty)."""
    eng = engines[0] if len(engines) == 1 else "mixed"
    return {
        "evidence_type": "pattern_hint",
        "engine": eng,
        "system": tag,
        "confidence": None,
        "execution_evidence": "unknown",
        "evidence_count": None,
        "sources": [],
        "criterion_candidates": [],
        "weight": 0.0,
    }


def _primary_engine(engines: List[str]) -> str:
    if "unity" in engines:
        return "unity"
    if engines:
        return str(engines[0])
    return "unknown"


def normalize_runtime_screenshot(path: str, engines: List[str]) -> Dict[str, Any]:
    """Runtime / gameplay image supplied with submission (path/name heuristics only)."""
    return {
        "evidence_type": "runtime_screenshot",
        "engine": _primary_engine(engines),
        "system": None,
        "confidence": None,
        "execution_evidence": "runtime_capture",
        "evidence_count": 1,
        "sources": [path],
        "criterion_candidates": [],
        "weight": 0.0,
    }


def normalize_runtime_log(path: str, signals: Dict[str, Any], engines: List[str]) -> Dict[str, Any]:
    """Parsed runtime / Player.log-style file with deterministic keyword signals."""
    return {
        "evidence_type": "runtime_log",
        "engine": _primary_engine(engines),
        "system": None,
        "confidence": None,
        "execution_evidence": "runtime_log",
        "evidence_count": signals.get("line_count") if isinstance(signals, dict) else None,
        "sources": [path],
        "log_signals": signals if isinstance(signals, dict) else {},
        "criterion_candidates": [],
        "weight": 0.0,
    }


def normalize_video_frame(
    frame_path: str,
    source_video_basename: str,
    timestamp_seconds: float,
    engines: List[str],
) -> Dict[str, Any]:
    """One sampled frame from a submission video (presence-only modality)."""
    return {
        "evidence_type": "video_frame",
        "engine": _primary_engine(engines),
        "system": None,
        "confidence": None,
        "execution_evidence": "video_frame_sample",
        "evidence_count": 1,
        "sources": [frame_path],
        "timestamp_seconds": round(float(timestamp_seconds), 4),
        "source": source_video_basename,
        "criterion_candidates": [],
        "weight": 0.0,
    }


def normalize_spreadsheet_semantic(row: Dict[str, Any], engines: List[str]) -> Dict[str, Any]:
    """Deterministic Excel workbook signals (no semantic grading)."""
    engine = row.get("engine") or (
        "excel_spreadsheet" if "excel_spreadsheet" in engines else _primary_engine(engines)
    )
    return {
        "evidence_type": "spreadsheet_semantic",
        "engine": engine,
        "system": None,
        "confidence": None,
        "execution_evidence": row.get("execution_evidence") or "excel_workbook",
        "evidence_count": row.get("evidence_count"),
        "sources": list(row.get("sources") or []),
        "sheet_count": row.get("sheet_count"),
        "formula_cells": row.get("formula_cells"),
        "formula_types": list(row.get("formula_types") or []),
        "charts_detected": row.get("charts_detected"),
        "chart_count": row.get("chart_count"),
        "table_count": row.get("table_count"),
        "cross_sheet_references": row.get("cross_sheet_references"),
        "conditional_logic_detected": row.get("conditional_logic_detected"),
        "criterion_candidates": [],
        "weight": 0.0,
    }


def normalize_packet_tracer_topology(row: Dict[str, Any], engines: List[str]) -> Dict[str, Any]:
    """Deterministic Packet Tracer file signals (no semantic grading)."""
    engine = row.get("engine") or (
        "cisco_packet_tracer" if "cisco_packet_tracer" in engines else _primary_engine(engines)
    )
    return {
        "evidence_type": "packet_tracer_topology",
        "engine": engine,
        "system": None,
        "confidence": None,
        "execution_evidence": row.get("execution_evidence") or "packet_tracer_file",
        "evidence_count": row.get("evidence_count"),
        "sources": list(row.get("sources") or []),
        "topology_detected": row.get("topology_detected"),
        "ip_configurations_detected": row.get("ip_configurations_detected"),
        "subnets_detected": row.get("subnets_detected"),
        "static_routes_detected": row.get("static_routes_detected"),
        "routing_protocols": list(row.get("routing_protocols") or []),
        "device_count": row.get("device_count"),
        "router_count": row.get("router_count"),
        "switch_count": row.get("switch_count"),
        "pc_count": row.get("pc_count"),
        "criterion_candidates": [],
        "weight": 0.0,
    }


def normalize_ocr_text(row: Dict[str, Any], engines: List[str]) -> Dict[str, Any]:
    """Raw OCR line from ocr_runtime_extractor (no interpretation)."""
    raw = str(row.get("raw_text") or "")
    return {
        "evidence_type": "ocr_text",
        "engine": _primary_engine(engines),
        "system": None,
        "confidence": None,
        "execution_evidence": "ocr_presence",
        "evidence_count": 1,
        "sources": [str(row.get("image_path") or "")],
        "timestamp_seconds": row.get("timestamp_seconds"),
        "source": row.get("source"),
        "raw_text": raw[:8000],
        "criterion_candidates": [],
        "weight": 0.0,
    }


def build_evidence_layer_from_profile(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build the persisted evidence_layer block from a full project profile
    (output of build_project_profile).
    """
    if not profile:
        return {
            "schema_version": SCHEMA_VERSION,
            "items": [],
            "engines_detected": [],
            "profile_version": None,
            "unity_semantic_meta": None,
            "runtime_corroboration": build_runtime_corroboration(None),
            "temporal_alignment": build_temporal_alignment(None),
            "cross_modal_corroboration": build_cross_modal_corroboration(
                None, None, build_runtime_corroboration(None)
            ),
            "ui_token_correlation": build_ui_token_correlation(None),
        }

    engines = list(profile.get("engines_detected") or [])
    items: List[Dict[str, Any]] = []
    semantic_keys: set = set()

    if "unity" in engines:
        us = profile.get("unity_semantic") or {}
        if isinstance(us, dict) and "error" not in us:
            for det in us.get("system_detections") or []:
                if not isinstance(det, dict):
                    continue
                norm = normalize_unity_system_detection(det)
                items.append(norm)
                sy = norm.get("system")
                if sy:
                    semantic_keys.add(str(sy))

    for tag in profile.get("systems_detected") or []:
        if tag in semantic_keys:
            continue
        items.append(normalize_pattern_hint(tag, engines))

    rt = profile.get("runtime_evidence") or {}
    if isinstance(rt, dict):
        for row in rt.get("screenshot_candidates") or []:
            if not isinstance(row, dict):
                continue
            pth = row.get("path")
            base = row.get("basename")
            if not pth or not base:
                continue
            items.append(normalize_runtime_screenshot(str(pth), engines))
        for row in rt.get("log_files") or []:
            if not isinstance(row, dict):
                continue
            pth = row.get("path")
            base = row.get("basename")
            sig = row.get("signals") or {}
            if not pth or not base:
                continue
            items.append(normalize_runtime_log(str(pth), sig, engines))
        for row in rt.get("video_evidence_items") or []:
            if not isinstance(row, dict):
                continue
            fpth = row.get("frame_path")
            src = row.get("source")
            ts = row.get("timestamp_seconds")
            if not fpth or src is None or ts is None:
                continue
            items.append(
                normalize_video_frame(str(fpth), str(src), float(ts), engines)
            )
        for row in rt.get("ocr_evidence_items") or []:
            if not isinstance(row, dict):
                continue
            if row.get("evidence_type") != "ocr_text":
                continue
            items.append(normalize_ocr_text(row, engines))

    pt = profile.get("packet_tracer_evidence")
    if isinstance(pt, dict) and pt.get("pkt_files"):
        for row in build_packet_tracer_evidence_items(pt, engines):
            items.append(normalize_packet_tracer_topology(row, engines))

    xl = profile.get("excel_semantic_evidence")
    if isinstance(xl, dict) and xl.get("workbook_files"):
        for row in build_spreadsheet_semantic_evidence_items(xl, engines):
            items.append(normalize_spreadsheet_semantic(row, engines))

    us = profile.get("unity_semantic") if "unity" in engines else None
    meta = None
    if isinstance(us, dict) and "error" not in us:
        meta = {
            "extractor_version": us.get("extractor_version"),
            "scripts_analyzed": us.get("scripts_analyzed"),
            "monobehaviour_count": us.get("monobehaviour_count"),
            "limitations_ar": us.get("limitations_ar"),
        }

    ta = profile.get("temporal_alignment")
    if not isinstance(ta, dict):
        ta = build_temporal_alignment(profile)

    cm = profile.get("cross_modal_corroboration")
    if not isinstance(cm, dict):
        cm = build_cross_modal_corroboration(
            ta,
            profile.get("runtime_evidence"),
            build_runtime_corroboration(profile),
        )

    ut = profile.get("ui_token_correlation")
    if not isinstance(ut, dict):
        ut = build_ui_token_correlation(profile)

    sub_in = profile.get("submission_intake")
    _si_out: Optional[Dict[str, Any]] = None
    if isinstance(sub_in, dict) and sub_in:
        _si_out = {
            "version": sub_in.get("version"),
            "source": sub_in.get("source"),
            "submission_noise_flags": sub_in.get("submission_noise_flags"),
            "upload_diagnostics": sub_in.get("upload_diagnostics"),
        }

    layer = {
        "schema_version": SCHEMA_VERSION,
        "items": items,
        "engines_detected": engines,
        "profile_version": profile.get("version"),
        "unity_semantic_meta": meta,
        "runtime_corroboration": build_runtime_corroboration(profile),
        "temporal_alignment": ta,
        "cross_modal_corroboration": cm,
        "ui_token_correlation": ut,
    }
    if _si_out is not None:
        layer["submission_intake"] = _si_out

    pt = profile.get("packet_tracer_evidence")
    if isinstance(pt, dict) and pt.get("pkt_files"):
        layer["packet_tracer_evidence"] = {
            "extractor_version": pt.get("extractor_version"),
            "aggregate": pt.get("aggregate"),
            "network_evidence_summary": pt.get("network_evidence_summary"),
            "noise_flags": pt.get("noise_flags") or [],
        }

    xl = profile.get("excel_semantic_evidence")
    if isinstance(xl, dict) and xl.get("workbook_files"):
        layer["excel_semantic_evidence"] = {
            "extractor_version": xl.get("extractor_version"),
            "aggregate": xl.get("aggregate"),
            "spreadsheet_semantic_summary": xl.get("spreadsheet_semantic_summary"),
            "noise_flags": xl.get("noise_flags") or [],
        }
    return layer


def slim_profile_for_persistence(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Strip heavy fields but keep audit-relevant structure for DB JSON."""
    if not profile:
        return {}
    out: Dict[str, Any] = {
        "version": profile.get("version"),
        "engines_detected": profile.get("engines_detected"),
        "systems_detected": profile.get("systems_detected"),
        "systems_semantic": profile.get("systems_semantic"),
        "code_quality": profile.get("code_quality"),
        "file_stats": profile.get("file_stats"),
        "layout_evidence": profile.get("layout_evidence"),
    }
    rt = profile.get("runtime_evidence")
    if isinstance(rt, dict):
        out["runtime_evidence"] = {
            "version": rt.get("version"),
            "screenshot_basenames": [r.get("basename") for r in (rt.get("screenshot_candidates") or []) if isinstance(r, dict)][:25],
            "log_basenames": [r.get("basename") for r in (rt.get("log_files") or []) if isinstance(r, dict)][:10],
            "log_signals": [
                {"basename": r.get("basename"), "signals": r.get("signals")}
                for r in (rt.get("log_files") or [])[:5]
                if isinstance(r, dict)
            ],
            "video_frame_count": rt.get("video_frame_count"),
            "video_metadata": {
                "duration_seconds": (rt.get("video_metadata") or {}).get("duration_seconds"),
                "frame_count_extracted": (rt.get("video_metadata") or {}).get("frame_count_extracted"),
                "source_basenames": [
                    s.get("basename")
                    for s in (rt.get("video_metadata") or {}).get("sources") or []
                    if isinstance(s, dict)
                ][:6],
            },
            "video_noise_flags": rt.get("video_noise_flags") or [],
            "ocr_evidence_count": len(
                [x for x in (rt.get("ocr_evidence_items") or []) if isinstance(x, dict)]
            ),
            "ocr_presence_flags": rt.get("ocr_presence_flags") or [],
            "ocr_noise_flags": rt.get("ocr_noise_flags") or [],
        }
    rc = build_runtime_corroboration(profile)
    out["runtime_corroboration"] = {
        "engine_version": rc.get("engine_version"),
        "by_system": {
            sys: {
                "corroboration_strength": (row or {}).get("corroboration_strength"),
                "runtime_corroborated": (row or {}).get("runtime_corroborated"),
                "corroboration_confidence": (row or {}).get("corroboration_confidence"),
                "corroboration_modalities": (row or {}).get("corroboration_modalities"),
                "modality_diversity_score": (row or {}).get("modality_diversity_score"),
                "weighted_corroboration_score": (row or {}).get("weighted_corroboration_score"),
                "source_confidence_tier": (row or {}).get("source_confidence_tier"),
                "corroboration_reasoning": (row or {}).get("corroboration_reasoning"),
                "corroboration_noise_flags": (row or {}).get("corroboration_noise_flags"),
                "modality_confidence_tiers": (row or {}).get("modality_confidence_tiers"),
            }
            for sys, row in (rc.get("by_system") or {}).items()
        },
        "missing_runtime_corroboration_flags": rc.get("missing_runtime_corroboration_flags") or [],
        "corroboration_conflicts": rc.get("corroboration_conflicts") or [],
        "evidence_weights": rc.get("evidence_weights") or {},
        "modality_confidence_tier_reference": rc.get("modality_confidence_tier_reference") or {},
    }
    ta = profile.get("temporal_alignment")
    if not isinstance(ta, dict):
        ta = build_temporal_alignment(profile)
    out["temporal_alignment"] = {
        "version": ta.get("version"),
        "window_seconds": ta.get("window_seconds"),
        "temporal_alignment_strength": ta.get("temporal_alignment_strength"),
        "temporal_event_count": len(ta.get("temporal_events") or []),
        "temporal_group_count": len(ta.get("temporal_groups") or []),
        "temporal_alignment_conflicts": ta.get("temporal_alignment_conflicts") or [],
        "temporal_reasoning": (ta.get("temporal_reasoning") or {}).get("reasoning") or [],
        "temporal_groups_sample": (ta.get("temporal_groups") or [])[:8],
    }
    cm = profile.get("cross_modal_corroboration")
    if not isinstance(cm, dict):
        cm = build_cross_modal_corroboration(
            ta,
            profile.get("runtime_evidence"),
            rc,
        )
    out["cross_modal_corroboration"] = {
        "version": cm.get("version"),
        "cross_modal_diversity_score": cm.get("cross_modal_diversity_score"),
        "cross_modal_window_count": len(cm.get("cross_modal_windows") or []),
        "cross_modal_noise_flags": cm.get("cross_modal_noise_flags") or [],
        "cross_modal_reasoning": (cm.get("cross_modal_reasoning") or {}).get("reasoning") or [],
        "cross_modal_windows_sample": (cm.get("cross_modal_windows") or [])[:8],
        "runtime_corroboration_reference": cm.get("runtime_corroboration_reference") or {},
    }
    ut = profile.get("ui_token_correlation")
    if not isinstance(ut, dict):
        ut = build_ui_token_correlation(profile)
    out["ui_token_correlation"] = {
        "version": ut.get("version"),
        "window_seconds": ut.get("window_seconds"),
        "token_noise_flags": ut.get("token_noise_flags") or [],
        "token_reasoning": (ut.get("token_reasoning") or {}).get("reasoning") or [],
        "token_correlation_groups_sample": (ut.get("token_correlation_groups") or [])[:12],
    }
    us = profile.get("unity_semantic")
    if isinstance(us, dict):
        if "error" in us:
            out["unity_semantic"] = {"error": us["error"]}
        else:
            out["unity_semantic"] = {
                "extractor_version": us.get("extractor_version"),
                "scripts_analyzed": us.get("scripts_analyzed"),
                "assets_peeked": us.get("assets_peeked"),
                "monobehaviour_count": us.get("monobehaviour_count"),
                "system_detections": us.get("system_detections"),
                "using_namespaces_top": us.get("using_namespaces_top"),
                "scene_prefab_hints": (us.get("scene_prefab_hints") or [])[:20],
                "limitations_ar": us.get("limitations_ar"),
                "monobehaviours": (us.get("monobehaviours") or [])[:30],
            }
    si = profile.get("submission_intake")
    if isinstance(si, dict) and si:
        out["submission_intake"] = {
            "version": si.get("version"),
            "source": si.get("source"),
            "submission_noise_flags": si.get("submission_noise_flags") or [],
            "upload_diagnostics": si.get("upload_diagnostics") or {},
        }
    pt = profile.get("packet_tracer_evidence")
    if isinstance(pt, dict) and pt.get("pkt_files"):
        out["packet_tracer_evidence"] = {
            "extractor_version": pt.get("extractor_version"),
            "pkt_basenames": [Path(str(p)).name for p in (pt.get("pkt_files") or [])[:5]],
            "aggregate": pt.get("aggregate"),
            "network_evidence_summary": pt.get("network_evidence_summary"),
            "noise_flags": pt.get("noise_flags") or [],
        }
    xl = profile.get("excel_semantic_evidence")
    if isinstance(xl, dict) and xl.get("workbook_files"):
        out["excel_semantic_evidence"] = {
            "extractor_version": xl.get("extractor_version"),
            "workbook_basenames": [
                Path(str(p)).name for p in (xl.get("workbook_files") or [])[:5]
            ],
            "aggregate": xl.get("aggregate"),
            "spreadsheet_semantic_summary": xl.get("spreadsheet_semantic_summary"),
            "noise_flags": xl.get("noise_flags") or [],
        }
    return out


def compact_semantic_for_criterion(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Minimal row per system for per-criterion snapshots (smaller JSON)."""
    out: List[Dict[str, Any]] = []
    for it in items:
        if it.get("evidence_type") != "code_system":
            continue
        out.append(
            {
                "system": it.get("system"),
                "confidence": it.get("confidence"),
                "execution_evidence": it.get("execution_evidence"),
            }
        )
    return out


def attach_criterion_academic_snapshots(
    grading_result: Dict[str, Any],
    evidence_layer: Dict[str, Any],
    *,
    project_profile: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Enrich criteria_results with academic_snapshot (deterministic + AI slice).
    Modifies grading_result in place. Rubric shadow does not change achieved.
    """
    items = evidence_layer.get("items") or []
    compact = compact_semantic_for_criterion(items)
    pattern_compact = [
        {"system": it.get("system"), "evidence_type": "pattern_hint"}
        for it in items
        if it.get("evidence_type") == "pattern_hint"
    ]
    rt_logs = [it for it in items if it.get("evidence_type") == "runtime_log"]
    rt_shots = [it for it in items if it.get("evidence_type") == "runtime_screenshot"]
    rt_video = [it for it in items if it.get("evidence_type") == "video_frame"]
    rt_ocr = [it for it in items if it.get("evidence_type") == "ocr_text"]
    pt_items = [it for it in items if it.get("evidence_type") == "packet_tracer_topology"]
    xl_items = [it for it in items if it.get("evidence_type") == "spreadsheet_semantic"]
    log_collision = any(
        bool((it.get("log_signals") or {}).get("mentions_collision")) for it in rt_logs
    )
    log_scene = any(bool((it.get("log_signals") or {}).get("mentions_scene")) for it in rt_logs)
    log_save = any(bool((it.get("log_signals") or {}).get("mentions_save")) for it in rt_logs)

    rc = evidence_layer.get("runtime_corroboration") or {}
    rc_by = rc.get("by_system") or {}
    runtime_corroboration_compact = {
        sys: (row or {}).get("corroboration_strength") or "none"
        for sys, row in rc_by.items()
        if isinstance(row, dict)
    }
    rc_flags = list(rc.get("missing_runtime_corroboration_flags") or [])
    corroboration_conflicts = list(rc.get("corroboration_conflicts") or [])

    strongly_corroborated_systems: List[str] = []
    weakly_corroborated_systems: List[str] = []
    for sys, row in rc_by.items():
        if not isinstance(row, dict):
            continue
        st = str(row.get("corroboration_strength") or "none")
        try:
            w = float(row.get("weighted_corroboration_score") or 0.0)
        except (TypeError, ValueError):
            w = 0.0
        if st == "medium" or w >= 0.7:
            strongly_corroborated_systems.append(sys)
        elif st == "weak":
            weakly_corroborated_systems.append(sys)
    corroboration_summary = {
        "strongly_corroborated_systems": sorted(strongly_corroborated_systems),
        "weakly_corroborated_systems": sorted(weakly_corroborated_systems),
    }

    ta_layer = evidence_layer.get("temporal_alignment") or {}
    temporal_observation = {
        "version": ta_layer.get("version"),
        "window_seconds": ta_layer.get("window_seconds"),
        "temporal_alignment_strength": ta_layer.get("temporal_alignment_strength"),
        "temporal_event_count": len(ta_layer.get("temporal_events") or []),
        "temporal_group_count": len(ta_layer.get("temporal_groups") or []),
        "temporal_alignment_conflicts": ta_layer.get("temporal_alignment_conflicts") or [],
        "temporal_reasoning": (ta_layer.get("temporal_reasoning") or {}).get("reasoning") or [],
    }

    cm_layer = evidence_layer.get("cross_modal_corroboration") or {}
    cross_modal_observation = {
        "version": cm_layer.get("version"),
        "cross_modal_diversity_score": cm_layer.get("cross_modal_diversity_score"),
        "cross_modal_window_count": len(cm_layer.get("cross_modal_windows") or []),
        "cross_modal_noise_flags": cm_layer.get("cross_modal_noise_flags") or [],
        "cross_modal_reasoning": (cm_layer.get("cross_modal_reasoning") or {}).get("reasoning") or [],
    }

    ut_layer = evidence_layer.get("ui_token_correlation") or {}
    ui_token_observation = {
        "version": ut_layer.get("version"),
        "window_seconds": ut_layer.get("window_seconds"),
        "token_group_count": len(ut_layer.get("token_correlation_groups") or []),
        "token_noise_flags": ut_layer.get("token_noise_flags") or [],
        "token_reasoning": (ut_layer.get("token_reasoning") or {}).get("reasoning") or [],
        "tokens_strength_summary": [
            {
                "token": g.get("token"),
                "correlation_strength": g.get("correlation_strength"),
                "sources": g.get("sources"),
                "temporal_overlap": g.get("temporal_overlap"),
            }
            for g in (ut_layer.get("token_correlation_groups") or [])
            if isinstance(g, dict)
        ][:15],
    }

    pt_layer = evidence_layer.get("packet_tracer_evidence") or {}
    if not isinstance(pt_layer, dict):
        pt_layer = {}
    network_evidence_summary = pt_layer.get("network_evidence_summary") or {}
    if not network_evidence_summary and pt_items:
        network_evidence_summary = {
            "pkt_file_count": len(pt_items),
            "topology": {"topology_detected": any(it.get("topology_detected") for it in pt_items)},
            "addressing": {
                "ip_configurations_detected": any(
                    it.get("ip_configurations_detected") for it in pt_items
                ),
                "subnets_detected": max(
                    int(it.get("subnets_detected") or 0) for it in pt_items
                )
                if pt_items
                else 0,
            },
            "routing": {
                "static_routes_detected": any(it.get("static_routes_detected") for it in pt_items),
                "routing_protocols": sorted(
                    {
                        p
                        for it in pt_items
                        for p in (it.get("routing_protocols") or [])
                    }
                ),
            },
        }

    xl_layer = evidence_layer.get("excel_semantic_evidence") or {}
    if not isinstance(xl_layer, dict):
        xl_layer = {}
    spreadsheet_semantic_summary = xl_layer.get("spreadsheet_semantic_summary") or {}
    if not spreadsheet_semantic_summary and xl_items:
        spreadsheet_semantic_summary = {
            "workbook_file_count": len(xl_items),
            "formulas": {
                "formula_cells": sum(int(it.get("formula_cells") or 0) for it in xl_items),
                "formula_types": sorted(
                    {t for it in xl_items for t in (it.get("formula_types") or [])}
                ),
                "conditional_logic_detected": any(
                    it.get("conditional_logic_detected") for it in xl_items
                ),
                "cross_sheet_references": any(
                    it.get("cross_sheet_references") for it in xl_items
                ),
            },
            "charts": {
                "charts_detected": any(it.get("charts_detected") for it in xl_items),
                "chart_count": sum(int(it.get("chart_count") or 0) for it in xl_items),
            },
        }

    si_layer = evidence_layer.get("submission_intake") or {}
    submission_intake_observation: Dict[str, Any] = {}
    if isinstance(si_layer, dict) and si_layer:
        ud = si_layer.get("upload_diagnostics") or {}
        submission_intake_observation = {
            "version": si_layer.get("version"),
            "source": si_layer.get("source"),
            "submission_noise_flags": si_layer.get("submission_noise_flags") or [],
            "upload_diagnostics": {
                "total_files_uploaded": ud.get("total_files_uploaded"),
                "ignored_files": ud.get("ignored_files"),
                "effective_analysis_files": ud.get("effective_analysis_files"),
                "ignore_ratio": ud.get("ignore_ratio"),
                "relative_path_files": ud.get("relative_path_files"),
                "on_disk_files": ud.get("on_disk_files"),
            },
        }

    for cr in grading_result.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        lvl = cr.get("criteria_level") or ""
        achieved = bool(cr.get("achieved"))
        reasoning = str(cr.get("reasoning") or "")[:4000]
        cr["academic_snapshot"] = {
            "criterion": lvl,
            "systems_semantic": compact,
            "pattern_hints": pattern_compact,
            "runtime_evidence": {
                "runtime_screenshot_items": len(rt_shots),
                "runtime_log_items": len(rt_logs),
                "video_frame_items": len(rt_video),
                "ocr_text_items": len(rt_ocr),
                "log_mentions_collision": log_collision,
                "log_mentions_scene_load": log_scene,
                "log_mentions_save": log_save,
            },
            "runtime_corroboration": runtime_corroboration_compact,
            "corroboration_summary": corroboration_summary,
            "missing_runtime_corroboration_flags": rc_flags,
            "corroboration_conflicts": corroboration_conflicts,
            "temporal_alignment_observation": temporal_observation,
            "cross_modal_observation": cross_modal_observation,
            "ui_token_observation": ui_token_observation,
            "submission_intake_observation": submission_intake_observation,
            "packet_tracer_topology_items": len(pt_items),
            "network_evidence_summary": network_evidence_summary,
            "spreadsheet_semantic_items": len(xl_items),
            "spreadsheet_semantic_summary": spreadsheet_semantic_summary,
            "manual_flags": [],
            "ai_reasoning_summary": reasoning,
            "final_recommendation": "likely_achieved" if achieved else "likely_not_achieved",
        }

    try:
        from .rubric_sufficiency_contracts import attach_rubric_sufficiency_shadow

        layer_shadow = attach_rubric_sufficiency_shadow(
            grading_result,
            evidence_layer,
            profile=project_profile,
        )
        evidence_layer["rubric_sufficiency_shadow"] = layer_shadow
    except Exception:
        evidence_layer["rubric_sufficiency_shadow"] = {
            "version": None,
            "shadow_mode": "observation_only",
            "error": "rubric_shadow_attach_failed",
            "by_criterion": {},
        }

    try:
        from .human_review_gates import attach_human_review_gates

        attach_human_review_gates(grading_result, evidence_layer)
    except Exception:
        evidence_layer["human_review_gates"] = {
            "version": None,
            "advisory_mode": "governance_signal_only",
            "error": "human_review_gates_attach_failed",
            "submission": {},
            "by_criterion": {},
        }
