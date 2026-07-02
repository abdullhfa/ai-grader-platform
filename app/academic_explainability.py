"""
Academic explainability layer — governance intent, missing evidence, extraction coverage.

Principle: decisions (U, HOLD, gated runtime) must be defensible to teachers and auditors.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

_SOURCE_CODE_EXT = frozenset({".cs", ".py", ".java", ".cpp", ".c", ".js", ".gd", ".gml", ".lua"})

BASIC_PRO_UPGRADE_STATUS_AR = "تحديث الى خطة برو"
PRESENT_STATUS_AR = "تم التدقيق"
BASIC_PRO_GATED_REQUIREMENTS_AR = frozenset(
    {
        "ملف اللعبة (exe/build)",
        "أدلة الاختبار (خطط/سجلات)",
        "التحقق من الصور والفيديو",
        "التحقق من التشغيل (runtime)",
    }
)

_WORD_REPORT_REQUIREMENT_AR = "تقرير Word/PDF"
_WORD_REPORT_LEGACY_AR = "تقرير Word/PDF (GDD/توثيق)"

_REMOVED_DIAGNOSTIC_REQUIREMENTS_AR = frozenset(
    {
        "Web Runtime Browser Automation",
        "Android Emulator Farm (Flutter/Kotlin/Java)",
        "GameMaker Runtime Verification",
        "Scratch Verification",
        "لقطات شاشة",
        "لقطات شاشة للعبة",
    }
)

_VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".webm", ".m4v", ".flv"}
)


def _submission_has_video(inventory: Dict[str, Any]) -> bool:
    meta = inventory.get("basic_video_keyframes_meta") or {}
    if int(meta.get("videos_found") or 0) > 0:
        return True
    ves = inventory.get("visual_evidence_summary") or {}
    if int(ves.get("video_keyframes_found") or 0) > 0:
        return True
    for raw in inventory.get("intake_relative_paths") or []:
        if Path(str(raw)).suffix.lower() in _VIDEO_EXTENSIONS:
            return True
    rt = inventory.get("runtime_artifacts") or {}
    if rt.get("gameplay_video_detected"):
        return True
    media = inventory.get("media_artifacts") or {}
    if media.get("files"):
        return True
    gvi = inventory.get("gameplay_video_inference") or {}
    if int(gvi.get("videos_analyzed") or 0) > 0:
        return True
    for raw in inventory.get("submission_paths") or []:
        if Path(str(raw)).suffix.lower() in _VIDEO_EXTENSIONS:
            return True
    return False


def _basic_video_keyframe_stats(inventory: Dict[str, Any]) -> tuple[int, int, int]:
    """Return (videos_found, frames_extracted, frames_per_video) from snapshot inventory."""
    meta = inventory.get("basic_video_keyframes_meta") or {}
    ves = inventory.get("visual_evidence_summary") or {}
    videos = int(ves.get("video_keyframes_found") or meta.get("videos_found") or 0)
    frames = int(ves.get("video_keyframes_analyzed") or meta.get("frames_extracted") or 0)
    per = int(meta.get("frames_per_video") or 5)
    return videos, frames, per


def _media_verification_present(
    inventory: Dict[str, Any],
    *,
    has_screenshots: bool,
    grading_mode: str | None = None,
) -> tuple[bool, str]:
    """Full image/video verification (PRO); BASIC uses Word vision + FFmpeg keyframes."""
    emb = inventory.get("embedded_screenshots") or {}
    has_image_assets = (emb.get("count") or 0) > 0 or has_screenshots
    has_video = _submission_has_video(inventory)

    if not has_image_assets and not has_video:
        return True, "—"

    if inventory_is_basic_mode(inventory, grading_mode):
        ves = inventory.get("visual_evidence_summary") or {}
        img_analyzed = int(ves.get("images_analyzed") or 0)
        vk_videos, vk_frames, vk_per = _basic_video_keyframe_stats(inventory)
        images_ok = (not has_image_assets) or bool(inventory.get("vision_analysis_used")) or img_analyzed > 0
        if has_video:
            if vk_frames > 0:
                video_ok = True
                video_label = f"{vk_per} إطار/فيديو × {vk_videos} ({vk_frames} → تحليل بصري)"
            else:
                video_ok = False
                video_label = "فيديو وُجد — لم تُستخرج إطارات FFmpeg"
        else:
            video_ok = True
            video_label = ""

        if images_ok and video_ok:
            if has_video:
                return True, f"عدد الفيديوهات : {vk_videos}"
            return True, f"أساسي: {img_analyzed} صورة (Word/PDF)"

        parts: List[str] = []
        if has_image_assets and not images_ok:
            parts.append("صور لم تُحلَّل")
        if has_video and not video_ok:
            parts.append(video_label or "فيديو لم يُحلَّل")
        return False, " · ".join(parts) if parts else "غير منفّذ"

    gvi = inventory.get("gameplay_video_inference") or {}
    images_ok = (not has_image_assets) or bool(inventory.get("vision_analysis_used"))
    video_ok = (not has_video) or (
        int(gvi.get("videos_analyzed") or 0) > 0
        or int(gvi.get("frames_sampled") or 0) > 0
        or bool(gvi.get("skipped_runtime_verified"))
    )
    verified = images_ok and video_ok
    if verified:
        if has_image_assets and has_video:
            return True, "تم (صور + فيديو)"
        if has_video:
            return True, "تم (فيديو)"
        return True, "تم (صور)"
    return False, "غير منفّذ"


def inventory_is_basic_mode(
    inventory: Dict[str, Any],
    grading_mode: str | None = None,
) -> bool:
    from app.grading_mode_policy import is_fast_grading_mode

    if is_fast_grading_mode(grading_mode):
        return True
    note = str(inventory.get("grading_mode_note_ar") or "")
    if "BASIC" in note.upper() or "وضع BASIC" in note:
        return True
    rt = inventory.get("runtime_observation_report") or {}
    return isinstance(rt, dict) and rt.get("status") == "skipped_fast_mode"


def basic_pro_upgrade_status(
    requirement_ar: str,
    default_status_ar: str,
    *,
    inventory: Dict[str, Any],
    grading_mode: str | None = None,
    present: bool = False,
) -> str:
    if present:
        return default_status_ar
    if requirement_ar not in BASIC_PRO_GATED_REQUIREMENTS_AR:
        return default_status_ar
    if inventory_is_basic_mode(inventory, grading_mode):
        return BASIC_PRO_UPGRADE_STATUS_AR
    return default_status_ar


def sanitize_missing_evidence_diagnostics_for_ui(
    diagnostics: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Drop retired checklist rows and normalize legacy labels for UI display."""
    if not diagnostics or not isinstance(diagnostics, dict):
        return diagnostics
    rows: List[Dict[str, Any]] = []
    for row in diagnostics.get("rows") or []:
        if not isinstance(row, dict):
            continue
        req = str(row.get("requirement_ar") or "")
        if req in _REMOVED_DIAGNOSTIC_REQUIREMENTS_AR:
            continue
        r = dict(row)
        if req == _WORD_REPORT_LEGACY_AR:
            r["requirement_ar"] = _WORD_REPORT_REQUIREMENT_AR
        rows.append(r)
    if rows == list(diagnostics.get("rows") or []):
        return diagnostics
    out = dict(diagnostics)
    out["rows"] = rows
    missing = [r["requirement_ar"] for r in rows if not r.get("present")]
    out["missing_count"] = len(missing)
    out["missing_items_ar"] = missing
    return out


