"""
Format criterion feedback for human-readable Word/PDF reports (Arabic-first).
"""
from __future__ import annotations

import html
import re
from typing import List, Optional, Tuple

_RUNTIME_HEADER_RE = re.compile(
    r"^[✅❌⏸]\s*\[(Runtime observation L4|Runtime adjudication|Runtime partial)\]\s*"
    r"(?P<body>.*?)(?:\n\n|\Z)",
    re.DOTALL | re.MULTILINE,
)

_VERDICT_AR = {
    "operational support strong": "قوي — أدلة تشغيل كافية ضمن sandbox (L4)",
    "operational_support_strong": "قوي — أدلة تشغيل كافية ضمن sandbox (L4)",
    "operational support partial": "جزئي — يحتاج مراجعة بشرية",
    "operational_support_partial": "جزئي — يحتاج مراجعة بشرية",
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


def format_criterion_feedback_for_report(
    feedback: str,
    *,
    runtime_note_ar: Optional[str] = None,
) -> str:
    """
    Build teacher-readable Arabic sections: assessor comment first, then runtime evidence.
    """
    from app.btec_criteria_governance import strip_btec_governance_feedback

    feedback = strip_btec_governance_feedback(feedback or "")
    runtime_block, assessor = split_runtime_feedback(feedback)
    if runtime_note_ar and not runtime_block:
        runtime_block = runtime_note_ar

    parts: List[str] = []
    if assessor:
        parts.append("تعليق المقيّم:")
        parts.append(assessor)

    runtime_fmt = format_runtime_section(runtime_block) if runtime_block else ""
    if not runtime_fmt and runtime_note_ar:
        runtime_fmt = runtime_note_ar
    if runtime_fmt:
        parts.append(runtime_fmt)

    if not parts:
        return clean_report_text((feedback or "").strip())
    return clean_report_text("\n\n".join(parts))


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
    return t.strip()
