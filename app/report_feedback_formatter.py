"""
Format criterion feedback for human-readable Word/PDF reports (Arabic-first).
"""
from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional, Tuple

_RUNTIME_HEADER_RE = re.compile(
    r"^[✅❌⏸]\s*\[(Runtime observation L4|Runtime adjudication|Runtime partial)\]\s*"
    r"(?P<body>.*?)(?:\n\n|\Z)",
    re.DOTALL | re.MULTILINE,
)

_VERDICT_AR = {
    "operational support strong": "قوي — أدلة تشغيل كافية ضمن sandbox (L4)",
    "operational_support_strong": "قوي — أدلة تشغيل كافية ضمن sandbox (L4)",
    "operational support partial": "جزئي — التحقق الآلي غير مكتمل",
    "operational_support_partial": "جزئي — التحقق الآلي غير مكتمل",
    "insufficient": "غير كافٍ — لا يكفي لإثبات التشغيل",
}

_REASON_AR = {
    "Godot PCK صالح — scenes/assets مُرصدة": "تم التحقق من حزمة Godot (PCK) ووجود مشاهد/أصول.",
    "APK structure صالح (dex+manifest)": "تم التحقق من بنية APK (ملفات dex و manifest).",
    "EXE smoke/launch observation": "تشغيل تجريبي قصير لملف EXE للتحقق من الإقلاع.",
    "EXE launch attempt + APK/PCK corroboration": "محاولة تشغيل EXE مع تأكيد APK/PCK.",
    "Godot export detected": "رُصد تصدير Godot (exe/pck/apk).",
    "testing documentation present": "وُجدت وثائق/أدلة اختبار (استبيان، تقارير، إلخ).",
    "runnable artifact smoke-stable": "البرنامج القابل للتشغيل بقي مستقراً خلال نافذة المراقبة.",
    "crash/early exit observed": "رُصد تعطل أو إغلاق مبكر أثناء التشغيل التجريبي.",
}


def _translate_reason(raw: str) -> str:
    raw = (raw or "").strip().rstrip(".")
    if not raw:
        return ""
    return _REASON_AR.get(raw, raw)


def split_runtime_feedback(feedback: str) -> Tuple[str, str]:
    """Return (runtime_block, assessor_comment)."""
    text = (feedback or "").strip()
    if not text:
        return "", ""
    m = _RUNTIME_HEADER_RE.match(text)
    if not m:
        return "", text
    runtime = m.group(0).strip()
    rest = text[m.end() :].strip()
    return runtime, rest


def _parse_runtime_body(runtime_block: str) -> Tuple[str, str, List[str]]:
    body = runtime_block
    body = re.sub(
        r"^[✅❌⏸]\s*\[(Runtime observation L4|Runtime adjudication|Runtime partial)\]\s*",
        "",
        body,
    ).strip()
    body = re.sub(r"Observations collected under controlled conditions\.?\s*", "", body).strip()

    level = ""
    reasons: List[str] = []
    verdict_key = ""

    if ":" in body:
        head, tail = body.split(":", 1)
        level = head.strip()
        tail = tail.strip()
        if "—" in tail:
            verdict_part, reason_part = tail.split("—", 1)
            verdict_key = verdict_part.strip().lower()
            reasons = [p.strip() for p in reason_part.split(";") if p.strip()]
        else:
            verdict_key = tail.lower()
    else:
        reasons = [p.strip() for p in body.split(";") if p.strip()]

    return level, verdict_key, reasons


def format_runtime_section(runtime_block: str) -> str:
    if not runtime_block:
        return ""
    level, verdict_key, reasons = _parse_runtime_body(runtime_block)

    lines = ["أدلة التشغيل المسجّلة (L4 — sandbox، للمراجعة):"]
    verdict_ar = _VERDICT_AR.get(verdict_key, verdict_key or "—")
    if level:
        lines.append(f"• المعيار: {level}")
    if verdict_ar and verdict_ar != "—":
        lines.append(f"• مستوى الدعم التشغيلي: {verdict_ar}")
    for r in reasons:
        tr = _translate_reason(r)
        if tr:
            lines.append(f"• {tr}")
    lines.append(
        "• تنويه: L4 = ملاحظة آلية ضمن بيئة محكومة — لا تُعد تحققاً بشرياً (L5)."
    )
    return "\n".join(lines)


def _runtime_engine_label_ar(engine_id: str) -> str:
    return {
        "gamemaker": "GameMaker",
        "godot": "Godot",
        "scratch": "Scratch",
        "unity": "Unity",
    }.get((engine_id or "").strip().lower(), "اللعبة")