def apply_basic_pro_upgrade_display(
    diagnostics: Optional[Dict[str, Any]],
    inventory: Dict[str, Any],
    grading_mode: str | None = None,
) -> Optional[Dict[str, Any]]:
    """Replace PRO-only missing/runtime labels with upgrade hint in BASIC mode."""
    diagnostics = sanitize_missing_evidence_diagnostics_for_ui(diagnostics)
    if not diagnostics or not isinstance(diagnostics, dict):
        return diagnostics
    if not inventory_is_basic_mode(inventory, grading_mode):
        return diagnostics
    out = dict(diagnostics)
    rows: List[Dict[str, Any]] = []
    for row in diagnostics.get("rows") or []:
        r = dict(row)
        if not r.get("present") and r.get("requirement_ar") in BASIC_PRO_GATED_REQUIREMENTS_AR:
            r["status_ar"] = BASIC_PRO_UPGRADE_STATUS_AR
            r["pro_upgrade_label"] = True
        rows.append(r)
    out["rows"] = rows
    return out


def _existing_paths(submission_paths: Optional[List[str]]) -> List[Path]:
    out: List[Path] = []
    for raw in submission_paths or []:
        try:
            p = Path(raw)
            if p.is_file():
                out.append(p)
        except (OSError, ValueError):
            continue
    return out


def _submission_tree_roots(submission_paths: Optional[List[str]]) -> set[Path]:
    roots: set[Path] = set()
    for fp in _existing_paths(submission_paths):
        roots.add(fp.parent)
        for parent in fp.parents:
            if parent.name.lower() in ("assets", "scripts", "script", "src") or parent.parent == parent:
                roots.add(parent)
                break
    if not roots and submission_paths:
        try:
            roots.add(Path(submission_paths[0]).parent)
        except (OSError, ValueError):
            pass
    return roots


def _should_skip_engine_bundle_path(path: Path) -> bool:
    """Skip Godot/Unity editor bundles mistakenly counted as student source."""
    try:
        from app.godot_submission_utils import is_godot_editor_bundle_path

        return is_godot_editor_bundle_path(path)
    except Exception:
        lower = str(path).lower()
        skip_fragments = (
            "godot_v4.",
            "godot_v3.",
            "godot.windows",
            "godot.mono",
            "أدوات التصدير",
            "export templates",
            "monobleedingedge",
            "embedruntime",
        )
        return any(frag in lower for frag in skip_fragments)


