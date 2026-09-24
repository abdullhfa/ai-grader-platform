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
    "operational support partial": "جزئي — يحتاج مراجعة بشرية",
    "operational_support_partial": "جزئي — يحتاج مراجعة بشرية",
    "insufficient": "غير كافٍ — لا يكفي لإثبات التشغيل",
    "partial corroboration": "دعم جزئي مع تعزيز أدلة إضافية",
    "partial_corroboration": "دعم جزئي مع تعزيز أدلة إضافية",
    "static corroborated": "معتمد — تشغيل ناجح + أدلة كود حتمية",
    "static_corroborated": "معتمد — تشغيل ناجح + أدلة كود حتمية",
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
    "review verifier": "للمراجعة عبر أداة التحقق.",
    "partial corroboration": "دعم جزئي مع تعزيز أدلة إضافية.",
    "interaction_detected during gameplay session": "رُصد تفاعل أثناء جلسة التشغيل.",
    "EXE smoke/launch observation مع corroboration إضافية": "تشغيل EXE ناجح مع أدلة تعزيز إضافية.",
    "EXE launch/smoke فقط — gameplay غير مُتحقَّق": "تشغيل EXE ناجح (نافذة مستقرة).",
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


def format_runtime_section(runtime_block: str, *, gate_open: bool = False) -> str:
    if not runtime_block:
        return ""
    level, verdict_key, reasons = _parse_runtime_body(runtime_block)

    # Plain teacher/student language — no internal jargon (sandbox/L4/...).
    lines = ["ماذا حدث عند تشغيل اللعبة آلياً:"]
    verdict_ar = _VERDICT_AR.get(verdict_key, verdict_key or "—")
    if verdict_ar and verdict_ar != "—":
        lines.append(f"• قوة أدلة التشغيل: {verdict_ar}")
    for r in reasons:
        tr = _translate_reason(r)
        if tr:
            lines.append(f"• {tr}")
    if gate_open:
        lines.append(
            "• الخلاصة: اللعبة اشتغلت بنجاح، والميزات المطلوبة موجودة فعلاً في "
            "كود مشروع الطالب (مع تحديد الملف والسطر لكل ميزة)."
        )
    else:
        lines.append(
            "• الخلاصة: هذه ملاحظات آلية أثناء تشغيل اللعبة — القرار النهائي للمعلم."
        )
    return "\n".join(lines)


_BAKED_RUNTIME_HEADERS = (
    "أدلة التشغيل المسجّلة",
    "أدلة تشغيل اللعبة",
    "ماذا حدث عند تشغيل اللعبة",
)


def _strip_baked_runtime_sections(text: str) -> str:
    """
    Remove previously-rendered runtime sections that were saved inside the
    feedback text by an older report generation, so re-rendering never
    duplicates or contradicts the fresh runtime section.
    """
    if not text:
        return ""
    out_lines: List[str] = []
    skipping = False
    for line in text.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(h) for h in _BAKED_RUNTIME_HEADERS):
            skipping = True
            continue
        if skipping:
            if not stripped or stripped.startswith("•"):
                continue
            skipping = False
        if stripped.startswith("• تنويه: L4"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines).strip()


_ENGINE_DISPLAY_NAMES = {
    "godot": "Godot",
    "gamemaker": "GameMaker",
    "unity": "Unity",
    "scratch": "Scratch",
    "unreal": "Unreal",
}