def ensure_runtime_outcome_engine(
    outcome: Optional[Dict[str, Any]], *, engine_id: str = ""
) -> Dict[str, Any]:
    """Add engine identity to legacy persisted runtime outcomes when available."""
    out = dict(outcome or {})
    resolved = str(out.get("engine_id") or engine_id or "").strip().lower()
    out["engine_id"] = resolved
    out["engine_label_ar"] = out.get("engine_label_ar") or _runtime_engine_label_ar(resolved)
    return out


def build_runtime_outcome(
    gv: Optional[Dict[str, Any]] = None,
    gate: Optional[Dict[str, Any]] = None,
    *,
    agent_play_label_ar: Optional[str] = None,
    engine_id: str = "",
) -> Dict[str, Any]:
    """Structured runtime outcome for Word/UI (no raw JSON)."""
    gv = gv or {}
    gate = gate or {}
    criterion_pass = gate.get("criterion_pass") or {}
    failure_code = str(gv.get("failure_reason_code") or "").strip() or None
    failure_ar = str(gv.get("failure_reason_ar") or "").strip() or None
    gameplay_entered = gv.get("gameplay_entered")
    l4_level = gv.get("l4_level") or gv.get("automated_l4_level") or gate.get("l4_level")
    evidence = gv.get("failure_evidence") if isinstance(gv.get("failure_evidence"), dict) else {}

    if gameplay_entered is True and not failure_code:
        agent_result_ar = agent_play_label_ar or "نعم — دخل gameplay (L4)"
    elif failure_code or failure_ar:
        agent_result_ar = agent_play_label_ar or "لا — لم يُثبت gameplay"
    else:
        agent_result_ar = agent_play_label_ar or "غير محدد — لم تُكتمل ملاحظة التشغيل"

    evidence_lines: List[str] = []
    if failure_code:
        evidence_lines.append(f"رمز التصنيف: {failure_code}")
    if l4_level:
        evidence_lines.append(f"مستوى L4: {l4_level}")
    if gameplay_entered is not None:
        evidence_lines.append(
            f"gameplay_entered: {'نعم' if gameplay_entered else 'لا'}"
        )
    menu = gv.get("menu_navigation") if isinstance(gv.get("menu_navigation"), dict) else {}
    if menu.get("status"):
        evidence_lines.append(f"حالة القائمة: {menu.get('status')}")
    if evidence.get("process_crashed"):
        evidence_lines.append("تعطل العملية أثناء المراقبة")
    if evidence.get("server_dialog_detected"):
        evidence_lines.append("حوار شبكة/خادم مُكتشف")
    retry_count = len(gv.get("godot_retry_attempts") or [])
    if retry_count:
        evidence_lines.append(f"محاولات Godot retry: {retry_count}")

    p5_open = bool(criterion_pass.get("P5"))
    p6_open = bool(criterion_pass.get("P6"))
    impact_lines = [
        f"C.P5: {'Gate مفتوح — يمكن منح المعيار عند استيفاء أدلة الملفات' if p5_open else 'Gate مغلق — يتطلب gameplay L4'}",
        f"C.P6: {'Gate مفتوح — يتطلب وثائق اختبار + L4' if p6_open else 'Gate مغلق — يتطلب gameplay L4 ووثائق اختبار'}",
    ]

    return {
        "engine_id": (engine_id or "").strip().lower(),
        "engine_label_ar": _runtime_engine_label_ar(engine_id),
        "agent_play_result_ar": agent_result_ar,
        "final_failure_reason_ar": failure_ar or ("—" if not failure_code else failure_code),
        "failure_reason_code": failure_code,
        "evidence_summary_ar": evidence_lines,
        "impact_cp5_cp6_ar": impact_lines,
        "gameplay_entered": gameplay_entered,
        "l4_level": l4_level,
        "criterion_pass_p5": p5_open,
        "criterion_pass_p6": p6_open,
    }


# Compatibility aliases for persisted snapshots created before runtime outcomes
# carried their engine identity.
build_godot_runtime_outcome = build_runtime_outcome