def _count_cs_on_disk(submission_paths: Optional[List[str]]) -> int:
    """Count student source files on disk (.cs, .gd, .gml, …) — excludes engine bundles."""
    roots = _submission_tree_roots(submission_paths)
    counted: set[str] = set()
    skip_dir_names = frozenset(
        {
            "library",
            "temp",
            "obj",
            "bin",
            "node_modules",
            ".godot",
            ".import",
        }
    )
    source_globs = ("*.cs", "*.gd", "*.gml", "*.py", "*.js", "*.ts")
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for pattern in source_globs:
                for src in root.rglob(pattern):
                    if not src.is_file() or _should_skip_engine_bundle_path(src):
                        continue
                    try:
                        rel_parts = src.relative_to(root).parts
                    except ValueError:
                        rel_parts = src.parts
                    if any(part.lower() in skip_dir_names for part in rel_parts):
                        continue
                    key = str(src.resolve()).lower()
                    counted.add(key)
        except OSError:
            continue
    return len(counted)


def _estimate_cs_in_intake(project_profile: Optional[Dict[str, Any]]) -> int:
    profile = project_profile or {}
    si = profile.get("submission_intake") or {}
    rel_paths = si.get("intake_relative_paths") or si.get("relative_paths") or []
    n = sum(
        1
        for p in rel_paths
        if str(p).lower().endswith(".cs")
    )
    if n:
        return n
    unity = (profile.get("unity_evidence") or profile.get("engines") or {})
    if isinstance(unity, dict):
        sig = unity.get("unity_source_signals") or profile.get("runtime_evidence", {}).get(
            "unity_source_signals"
        )
        if isinstance(sig, dict) and sig.get("scripts_analyzed"):
            return int(sig["scripts_analyzed"])
    return 0