def build_godot_runtime_outcome(
    gv: Optional[Dict[str, Any]] = None,
    gate: Optional[Dict[str, Any]] = None,
    *,
    agent_play_label_ar: Optional[str] = None,
    engine_id: Optional[str] = None,
    criteria_open: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """Structured engine runtime outcome for Word/UI (no raw JSON).

    `criteria_open` (optional) carries the *final* achieved+awardable state
    for C.P5/C.P6 straight from criteria_results — the single source of
    truth. When given, it overrides `gate.criterion_pass` (which only knows
    about automated in-sandbox launch evidence) so the narrative here can
    never contradict the requirement table when a criterion was granted
    through a different accepted path (video, human review, deliverable
    pass with source code).
    """
    gv = gv or {}
    gate = gate or {}
    criteria_open = criteria_open or {}
    engine_name = _ENGINE_DISPLAY_NAMES.get(
        str(engine_id or gv.get("engine_id") or gv.get("engine") or "").lower(), ""
    )
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
    _L4_PLAIN = {
        "L4_full": "التحقق الآلي: كامل (اللعبة اشتغلت والميزات مثبتة)",
        "L4_partial": "التحقق الآلي: جزئي (اللعبة اشتغلت وبعض الميزات مثبتة)",
        "L3": "تم تشغيل ملف اللعبة فقط (بدون إثبات ميزات)",
    }
    if l4_level:
        evidence_lines.append(_L4_PLAIN.get(str(l4_level), str(l4_level)))
    if gameplay_entered is not None:
        evidence_lines.append(
            f"الدخول إلى شاشة اللعب: {'نعم' if gameplay_entered else 'لا'}"
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

    p5_from_l4 = bool(criterion_pass.get("P5"))
    p6_from_l4 = bool(criterion_pass.get("P6"))
    p5_open = bool(criteria_open["P5"]) if "P5" in criteria_open else p5_from_l4
    p6_open = bool(criteria_open["P6"]) if "P6" in criteria_open else p6_from_l4
    impact_lines = [
        (
            "C.P5 (النموذج الأولي للعبة): "
            + (
                "يمكن منحه — اللعبة اشتغلت والأدلة كافية"
                if p5_open
                else "لا يُمنح بعد — نحتاج إثبات تشغيل اللعبة فعلياً (أو فيديو لعب / مراجعة المعلم)"
            )
        ),
        (
            "C.P6 (اختبار اللعبة وتحسينها): "
            + (
                "يمكن منحه — اللعبة اشتغلت ووثائق الاختبار موجودة"
                if p6_open
                else "لا يُمنح بعد — نحتاج إثبات التشغيل مع وثائق اختبار (أو فيديو لعب / مراجعة المعلم)"
            )
        ),
    ]
    # When a criterion was granted through evidence the automated in-app
    # agent can't see (e.g. a submitted gameplay video, since there was no
    # runnable build to launch), say so explicitly — otherwise "الوكيل: لا"
    # next to "C.P5: يمكن منحه" reads as a contradiction.
    if p5_open and not p5_from_l4:
        impact_lines[0] += " — عبر دليل بديل (فيديو لعب موثّق أو مراجعة معلم)، وليس عبر تشغيل تلقائي مباشر"
    if p6_open and not p6_from_l4:
        impact_lines[1] += " — عبر دليل بديل (فيديو لعب موثّق أو مراجعة معلم)، وليس عبر تشغيل تلقائي مباشر"

    return {
        "agent_play_result_ar": agent_result_ar,
        "final_failure_reason_ar": failure_ar or ("—" if not failure_code else failure_code),
        "failure_reason_code": failure_code,
        "evidence_summary_ar": evidence_lines,
        "impact_cp5_cp6_ar": impact_lines,
        "gameplay_entered": gameplay_entered,
        "l4_level": l4_level,
        "criterion_pass_p5": p5_open,
        "criterion_pass_p6": p6_open,
        "engine_display_name": engine_name,
    }


def format_godot_runtime_outcome_ar(outcome: Optional[Dict[str, Any]] = None) -> str:
    """Arabic Word block: agent result, failure, evidence, C.P5/C.P6 impact."""
    if not outcome:
        return ""
    engine_name = str(outcome.get("engine_display_name") or "").strip()
    header = (
        f"نتيجة تشغيل اللعبة ({engine_name}):" if engine_name else "نتيجة تشغيل اللعبة:"
    )
    lines = [
        header,
        f"• {outcome.get('agent_play_result_ar') or '—'}",
    ]
    failure_ar = str(outcome.get("final_failure_reason_ar") or "").strip()
    if failure_ar and failure_ar != "—":
        lines.extend(["", "سبب عدم اكتمال التشغيل:", f"• {failure_ar}"])
    evidence_items = [
        str(item).strip()
        for item in (outcome.get("evidence_summary_ar") or [])
        if str(item).strip() and str(item).strip() != "—"
    ]
    if evidence_items:
        lines.extend(["", "تفاصيل تقنية (للمراجعة):"])
        for item in evidence_items:
            lines.append(f"• {item}")
    lines.extend(["", "أثر التشغيل على معايير اللعبة (C.P5 / C.P6):"])
    for item in outcome.get("impact_cp5_cp6_ar") or []:
        lines.append(f"• {item}")
    lines.append(
        "• ملاحظة: تقييم التقرير المكتوب (B.P3/B.P4) مستقل عن تقييم تشغيل اللعبة (C.P5/C.P6)."
    )
    return clean_report_text("\n".join(lines))


def format_criterion_feedback_for_report(
    feedback: str,
    *,
    runtime_note_ar: Optional[str] = None,
    achieved: Optional[bool] = None,
    awardable: Optional[bool] = None,
    godot_runtime_outcome: Optional[Dict[str, Any]] = None,
    gate_open: bool = False,
) -> str:
    """
    Build teacher-readable Arabic sections. When governance blocked achievement,
    only the institutional voice is shown (no AI assessor praise).
    """
    from app.btec_criteria_governance import strip_btec_governance_feedback

    feedback = strip_btec_governance_feedback(feedback or "")
    feedback = _strip_baked_runtime_sections(feedback)
    runtime_block, assessor = split_runtime_feedback(feedback)
    if runtime_note_ar and not runtime_block:
        note = str(runtime_note_ar)
        # A previously-rendered (baked) section cannot be re-parsed reliably —
        # drop it; a fresh plain-language section is rendered below instead.
        if "•" in note or any(h in note for h in _BAKED_RUNTIME_HEADERS):
            note = ""
        runtime_block = note

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

    runtime_fmt = (
        format_runtime_section(runtime_block, gate_open=gate_open) if runtime_block else ""
    )
    if not runtime_fmt and gate_open and not institutional_only:
        runtime_fmt = (
            "ماذا حدث عند تشغيل اللعبة آلياً:\n"
            "• الخلاصة: اللعبة اشتغلت بنجاح، والميزات المطلوبة موجودة فعلاً في "
            "كود مشروع الطالب (مع تحديد الملف والسطر لكل ميزة)."
        )
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
        return "⏸", "مراجعة بشرية مطلوبة (Human Review Required)", "FEF3C7", "F59E0B"
    if achieved and awardable:
        return "✅", "تحقق المعيار (Achieved)", "D1FAE5", "10B981"
    if achieved and not awardable:
        # Lead with "محجوب" so teachers/students do not misread Merit as granted.
        return "⏸", "محجوب — تحقق أكاديمياً ومعايير سابقة ناقصة", "FEF3C7", "F59E0B"
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
    # Remove isolate marks from older renders — they show as boxes in Word.
    t = t.replace("⁦", "").replace("⁧", "").replace("⁨", "").replace("⁩", "")
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
    t = _plain_language(t)
    t = _isolate_latin_phrases(t)
    return strip_embedded_json_blocks(t.strip())


# Teacher/student-friendly wording — technical jargon → plain Arabic.
_PLAIN_REPLACEMENTS: Tuple[Tuple[str, str], ...] = (
    ("(`.exe`)", "(ملف تشغيل اللعبة)"),
    ("`.exe`", "ملف تشغيل اللعبة"),
    ("ملف .exe", "ملف تشغيل اللعبة"),
    ("وكود GML المرفق", "وكود اللعبة المرفق"),
    ("كود GML", "كود اللعبة"),
    ("أكواد برمجية (GML)", "أكواد اللعبة البرمجية"),
    ("ملفات GML", "ملفات كود اللعبة"),
    ("Static-Corroborated Runtime", "تشغيل ناجح مع ميزات مثبتة من الكود"),
    ("sandbox", "بيئة التشغيل الآلي"),
    ("gameplay loop", "حلقة اللعب"),
    ("(gameplay)", "(اللعب الفعلي)"),
    ("functional_smoke_and_test_doc", "تشغيل ناجح + وثائق اختبار"),
)


def _plain_language(text: str) -> str:
    if not text:
        return text
    if not any("؀" <= c <= "ۿ" for c in text):
        return text
    for old, new in _PLAIN_REPLACEMENTS:
        if old in text:
            text = text.replace(old, new)
    return text


# Latin phrase (possibly multi-word, incl. dots/slashes like C.P5/C.P6) inside
# RTL Arabic text. Wrapped in LRE…PDF (U+202A…U+202C) so Word keeps the
# internal left-to-right order. NOTE: the newer isolate marks (U+2066/U+2069)
# render as visible boxes in older Word builds — never use them here.
_LATIN_PHRASE_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9_.\-/:+%]*(?:\([A-Za-z0-9_.\-/:+% ]*\))?"
    r"(?: [A-Za-z][A-Za-z0-9_.\-/:+%]*(?:\([A-Za-z0-9_.\-/:+% ]*\))?)*"
)
_LRI = "‪"  # LEFT-TO-RIGHT EMBEDDING (widely supported)
_PDI = "‬"  # POP DIRECTIONAL FORMATTING


def _isolate_latin_phrases(text: str) -> str:
    """Wrap Latin phrases with directional isolates for correct RTL display."""
    if not text or _LRI in text:
        return text
    if not any("؀" <= c <= "ۿ" for c in text):
        return text  # pure Latin/other — no mixing to fix

    def _wrap(m: re.Match[str]) -> str:
        seg = m.group(0)
        if len(seg) <= 1:
            return seg
        return f"{_LRI}{seg}{_PDI}"

    return _LATIN_PHRASE_RE.sub(_wrap, text)