def format_runtime_outcome_ar(outcome: Optional[Dict[str, Any]] = None) -> str:
    """Arabic Word block: agent result, failure, evidence, C.P5/C.P6 impact."""
    if not outcome:
        return ""
    lines = [
        f"نتيجة Agent play ({outcome.get('engine_label_ar') or 'اللعبة'}):",
        f"• {outcome.get('agent_play_result_ar') or '—'}",
        "",
        "سبب الفشل النهائي:",
        f"• {outcome.get('final_failure_reason_ar') or '—'}",
        "",
        "ملخص الأدلة (runtime — ليس أدلة ملفات):",
    ]
    for item in outcome.get("evidence_summary_ar") or []:
        lines.append(f"• {item}")
    if not outcome.get("evidence_summary_ar"):
        lines.append("• —")
    lines.extend(["", "الأثر على C.P5 / C.P6:"])
    for item in outcome.get("impact_cp5_cp6_ar") or []:
        lines.append(f"• {item}")
    lines.append(
        "• تنويه: أدلة الملفات (B.P3/B.P4) منفصلة عن أدلة التشغيل (C.P5/C.P6)."
    )
    return clean_report_text("\n".join(lines))


format_godot_runtime_outcome_ar = format_runtime_outcome_ar


def format_criterion_feedback_for_report(
    feedback: str,
    *,
    runtime_note_ar: Optional[str] = None,
    achieved: Optional[bool] = None,
    awardable: Optional[bool] = None,
    godot_runtime_outcome: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build teacher-readable Arabic sections. When governance blocked achievement,
    only the institutional voice is shown (no AI assessor praise).
    """
    from app.btec_criteria_governance import strip_btec_governance_feedback

    feedback = strip_btec_governance_feedback(feedback or "")
    runtime_block, assessor = split_runtime_feedback(feedback)
    if runtime_note_ar and not runtime_block:
        runtime_block = runtime_note_ar

    institutional_only = achieved is False or (
        achieved is True and awardable is False
    )

    parts: List[str] = []
    if institutional_only:
        body = assessor or feedback
        if body:
            parts.append("قرار الحوكمة المؤسسية:")
            parts.append(body)
    else:
        if assessor:
            parts.append("تعليق المقيّم:")
            parts.append(assessor)

    runtime_fmt = format_runtime_section(runtime_block) if runtime_block else ""
    if not runtime_fmt and runtime_note_ar and not institutional_only:
        runtime_fmt = runtime_note_ar
    if runtime_fmt and not institutional_only:
        parts.append(runtime_fmt)

    godot_fmt = format_godot_runtime_outcome_ar(godot_runtime_outcome)
    if godot_fmt and not institutional_only:
        parts.append(godot_fmt)

    if not parts:
        return clean_report_text((feedback or "").strip())
    return clean_report_text("\n\n".join(parts))


def criterion_report_display(
    criteria: dict,
) -> tuple[str, str, str, str]:
    """Return (icon, status_text, card_bg, card_border) for Word report cards."""
    human_review = (criteria.get("achievement_authority") or "") == "HUMAN_REVIEW_REQUIRED"
    achieved = bool(criteria.get("achieved", False))
    awardable = criteria.get("awardable", achieved)

    if human_review:
        return "⏸", "التحقق الآلي غير مكتمل (Automated Verification Incomplete)", "FEF3C7", "F59E0B"
    if achieved and awardable:
        return "✅", "تحقق المعيار (Achieved)", "D1FAE5", "10B981"
    if achieved and not awardable:
        return "⏸", "تحقق المعيار — معايير سابقة ناقصة", "FEF3C7", "F59E0B"
    return "❌", "لم يتحقق المعيار (Not Achieved)", "FEE2E2", "EF4444"


def strip_embedded_json_blocks(text: str) -> str:
    """Remove raw AI JSON blobs accidentally appended to teacher-facing feedback."""
    if not text:
        return ""
    for marker in ('```json', '{"criteria_evaluation"', '{"criteria_results"'):
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx].rstrip()
    return text


def clean_report_text(text: str) -> str:
    """
    Decode HTML/XML entities (&apos; &quot; &amp; …) and normalize common artifacts
    before writing human-facing Word/PDF content.
    """
    if text is None:
        return ""
    t = (text).strip()
    if not t:
        return ""
    # Decode standard + common XML entities (may appear twice if over-escaped)
    for _ in range(2):
        unescaped = html.unescape(t)
        if unescaped == t:
            break
        t = unescaped
    t = (
        t.replace("&apos;", "'")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&#x27;", "'")
    )
    # «quoted Arabic» reads better in RTL than ASCII '…'
    def _arabic_quote(m: re.Match[str]) -> str:
        inner = m.group(1)
        if any("\u0600" <= c <= "\u06FF" for c in inner):
            return f"«{inner}»"
        return m.group(0)

    t = re.sub(r"'([^']{1,120})'", _arabic_quote, t)
    return strip_embedded_json_blocks(t.strip())