def build_extraction_coverage_metrics(
    *,
    submission_paths: Optional[List[str]] = None,
    inventory: Optional[Dict[str, Any]] = None,
    project_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """How much of the project tree was actually ingested for grading."""
    inv = inventory or {}
    src_block = inv.get("source_code") or {}
    ingested = len(src_block.get("files") or [])
    detected_on_disk = _count_cs_on_disk(submission_paths)
    estimated_archive = _estimate_cs_in_intake(project_profile)

    src_block_files = src_block.get("files") or []
    gd_ingested = sum(
        1
        for f in src_block_files
        if str((f or {}).get("ext") or "").lower() == ".gd"
    )
    pck_embedded = [
        f for f in src_block_files
        if (f or {}).get("source_kind") == "godot_pck_embedded"
    ]
    pck_gd_hits = sum(int((f or {}).get("gd_script_hits") or 0) for f in pck_embedded)

    estimated = max(detected_on_disk, estimated_archive, ingested, gd_ingested)
    if estimated <= 0 and ingested > 0:
        estimated = ingested
    if gd_ingested >= 8 and ingested >= gd_ingested:
        estimated = max(estimated, ingested)

    # Godot export-only (.pck/.exe) — do not compare against editor .cs noise.
    if pck_embedded and ingested >= 1:
        estimated = max(1, min(estimated, ingested + max(pck_gd_hits, 1)))
        if pck_gd_hits >= 3:
            estimated = max(estimated, min(pck_gd_hits, 40))

    ratio = round(ingested / estimated, 4) if estimated > 0 else (1.0 if ingested == 0 else 0.0)
    if estimated > ingested and ingested >= 0:
        ratio = round(min(1.0, ingested / estimated), 4)
    if pck_embedded and ingested >= 1 and pck_gd_hits >= 1:
        ratio = max(ratio, min(1.0, pck_gd_hits / max(estimated, pck_gd_hits)))

    if estimated == 0:
        label_ar = "لا ملفات كود في مسارات التسليم"
        weak = False
    elif pck_embedded and ratio >= 0.5:
        label_ar = "تغطية من تصدير Godot (.pck) — لا ملفات .gd منفصلة"
        weak = False
    elif ratio >= 0.5:
        label_ar = "تغطية مقبولة"
        weak = False
    elif ratio >= 0.15:
        label_ar = "تغطية جزئية — تحليل الكود محدود"
        weak = True
    else:
        label_ar = "تغطية ضعيفة — خطر تحليل سطحي"
        weak = True

    doc_files = (inv.get("documentation") or {}).get("files") or []
    doc_ingested = len(doc_files)

    note_extra = ""
    if gd_ingested and estimated > ingested * 3:
        note_extra = " (تقدير المحرر يستثني حزمة Godot المرفقة — الكود الفعلي .gd مُحلَّل.)"

    return {
        "version": 1,
        "detected_cs_files_ingested": ingested,
        "detected_cs_files_on_disk": detected_on_disk,
        "estimated_project_cs_files": estimated,
        "gd_files_ingested": gd_ingested,
        "coverage_ratio": ratio,
        "coverage_label_ar": label_ar,
        "weak_analysis_risk": weak,
        "documents_ingested": doc_ingested,
        "note_ar": (
            f"استُخدم {ingested} ملف كود في التصحيح من ~{estimated} مُقدَّر في المشروع "
            f"(نسبة {ratio * 100:.1f}%). "
            + (
                "قد لا يعكس التحليل كامل المشروع."
                if weak
                else "التغطية كافية للتحليل الساكن."
            )
            + note_extra
        ),
    }


def build_governance_intent_explanation(inventory: Dict[str, Any]) -> Dict[str, Any]:
    """Teacher-facing: why runtime was or was not executed."""
    obs = inventory.get("runtime_observation_report") or {}
    status = obs.get("status") or "unavailable"
    exe = inventory.get("executable_artifacts") or {}
    rt_level = inventory.get("runtime_evidence_level") or {}
    l5 = inventory.get("l5_human_playtest") or {}

    runtime_observed = bool(
        obs.get("runtime_observed")
        or exe.get("runtime_observed")
        or (obs.get("platform_analyses") or [{}])[0]
        .get("signals", {})
        .get("legacy_observation", {})
        .get("runtime_observed")
    )

    partial_promo = bool(
        (obs.get("runtime_evidence_promotion") or {}).get("partial_runtime_verified")
        or obs.get("partial_runtime_verified")
    )
    if status == "completed" and runtime_observed:
        runtime_execution = "Enabled (L4 sandbox — advisory only)"
        runtime_execution_ar = "ملاحظة تشغيل L4 — جزئية/استشارية (ليست فشل النظام)"
        reason = "L4_observation_completed"
        reason_ar = "تمت ملاحظة runtime محكومة — ليست verification مؤسسية"
        academic_ar = "معايير التشغيل تحتاج مراجعة بشرية (L5) قبل أي ترقية سلطة"
        automatic_achievement = False
    elif status in ("failed", "crashed", "timeout") and (runtime_observed or partial_promo):
        runtime_execution = "Partial L4 observation"
        runtime_execution_ar = "تشغيل جزئي — ملاحظة L4 (ليست فشل النظام)"
        reason = "L4_partial_observation"
        reason_ar = "جلسة runtime محكومة — تحقق مؤسسي غير مكتمل"
        academic_ar = "أدلة تشغيل جزئية — مراجعة examiner / Manual Playtest قبل C.P5 Achieved"
        automatic_achievement = False
    elif status == "completed" and not runtime_observed:
        runtime_execution = "Completed without launch proof"
        runtime_execution_ar = "اكتمل التحليل الساكن — دون إثبات تشغيل كامل"
        reason = "L4_static_only"
        reason_ar = "ملاحظة هيكلية/ساكنة — يُفضّل Manual Playtest"
        academic_ar = (
            "التحليل الساكن مكتمل — Manual Playtest مطلوب قبل Achieved "
            "لمعايير التشغيل (C.P5/C.P6)"
        )
        automatic_achievement = False
    elif status == "gated":
        runtime_execution = "Disabled by governance"
        runtime_execution_ar = "معطّل بحكم الحوكمة"
        reason = obs.get("reason") or "GOVERNANCE_FREEZE_v1_active"
        reason_ar = obs.get("gate_ar") or (
            "Stage 5 Pilot — L4 sandbox مقفول حتى Verdict مؤسسي (GOVERNANCE_FREEZE_v2)"
        )
        academic_ar = (
            "معايير runtime (مثل C.P5/C.P6) تتطلب Manual Playtest من المعلّم "
            "أو فتح L4 بعد Epoch Workshop Review"
        )
        automatic_achievement = False
    elif exe.get("files"):
        runtime_execution = "Not executed (policy / unavailable)"
        runtime_execution_ar = "لم يُنفَّذ (سياسة أو عدم توفر)"
        reason = obs.get("reason") or "sandbox_not_run"
        reason_ar = "ملفات exe رُصدت — التشغيل الآلي غير مُفعَّل أو غير متاح"
        academic_ar = "وجود exe ≠ إثبات تشغيل — Manual Playtest مطلوب"
        automatic_achievement = False
    else:
        runtime_execution = "Not applicable"
        runtime_execution_ar = "غير متوفر"
        reason = "no_executable_detected"
        reason_ar = "لم يُرصد ملف تنفيذي"
        academic_ar = "لا مسار runtime — التقييم يعتمد على التوثيق والكود الساكن"
        automatic_achievement = False

    if l5.get("pass") is True:
        academic_ar += " — تم تسجيل L5 Manual Playtest (مراجعة بشرية)."

    return {
        "version": 1,
        "runtime_execution": runtime_execution,
        "runtime_execution_ar": runtime_execution_ar,
        "reason": reason,
        "reason_ar": reason_ar,
        "academic_implication_ar": academic_ar,
        "automatic_achievement_allowed": automatic_achievement,
        "authority_level": rt_level.get("authority") or "none",
        "runtime_evidence_level": rt_level.get("level", 0),
        "decision_package_url": obs.get("decision_package_url") or "/governance/l4-decision",
        "not_a_system_failure_ar": (
            "عدم التشغيل التلقائي **قرار حوكمة** — ليس عطلاً في النظام."
            if status == "gated"
            else ""
        ),
    }


def build_missing_evidence_diagnostics(
    inventory: Dict[str, Any],
    *,
    project_profile: Optional[Dict[str, Any]] = None,
    grading_mode: str | None = None,
) -> Dict[str, Any]:
    """Structured checklist: required vs present for BTEC game submissions."""
    doc = inventory.get("documentation") or {}
    src = inventory.get("source_code") or {}
    exe = inventory.get("executable_artifacts") or {}
    testing = inventory.get("testing_evidence") or {}
    emb = inventory.get("embedded_screenshots") or {}
    rt = inventory.get("runtime_artifacts") or {}
    coverage = inventory.get("extraction_coverage") or {}
    obs = inventory.get("runtime_observation_report") or {}
    l5 = inventory.get("l5_human_playtest") or {}

    has_exe = bool(exe.get("files") or rt.get("executables_detected") or inventory.get("has_executable_artifacts"))
    has_scratch = bool(
        rt.get("scratch_detected")
        or (rt.get("scratch_signals") or {}).get("detected")
        or any(
            str((f or {}).get("ext") or "").lower() in (".sb3", ".sb2", ".sb")
            or (f or {}).get("artifact_kind") == "scratch_project"
            for f in (exe.get("files") or [])
        )
    )
    has_exe = (has_exe or has_scratch)
    doc_block = inventory.get("documentation") or {}
    has_doc = doc_block.get("status") in ("analyzed", "detected") and bool(doc_block.get("files"))
    if not has_doc and int(doc_block.get("file_count") or 0) > 0:
        has_doc = True
    has_word = has_doc and any(
        f.get("ext", "").lower() in (".docx", ".doc", ".pdf", ".odt")
        for f in doc_block.get("files") or [{"ext": ".docx"}]
    )
    has_src = (
        (src.get("status") in ("analyzed", "detected") and bool(src.get("files")))
        or bool(inventory.get("has_source_code_artifacts"))
        or has_scratch
    )
    has_pck_src = any(
        (f or {}).get("source_kind") == "godot_pck_embedded"
        for f in (src.get("files") or [])
    )
    cov_ratio = float(coverage.get("coverage_ratio") or 0)
    weak_src = bool(coverage.get("weak_analysis_risk")) and cov_ratio < 0.5
    has_screenshots = (
        (emb.get("count") or 0) > 0
        or rt.get("screenshot_folder_detected")
        or (rt.get("runtime_screenshot_count") or 0) > 0
    )
    has_gamemaker = str(obs.get("engine") or "").lower() == "gamemaker" or bool(
        obs.get("gamemaker_runtime_verification")
        or obs.get("gamemaker_artifact_analysis")
        or obs.get("gamemaker_gameplay_replay")
    )
    if not has_gamemaker:
        for f in (src.get("files") or []):
            ext = str((f or {}).get("ext") or "").lower()
            if ext in (".yyp", ".gml", ".yy"):
                has_gamemaker = True
                break
    ves = inventory.get("visual_evidence_summary") or {}
    img_found = int(ves.get("images_found") or emb.get("count") or 0)
    img_submitted = int(ves.get("images_submitted") or emb.get("vision_submitted_count") or 0)
    img_analyzed = int(ves.get("images_analyzed") or emb.get("vision_analyzed_count") or 0)
    img_used = int(ves.get("images_used_in_decision") or emb.get("images_used_in_decision") or 0)
    vision_attempted = bool(ves.get("vision_attempted"))
    vision_failed = ves.get("vision_status") == "failed"
    if img_found > 0 and not has_screenshots:
        has_screenshots = True

    from app.visual_evidence_registry import (
        authority_testing_available,
        get_criterion_authority,
        submission_testing_evidence_present,
    )

    p6_auth = get_criterion_authority(inventory, "P6")
    if inventory.get("criterion_authority"):
        has_testing = authority_testing_available(inventory)
    else:
        has_testing = submission_testing_evidence_present(
            inventory,
            criteria_results=inventory.get("criteria_results") or [],
        )
        p6_auth = get_criterion_authority(inventory, "P6")
    cp6_achieved = any(
        isinstance(cr, dict)
        and str(cr.get("criteria_level") or "").upper().endswith("P6")
        and cr.get("achieved")
        for cr in (inventory.get("criteria_results") or [])
    )
    legacy_obs = (obs.get("platform_analyses") or [{}])[0].get("signals", {}).get(
        "legacy_observation", {}
    ) if obs.get("platform_analyses") else {}
    if not isinstance(legacy_obs, dict):
        legacy_obs = {}
    nested_observed = legacy_obs.get("runtime_observed") or (
        (obs.get("signals") or {}).get("legacy_observation") or {}
    ).get("runtime_observed")

    rv = inventory.get("runtime_validation") or obs.get("runtime_validation") or {}
    smoke = (rv.get("functional_smoke") or {}) if isinstance(rv, dict) else {}
    smoke_pass = smoke.get("functional_smoke_pass") is True
    runtime_method = str(
        obs.get("observation_mode")
        or obs.get("runtime_method")
        or (obs.get("platform_analyses") or [{}])[0]
        .get("signals", {})
        .get("runtime_method")
        or ""
    )
    structure_only = runtime_method in (
        "godot_static_analysis",
        "godot_apk_pck_static_scan",
    ) or exe.get("status") in (
        "detected_not_executed",
        "observed_structure_only",
    )
    launch_attempted = obs.get("game_launch_attempted")
    if launch_attempted is False:
        structure_only = True
    sig0 = (obs.get("platform_analyses") or [{}])[0].get("signals") or {}
    if (sig0.get("pck_pairing") or {}).get("error") == "no_donor_exe_for_pck":
        structure_only = True
    if (sig0.get("pck_smoke") or {}).get("error") == "godot_binary_not_configured":
        structure_only = True
    if sig0.get("runtime_method") in ("godot_static_analysis", "godot_apk_pck_static_scan"):
        structure_only = True
    if (
        obs.get("status") in ("completed", "partial")
        and obs.get("runtime_verified") is not True
        and smoke.get("functional_smoke_pass") is not True
        and not l5.get("pass")
    ):
        structure_only = True

    runtime_verified = bool(
        l5.get("pass")
        or (
            smoke_pass
            and smoke.get("reason") not in (
                "observation_completed",
                "structure_only_no_game_launch",
                "game_not_launched",
                "completed_without_launch_evidence",
            )
        )
        or (
            obs.get("runtime_verified") is True
            and not structure_only
        )
        or (
            exe.get("runtime_verified") is True
            and not structure_only
        )
    )
    runtime_observed = bool(
        runtime_verified
        or nested_observed
        or obs.get("runtime_observed")
        or (structure_only and (has_exe or obs.get("status") in ("partial", "completed")))
    )

    def _neg(requirement_ar: str, default_ar: str, present: bool) -> str:
        return basic_pro_upgrade_status(
            requirement_ar,
            default_ar,
            inventory=inventory,
            grading_mode=grading_mode,
            present=present,
        )

    media_verify_present, media_verify_status = _media_verification_present(
        inventory,
        has_screenshots=has_screenshots,
        grading_mode=grading_mode,
    )

    _exe_not_run_ar = (
        "⚠ ملف GameMaker (.exe) موجود — لم يُشغَّل smoke test على الخادم"
        if has_gamemaker
        else (
            "⚠ ملف Scratch (.sb3) موجود — لم يُشغَّل static graph على الخادم"
            if has_scratch
            else "⚠ ملف build/APK موجود — لم يُشغَّل على الخادم"
        )
    )
    _exe_block_ar = (
        "ملف exe موجود لكن لم يُختبر تشغيله — C.P5 يحتاج playtest أو تفعيل L4"
        if has_gamemaker
        else (
            "ملف Scratch موجود لكن لم يُختبر — C.P5/C.P6 تحتاج playtest أو Scratch runtime"
            if has_scratch
            else "ملف موجود لكن لم يُختبر تشغيله — C.P5 يحتاج playtest أو Godot binary"
        )
    )
    rows = [
        {
            "requirement_ar": "ملف اللعبة (exe/build)",
            "status_ar": (
                _exe_not_run_ar
                if has_exe and structure_only
                else (
                    "⚠ الملف موجود — لم يُثبت تشغيل اللعبة"
                    if has_exe and not runtime_verified
                    else _neg(
                        "ملف اللعبة (exe/build)",
                        PRESENT_STATUS_AR if has_exe else "مفقود",
                        has_exe,
                    )
                )
            ),
            "present": has_exe and runtime_verified,
            "blocks_achievement_ar": (
                _exe_block_ar
                if has_exe and structure_only
                else ("" if has_exe else "C.P5 — لا build")
            ),
        },
        {
            "requirement_ar": _WORD_REPORT_REQUIREMENT_AR,
            "status_ar": PRESENT_STATUS_AR if has_word else "مفقود",
            "present": has_word,
            "blocks_achievement_ar": "" if has_word else "B.P3–C.P7 — لا أدلة كتابية",
        },
        {
            "requirement_ar": "أدلة الاختبار (خطط/سجلات)",
            "status_ar": (
                f"{PRESENT_STATUS_AR} — أدلة اختبار (Authority C.P6 ✓)"
                if has_testing
                and cp6_achieved
                and str(testing.get("status") or "") in ("partial", "detected", "analyzed", "documented")
                else (
                    "أدلة اختبار موجودة — لم يُمنح C.P6 (Gate/Governance)"
                    if has_testing
                    and not cp6_achieved
                    else (
                        BASIC_PRO_UPGRADE_STATUS_AR
                        if has_testing
                        else _neg("أدلة الاختبار (خطط/سجلات)", "مفقود", False)
                    )
                )
            ),
            "present": has_testing and cp6_achieved,
            "blocks_achievement_ar": (
                ""
                if has_testing
                else "C.P6 — لا testing evidence"
            ),
            "authority_source": "criterion_authority.P6.testing_authority_available",
            "authority_decision_basis": p6_auth.get("decision_basis") or "",
        },
        {
            "requirement_ar": "حالة الأدلة البصرية (Vision)",
            "status_ar": (
                f"تم تدقيق وتحليل {img_found} صورة"
                if img_found > 0 and img_analyzed > 0
                else (
                    f"⚠ فشل Vision — {ves.get('vision_error') or 'empty_vision_response'}"
                    if vision_failed
                    else (
                        "⚠ وُجدت صور — لم تحلل"
                        if img_found > 0
                        else "—"
                    )
                )
            ),
            "present": img_analyzed > 0 or vision_attempted,
            "blocks_achievement_ar": (
                ""
                if img_analyzed > 0 or img_found == 0
                else (
                    f"Vision failed — {ves.get('vision_error') or 'empty_vision_response'}"
                    if vision_failed
                    else "الصور وُجدت لكن لم تُحلَّل — لا تدخل قرار المعايير البصرية"
                )
            ),
        },
        {
            "requirement_ar": "التحقق من الصور والفيديو",
            "status_ar": _neg(
                "التحقق من الصور والفيديو",
                media_verify_status,
                media_verify_present,
            ),
            "present": media_verify_present,
            "blocks_achievement_ar": (
                ""
                if media_verify_present
                else "C.P5 — تحليل بصري كامل (Vision + فيديو) مطلوب"
            ),
        },
        {
            "requirement_ar": "تغطية الكود المصدري",
            "status_ar": (
                f"{PRESENT_STATUS_AR} (مشروع Scratch)"
                if has_scratch
                else (
                    "ضعيفة"
                    if weak_src and has_src and not has_pck_src
                    else (
                        f"{PRESENT_STATUS_AR} (تصدير Godot .pck)"
                        if has_pck_src and not has_src
                        else (PRESENT_STATUS_AR if has_src else "مفقود")
                    )
                )
            ),
            "present": has_scratch or (has_src and not weak_src) or has_pck_src,
            "blocks_achievement_ar": (
                ""
                if has_scratch
                else (
                    "تحليل الكود جزئي فقط — راجع extraction coverage"
                    if weak_src and not has_pck_src
                    else (
                        ""
                        if has_src or has_pck_src
                        else "لا كود مُستخرج للتحليل"
                    )
                )
            ),
        },
        {
            "requirement_ar": "التحقق من التشغيل (runtime)",
            "status_ar": (
                f"{PRESENT_STATUS_AR} — موثّق (L5 تشغيل بشري)"
                if l5.get("pass")
                else (
                    f"{PRESENT_STATUS_AR} — ملاحظة L4 جزئية (ليست فشل التصحيح)"
                    if runtime_verified and obs.get("status") in ("failed", "crashed", "timeout")
                    else (
                        f"{PRESENT_STATUS_AR} — ملاحظة L4 (تشغيل آلية، ليس تحققاً بشرياً L5)"
                        if runtime_verified
                        else (
                            (
                                "⚠ مشروع GameMaker — اللعبة لم تُشغَّل (تحقق من .exe و AI_GRADER_ENABLE_L4=1)"
                                if has_gamemaker
                                else (
                                    "⚠ مشروع Scratch (.sb3) — لم يُشغَّل static graph (PRO Scratch runtime)"
                                    if has_scratch
                                    else "⚠ APK/PCK مُفحوص هيكلياً — اللعبة لم تُشغَّل (اضبط AI_GRADER_GODOT_BIN أو exe+ pck)"
                                )
                            )
                            if structure_only and runtime_observed
                            else _neg(
                                "التحقق من التشغيل (runtime)",
                                "غير منفّذ — لم تُشغَّل اللعبة",
                                runtime_verified,
                            )
                        )
                    )
                )
            ),
            "present": runtime_verified,
            "blocks_achievement_ar": (
                (
                    "C.P5/C.P6/C.M3/C.D3 — التشغيل آلياً (L4) لا يُعادل لعباً فعلياً؛ "
                    "يُطلب فيديو gameplay من داخل اللعبة أو اختبار بشري (L5)."
                )
                if runtime_verified and not l5.get("pass")
                else (
                    (
                        "اللعبة لم تُشغَّل على الخادم — C.P5/C.P7 تحتاج playtest أو تفعيل L4 لـ GameMaker"
                        if has_gamemaker
                        else (
                            "ملف Scratch موجود — C.P5/C.P6 تحتاج Scratch runtime أو playtest موثّق"
                            if has_scratch
                            else "اللعبة لم تُشغَّل على الخادم — C.P5/C.P7 تحتاج playtest أو Godot binary"
                        )
                    )
                    if structure_only
                    else "C.P5/C.P6/C.P7 — Manual Playtest أو L4 sandbox مطلوب"
                )
            ),
        },
    ]

    # Text Suppression: avoid positive phrasing if evidence has not reached L5.
    runtime_row = next(
        (r for r in rows if r.get("requirement_ar") == "التحقق من التشغيل (runtime)"),
        None,
    )
    media_row = next(
        (r for r in rows if r.get("requirement_ar") == "التحقق من الصور والفيديو"),
        None,
    )
    mechanics = obs.get("mechanics_verification") or inventory.get("mechanics_verification") or {}
    l5_human = bool(l5.get("pass"))
    mechanics_level = str(mechanics.get("mechanics_level") or "").upper()
    reached_l5 = l5_human or mechanics_level == "L5"
    fast_mode = (grading_mode or "").strip().lower() in ("fast", "basic", "standard")
    if runtime_row and not reached_l5 and not fast_mode:
        runtime_row["status_ar"] = "ملاحظة تشغيل L4/L3 فقط — لا تحقق gameplay نهائي بدون L5"
        runtime_row["present"] = False
        runtime_row["blocks_achievement_ar"] = (
            "C.P5/C.P6/C.M3/C.D3 — يلزم إثبات ميكانيك اللعب (Jump/Score/Win-Lose) عبر L5."
        )
    runtime_signal_present = bool(obs.get("runtime_observed") or obs.get("runtime_verified"))
    if media_row and not reached_l5 and media_row.get("present") and runtime_signal_present and not fast_mode:
        media_row["status_ar"] = "تحليل بصري استشاري — لا يثبت صحة الميكانيك بدون L5"
        media_row["blocks_achievement_ar"] = (
            "الصور/الفيديو وحدها غير كافية لاعتماد الإنجاز دون تحقق ميكانيكي L5."
        )

    missing = [r["requirement_ar"] for r in rows if not r.get("present")]
    core_missing = [
        m
        for m in missing
        if m not in ("تغطية الكود المصدري", "التحقق من التشغيل (runtime)")
    ]
    if not missing:
        summary_ar = "أدلة أساسية موجودة — راجع المعايير الفردية للتفاصيل."
    elif core_missing:
        summary_ar = (
            "التسليم يفتقر إلى أدلة BTEC جوهرية — راجع المعايير والتصنيف المؤسسي."
        )
    elif has_exe or has_doc or runtime_verified:
        summary_ar = (
            "أدلة تشغيل/توثيق موجودة — تغطية الكود أو runtime قد تكون جزئية؛ "
            "لا يُخفَّض التقييم تلقائياً إلى U بسبب missing source فقط."
        )
    else:
        summary_ar = "راجع المعايير الفردية والتصنيف المؤسسي."

    return {
        "version": 1,
        "rows": rows,
        "missing_count": len(missing),
        "missing_items_ar": missing,
        "summary_ar": summary_ar,
    }


def attach_academic_explainability(
    inventory: Dict[str, Any],
    *,
    submission_paths: Optional[List[str]] = None,
    project_profile: Optional[Dict[str, Any]] = None,
    grading_mode: str | None = None,
) -> Dict[str, Any]:
    """Populate explainability blocks on artifact inventory."""
    inventory["extraction_coverage"] = build_extraction_coverage_metrics(
        submission_paths=submission_paths,
        inventory=inventory,
        project_profile=project_profile,
    )
    inventory["governance_intent"] = build_governance_intent_explanation(inventory)
    inventory["missing_evidence_diagnostics"] = build_missing_evidence_diagnostics(
        inventory,
        project_profile=project_profile,
        grading_mode=grading_mode,
    )
    return inventory


def format_explainability_for_grading(inventory: Dict[str, Any]) -> str:
    """Bounded block for AI grader — teacher-audit friendly."""
    gov = inventory.get("governance_intent") or {}
    diag = inventory.get("missing_evidence_diagnostics") or {}
    cov = inventory.get("extraction_coverage") or {}
    if not gov and not diag:
        return ""

    lines = [
        "───────────────────────────────────────────────────────────",
        "[Explainability — governance intent | missing evidence | coverage]",
        "───────────────────────────────────────────────────────────",
    ]
    if gov:
        lines.append(f"• Runtime execution: {gov.get('runtime_execution_ar', '')}")
        lines.append(f"• Reason: {gov.get('reason_ar', '')}")
        if gov.get("not_a_system_failure_ar"):
            lines.append(f"• {gov['not_a_system_failure_ar']}")
        lines.append(f"• Academic implication: {gov.get('academic_implication_ar', '')}")
        lines.append(
            f"• Automatic achievement allowed: "
            f"{'Yes' if gov.get('automatic_achievement_allowed') else 'No'}"
        )
    if cov:
        lines.append(
            f"• Code extraction coverage: {cov.get('detected_cs_files_ingested', 0)}/"
            f"{cov.get('estimated_project_cs_files', 0)} "
            f"({float(cov.get('coverage_ratio', 0)) * 100:.1f}%) — {cov.get('coverage_label_ar', '')}"
        )
    if diag.get("rows"):
        lines.append("• Missing evidence checklist:")
        for row in diag["rows"]:
            mark = "✓" if row.get("present") else "✗"
            lines.append(f"  {mark} {row.get('requirement_ar')}: {row.get('status_ar')}")
        if diag.get("summary_ar"):
            lines.append(f"• Summary: {diag['summary_ar']}")
    lines.append("───────────────────────────────────────────────────────────\n")
    return "\n".join(lines) + "\n"


