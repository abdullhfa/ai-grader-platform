"""
Textbook analysis and reference solution generation
"""
import asyncio
import os
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import pdfplumber  # type: ignore
from dotenv import load_dotenv  # type: ignore
from .ai_provider import get_global_provider, get_ai_provider, _looks_like_google_api_error_json

load_dotenv()

# Sections removed from teacher guide (دليل المهمة) — never generate or persist.
_EXCLUDED_GUIDE_SECTION_KEYS = (
    "section_4_theoretical",
    "section_4_practical",
    "section_5_evidence",
    "section_5_practical",
    "section_6_evidence",
    "section_6_grade_levels",
    "section_6_expected_deliverables",
    "section_7_grade_levels",
    "section_7_model_answer_framework",
    "section_7_evidence_authenticity",
    "section_8_common_errors",
    "section_9_marking_checklist",
    "section_9_common_errors",
    "section_10_student_model_answer",
    "section_1_criteria_extraction",
    "section_2_mission_interpretation",
    "section_2_teacher_reference",
    "section_3_criteria_guide",
    "section_3_theoretical",
    "section_2_theoretical",
    "section_3_practical",
    "section_4_theoretical",
    "section_4_practical",
    "section_5_practical",
)

_CRITERIA_ITEM_ALLOWED = frozenset({
    "code",
    "command_verb",
    "what_student_must_do",
    "required_evidence",
    "assessor_look_for",
    "common_errors",
})

_LEGACY_SECTION_HEADING_RE = re.compile(
    r"القسم\s+(الثاني|الثالث|الرابع|الخامس|السادس|السابع|الثامن|التاسع|العاشر|٢|٣|٤|٥|٦|٧|٨|٩|١٠)\b"
)

# Canonical Arabic title — دليل المعلم: القسم الأول فقط.
SLIM_V3_SECTION_TITLES = (
    "القسم الأول: تفسير كل معيار",
)

_SLIM_V3_TITLE_KEYS = (
    (
        "section_1_criteria_guide",
        "section_3_criteria_guide",
        "section_2_teacher_reference",
    ),
)


def apply_slim_v3_section_titles(data: Dict) -> Dict:
    """Force القسم الأول title (AI sometimes returns old numbering)."""
    if not isinstance(data, dict):
        return data
    title = SLIM_V3_SECTION_TITLES[0]
    for key in _SLIM_V3_TITLE_KEYS[0]:
        block = data.get(key)
        if isinstance(block, dict):
            block["title"] = title
    return data


def _sanitize_criteria_item(item: object) -> Dict:
    """Keep only slim_v3 per-criterion fields (no checklists / grade tables)."""
    if not isinstance(item, dict):
        return {}
    clean: Dict = {}
    for key in _CRITERIA_ITEM_ALLOWED:
        if key not in item:
            continue
        val = item[key]
        if key == "common_errors" and isinstance(val, list):
            clean[key] = [
                e for e in val
                if isinstance(e, dict) and (e.get("error") or e.get("how_to_avoid"))
            ][:2]
        elif isinstance(val, list):
            clean[key] = [str(x) for x in val if x][:3 if key == "required_evidence" else 99]
        elif val:
            clean[key] = val
    return clean


def _strip_markdown_legacy_sections(text: str) -> str:
    """Remove markdown blocks for sections 2–10 (keep section 1 only)."""
    if not text:
        return text
    lines: List[str] = []
    skip_block = False
    for line in text.splitlines():
        if _LEGACY_SECTION_HEADING_RE.search(line):
            skip_block = True
            continue
        if skip_block and re.search(r"القسم\s+الأول\b", line):
            skip_block = False
        if not skip_block:
            lines.append(line)
    return "\n".join(lines).strip()


def _filter_practical_steps(steps: object) -> List[str]:
    """Keep only plain step lines; drop embedded legacy section headings."""
    out: List[str] = []
    if not isinstance(steps, list):
        return out
    for item in steps:
        text = str(item).strip() if item is not None else ""
        if not text or _LEGACY_SECTION_HEADING_RE.search(text):
            continue
        out.append(text)
    return out[:6]


def enforce_slim_v3_guide_shape(data: Dict) -> Dict:
    """
    Collapse any guide JSON to slim_v3 — section 1 only (تفسير كل معيار).
    Strips sections 2–10 including theoretical/practical requirements.
    """
    if not isinstance(data, dict):
        return data

    sec1 = (
        data.get("section_1_criteria_guide")
        or data.get("section_3_criteria_guide")
        or data.get("section_2_teacher_reference")
        or {}
    )
    if not isinstance(sec1, dict):
        sec1 = {}
    raw_guides = sec1.get("criteria_guide") or []
    sec1_out: Dict = {
        "title": SLIM_V3_SECTION_TITLES[0],
        "criteria_guide": [
            _sanitize_criteria_item(g) for g in raw_guides if _sanitize_criteria_item(g)
        ],
    }
    intro = (sec1.get("mission_intro") or "").strip()
    if intro:
        sec1_out["mission_intro"] = intro
    note = (sec1.get("_degraded_note") or "").strip()
    if note:
        sec1_out["_degraded_note"] = note
    sec1 = sec1_out

    shaped: Dict = {
        "guide_version": "slim_v3",
        "section_1_criteria_guide": sec1,
    }

    has_body = bool(sec1.get("criteria_guide") or sec1.get("mission_intro"))
    md = data.get("markdown_guide") or data.get("teacher_guide")
    if md and not has_body:
        shaped["markdown_guide"] = _strip_markdown_legacy_sections(str(md))

    return apply_slim_v3_section_titles(shaped)


def strip_excluded_guide_sections(data: Dict) -> Dict:
    """Remove sections 2–10 and legacy blocks; keep only slim_v3 section 1."""
    return enforce_slim_v3_guide_shape(data)


def _reject_if_google_api_error_dict(obj: object) -> None:
    """Raise if AI returned a Google API error JSON instead of teacher-guide JSON."""
    if _looks_like_google_api_error_json(obj):
        raise ValueError(
            "واجهة Google رفضت الطلب (حصّة منتهية أو النموذج غير متاح لخطتك)."
            " جرّب تفعيل الفوترة، أو غيّر GEMINI_MODEL، أو شغّل Ollama كنسخة احتياطية."
        )


def _extract_images_and_analyze_sync(assignment_file_path: Optional[str]) -> str:
    """Run in a worker thread: extract images from assignment file and vision-analyze them."""
    if not assignment_file_path:
        return ""
    try:
        from app.document_processor import DocumentProcessor
        from app.ai_provider import get_vision_provider

        print(f"🖼️ [GUIDE] Extracting images from assignment file: {assignment_file_path}")
        extracted_images = DocumentProcessor.extract_images(assignment_file_path, 20)
        if not extracted_images:
            print("ℹ️ [GUIDE] No significant images found in assignment file")
            return ""
        print(f"🖼️ [GUIDE] Found {len(extracted_images)} images. Analyzing with Vision AI...")
        vision_provider = get_vision_provider()
        out = vision_provider.analyze_images(
            extracted_images,
            context="ملف تعيين BTEC (Assignment Brief) — صِف المخططات والجداول والمتطلبات المرئية",
            temperature=0.0,
        )
        if out:
            print(f"✅ [GUIDE] Assignment image analysis complete: {len(out)} chars")
        else:
            print("⚠️ [GUIDE] No image analysis returned")
        return out or ""
    except Exception as e:
        print(f"⚠️ [GUIDE] Image analysis failed (non-fatal): {e}")
        return ""


def extract_text_from_pdf(pdf_path: str, page_from: int, page_to: int) -> str:
    """
    Extract text from specific pages of a PDF
    """
    from pathlib import Path as _Path

    try:
        path = _Path(pdf_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"ملف PDF غير موجود: {path}")

        page_from = max(1, page_from)
        page_to = max(page_from, page_to)

        extracted_text = []
        with pdfplumber.open(str(path)) as pdf:
            total_pages = len(pdf.pages)
            if total_pages < 1:
                raise ValueError("ملف PDF لا يحتوي على صفحات")
            page_from = min(page_from, total_pages)
            page_to = min(max(page_from, page_to), total_pages)
            for page_num in range(page_from - 1, page_to):
                page = pdf.pages[page_num]
                text = page.extract_text() or ""
                if text.strip():
                    extracted_text.append(f"--- صفحة {page_num + 1} ---\n{text}\n")
        result = "\n".join(extracted_text)
        if not result.strip():
            raise ValueError(
                f"لم يُستخرج نص من الصفحات {page_from}–{page_to} "
                f"(قد تكون صفحات مسح ضوئي بدون OCR)"
            )
        return result
    except OSError as e:
        print(f"Error extracting text from PDF (OS): {e}")
        raise OSError(f"فشل فتح PDF — تحقق من المسار والصفحات: {e}") from e
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        raise Exception(f"فشل في استخراج النص من الكتاب: {str(e)}") from e


def _friendly_ai_error(exc: Exception) -> str:
    """Short Arabic hint for common provider misconfiguration."""
    msg = str(exc)
    if "deepseek-v3:671b" in msg or "model" in msg.lower() and "not found" in msg.lower():
        return (
            "اسم النموذج غير صحيح. في ملف .env استخدم "
            "OPENROUTER_MODEL=google/gemini-2.5-flash و OLLAMA_MODEL=deepseek-coder "
            "أو عطّل Ollama: DISABLE_OLLAMA_FALLBACK=true"
        )
    if "API key not valid" in msg or "INVALID_ARGUMENT" in msg:
        return (
            "مفتاح Gemini غير صالح. ضع مفتاح Google (يبدأ بـ AIza) في GEMINI_API_KEY "
            "أو استخدم AI_PROVIDER=openrouter مع OPENROUTER_API_KEY."
        )
    if "Empty response" in msg or "reasoning only" in msg:
        return (
            "النموذج لم يُرجع نصاً. جرّب OPENROUTER_MODEL=google/gemini-2.5-flash "
            "أو زِد GUIDE_MAX_TOKENS في .env."
        )
    return msg[:400]


def _call_ai_json(system_prompt: str, user_prompt: str, step_name: str) -> Dict:
    """
    Shared helper: call AI with retry/fallback logic and parse JSON response.
    Used by the 3-prompt pipeline in generate_reference_solution().
    """
    import time
    import random
    import re
    import traceback

    provider = get_global_provider()
    pname = provider.provider
    print(f"🔄 [{step_name}] Using {pname} (with provider fallback when needed)…")
    key_ok = bool(os.getenv("GEMINI_API_KEY")) if pname == "gemini" else True
    print(f"🧵 [{step_name}] Provider={pname}, Gemini key={'Yes' if key_ok else 'No'}")

    last_error = None
    max_retries = 5
    base_delay = 5
    response_text = ""
    guide_max_tokens = int(os.getenv("GUIDE_MAX_TOKENS", "16384") or "16384")
    # seed breaks some OpenRouter/Gemini reasoning models (empty content); use only for ollama.
    use_seed = 42 if pname == "ollama" else None

    # Try the current provider; if EVERY retry fails, escalate to the next provider once.
    tried_fallback = False
    for attempt in range(max_retries):
        try:
            response_text = provider.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=guide_max_tokens,
                seed=use_seed,
            )
            print(
                f"🔹 [{step_name}] Response ({len(response_text)} chars): {response_text[:150]}..."
            )
            break
        except Exception as e:
            error_str = str(e).lower()
            print(f" [{step_name}] Error ({pname}, attempt {attempt}): {str(e)}")
            last_error = e
            quota_hit = any(
                x in error_str
                for x in (
                    "429",
                    "rate limit",
                    "rate_limit",
                    "resource_exhausted",
                    "resource exhausted",
                    "quota",
                    "too many requests",
                    "503",
                    "overloaded",
                    "free_tier",
                )
            )
            # Treat transient network problems the same way as quota — they deserve a retry.
            network_hit = any(
                x in error_str
                for x in (
                    "connection",
                    "timeout",
                    "timed out",
                    "temporarily unavailable",
                    "502",
                    "504",
                    "reset by peer",
                    "incomplete chunked read",
                )
            )
            if quota_hit or network_hit:
                wait_match = re.search(r"try again in (\d+)m", error_str)
                if wait_match and int(wait_match.group(1)) > 1 and quota_hit:
                    # Multi-minute quota lockout — escalate to fallback provider
                    print(f" [{step_name}] Long quota lockout, attempting fallback provider.")
                    break
                sec_match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_str)
                if sec_match:
                    delay = min(float(sec_match.group(1)) + random.uniform(0, 1), 120.0)
                else:
                    delay = base_delay * (2**attempt) + random.uniform(0, 2)
                kind = "quota" if quota_hit else "network"
                print(
                    f" [{step_name}] {kind} issue. Retrying in {delay:.1f}s... ({attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
            elif not tried_fallback:
                # Unknown error on this provider — try the next provider in the chain ONCE
                from .ai_provider import get_fallback_provider
                tried_fallback = True
                fb = get_fallback_provider()
                if fb:
                    provider = fb
                    pname = provider.provider
                    print(f"🔄 [{step_name}] Switched to fallback provider: {pname}")
                    continue
                # No fallback available — surface the error
                traceback.print_exc()
                raise e
            else:
                traceback.print_exc()
                raise e

    # If the loop ended without success but we have a fallback chance, try once more
    if not response_text and not tried_fallback:
        from .ai_provider import get_fallback_provider
        fb = get_fallback_provider()
        if fb:
            print(f"🔄 [{step_name}] All retries on {pname} exhausted, trying fallback {fb.provider}")
            try:
                fb_name = fb.provider
                response_text = fb.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    max_tokens=guide_max_tokens,
                    seed=42 if fb_name == "ollama" else None,
                )
            except Exception as e:
                last_error = e

    if not response_text:
        raise Exception(f"فشل في {step_name}. آخر خطأ: {last_error}")

    response_text = re.sub(
        r"<think>.*?</think>",
        "",
        response_text,
        flags=re.DOTALL,
    ).strip()

    cjk_pattern = r"[\u4e00-\u9fff\uac00-\ud7af]"
    if re.search(cjk_pattern, response_text):
        print(f" [{step_name}] CJK hallucination detected, scrubbing...")
        response_text = response_text.replace("ي提供", "يقدم").replace("ي 제공", "يقدم")
        response_text = re.sub(cjk_pattern, "", response_text)

    try:
        with open(f"debug_ai_{step_name}.txt", "w", encoding="utf-8") as f:
            f.write(f"Provider: {pname}\n\n{response_text}")
    except Exception:
        pass

    json_match = re.search(r"(\{[\s\S]*\})", response_text)
    possible_json = json_match.group(1) if json_match else response_text
    try:
        parsed = json.loads(possible_json)
    except json.JSONDecodeError:
        try:
            parsed = json.loads(possible_json, strict=False)
        except json.JSONDecodeError:
            cleaned = re.sub(r"[\x00-\x1f\x7f](?![\n\r])", "", possible_json)
            cleaned = cleaned.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
            parsed = json.loads(cleaned)
    _reject_if_google_api_error_dict(parsed)
    return parsed


def generate_reference_solution(textbook_content: str, assignment_analysis: Dict, assignment_text: str = "", assignment_images_analysis: str = "") -> Dict:
    """
    Generate the BTEC Teacher Implementation Guide (slim_v3) — 1 AI call, section 1 only.
    """
    print("═══════════════════════════════════════")
    print("📋 جاري بناء دليل المعلم (slim_v3 — القسم الأول فقط)...")
    print("  → استدعاء JSON واحد")
    print("═══════════════════════════════════════")
    _t0 = time.perf_counter()

    # ── Prepare context blocks (full assignment + textbook text sent to the model) ──
    images_block = ""
    if assignment_images_analysis:
        images_block = f"\n IMAGES/DIAGRAMS IN THE ASSIGNMENT BRIEF:\n{assignment_images_analysis}\n"

    textbook_block = ""
    if textbook_content and textbook_content.strip():
        textbook_block = f"\n═══ TEXTBOOK REFERENCE CONTENT ═══\n{textbook_content.strip()}\n═══════════════════════════════════"

    base_rules = """CRITICAL RULES (apply to ALL outputs):
1. Language: ALL text values MUST be in professional Arabic.
2. BTEC Pearson Jordan standards — criterion-referenced (Achieved / Not Achieved). NO percentages.
3. Use the EXACT P/M/D criteria text from the brief. Do NOT invent criteria.
4. Be SPECIFIC and TECHNICAL: name exact tools, commands, file types.
5. P-level = basic tasks only. M-level = testing/optimization ONLY. D-level = critical evaluation ONLY.
6. BREVITY: keep every string concise. No long essays. Respect MAX limits in the schema.
7. Output ONLY valid JSON. No markdown, no commentary. Start with { and end with }."""

    call_system = f"""You are a Senior Pearson BTEC Internal Verifier (IV) in Jordan.
Produce the slim Teacher Guide (SECTION 1 ONLY) as one JSON object.
Do NOT include section 2 (المتطلبات النظرية), section 3 (المتطلبات العملية), or sections 6–10.
No evidence tables, grade-level blocks, marking checklists, theoretical concepts blocks, or practical steps lists.

{base_rules}

Return EXACTLY this JSON structure (no extra top-level keys):
{{
  "guide_version": "slim_v3",
  "section_1_criteria_guide": {{
    "title": "القسم الأول: تفسير كل معيار",
    "mission_intro": "MAX 3 sentences: scenario, tools, teacher expectations",
    "criteria_guide": [
      {{
        "code": "B.P3",
        "command_verb": "develop",
        "what_student_must_do": "MAX 4 sentences, technical",
        "required_evidence": ["evidence 1", "evidence 2"],
        "assessor_look_for": ["check 1", "check 2"],
        "common_errors": [
          {{"error": "specific technical mistake", "how_to_avoid": "specific fix"}}
        ]
      }}
    ]
  }}
}}

SECTION TITLE (use EXACTLY):
- section_1_criteria_guide.title = "القسم الأول: تفسير كل معيار"

LIMITS:
- criteria_guide: ONE entry per P/M/D criterion in the brief.
- required_evidence: MAX 3 items per criterion.
- common_errors: MAX 2 per criterion, technical only.
- NEVER add section_2_theoretical, section_3_practical, pass_threshold, merit_threshold, distinction_threshold, check_items, checklist_items, or grade-level blocks."""

    call_user = f"ASSIGNMENT BRIEF:\n{assignment_text}\n{textbook_block}\n{images_block}"

    merged: Dict = {}
    calls = [
        (call_system, call_user, "guide_sec1_3"),
    ]
    max_workers = int(os.getenv("GUIDE_MAX_WORKERS", "3") or "3")
    max_workers = max(1, min(max_workers, len(calls)))

    if max_workers == 1:
        for sys_prompt, usr_prompt, step_name in calls:
            try:
                result = _call_ai_json(sys_prompt, usr_prompt, step_name)
                merged.update(result)
                print(f"✅ [{step_name}] Done — keys: {list(result.keys())}")
            except Exception as e:
                print(f"❌ [{step_name}] Failed: {e}")
                import traceback
                traceback.print_exc()
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_step = {
                executor.submit(_call_ai_json, s, u, n): n
                for s, u, n in calls
            }
            for fut in as_completed(future_to_step):
                step_name = future_to_step[fut]
                try:
                    result = fut.result()
                    merged.update(result)
                    print(f"✅ [{step_name}] Done — keys: {list(result.keys())}")
                except Exception as e:
                    print(f"❌ [{step_name}] Failed: {e}")
                    import traceback
                    traceback.print_exc()

    print(f"⏱️ دليل المعلم (توليد JSON): {time.perf_counter() - _t0:.1f}s")

    if not merged:
        # Ultimate fallback — markdown + slim_v1 stub sections for Word export.
        print(" All structured calls failed. Falling back to markdown-only guide...")
        last_ai_error = ""
        markdown_text = ""
        try:
            from .ai_provider import reset_global_provider, get_ai_provider
            reset_global_provider()
            provider = get_ai_provider(os.getenv("AI_PROVIDER", "openrouter"))
            markdown_text = provider.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a BTEC assessor. Generate a teacher guide in Arabic."},
                    {"role": "user", "content": f"Generate a BTEC teacher guide for:\n{assignment_text}"}
                ],
                temperature=0.0,
                max_tokens=int(os.getenv("GUIDE_MAX_TOKENS", "8192") or "8192"),
            )
        except Exception as e2:
            last_ai_error = _friendly_ai_error(e2)

        degraded_note = (
            "⚠️ تعذّر توليد دليل المعلم تلقائياً. "
            "تحقق من إعدادات الذكاء الاصطناعي في ملف .env ثم أنشئ المهمة من جديد."
        )
        if last_ai_error:
            degraded_note += f" ({last_ai_error})"

        return strip_excluded_guide_sections({
            "guide_version": "slim_v3_degraded",
            "section_1_criteria_guide": {
                "title": "القسم الأول: تفسير كل معيار",
                "mission_intro": (
                    "لم يُولَّد دليل المعلم بعد بسبب خطأ في الاتصال بنموذج الذكاء الاصطناعي. "
                    "راجع إعدادات OPENROUTER_MODEL و OPENROUTER_API_KEY في ملف .env."
                ),
                "criteria_guide": [],
                "_degraded_note": degraded_note,
            },
        })

    merged = enforce_slim_v3_guide_shape(merged)
    print(f"✅ تم بناء دليل المعلم (slim_v3) — {len(merged)} مفاتيح")
    return merged


def analyze_assignment_requirements(assignment_text: str, known_criteria_list: Optional[List[Dict]] = None) -> Dict:
    """
    Analyze assignment requirements using AI to extract TASK-SPECIFIC requirements.
    Falls back to regex if AI fails.
    """
    print(" 🔍 Analyzing assignment requirements with AI...")

    # 1. Regex check for codes first (to help the AI)
    from .criteria_extractor import extract_required_criteria_from_text
    regex_codes = extract_required_criteria_from_text(assignment_text)
    codes_hint = f"Potential criteria codes found: {', '.join(regex_codes)}" if regex_codes else "No criteria codes found by regex."

    # 2. Use AI to extract the details from the assignment brief
    system_prompt = f"""You are a Senior BTEC Pearson Jordan Assessor. 
Your goal is to analyze the provided Assignment Brief and extract the EXACT grading criteria and their specific requirements as defined IN THIS TASK.

IMPORTANT: 
- Do NOT use generic BTEC descriptions. Use the SPECIFIC tasks described in the assignment.
- If the assignment text says "To achieve P1, you must create a login page", then the requirement is "Create a login page".
- Identify the Learning Aim for each criterion if possible.

{codes_hint}

Return a JSON object in this EXACT structure:
{{
  "topic": "The assignment title or main theme in Arabic",
  "required_criteria": ["A.P1", "B.M2", ...],
  "criteria_details": {{
    "A.P1": {{
      "name": "Criterion Name in Arabic",
      "description": "Specific task description for this criterion from the brief in Arabic",
      "key_requirements": ["Specific point 1", "Specific point 2"],
      "level": "P"
    }}
  }},
  "special_instructions": ["Any special constraints or tools mentioned in the task"]
}}

Language: All text values MUST be in professional Arabic.
"""
    user_prompt = f"ASSIGNMENT BRIEF TEXT:\n{assignment_text}"

    try:
        ai_result = _call_ai_json(system_prompt, user_prompt, "Assignment Requirement Analysis")
        
        # Post-process: Ensure all codes are in required_criteria
        if "criteria_details" in ai_result:
            ai_result["required_criteria"] = list(ai_result["criteria_details"].keys())
            
            # Map levels correctly
            for code, detail in ai_result["criteria_details"].items():
                if "level" not in detail:
                    upper_code = code.upper()
                    if 'P' in upper_code:
                        detail["level"] = "P"
                    elif 'M' in upper_code:
                        detail["level"] = "M"
                    elif 'D' in upper_code:
                        detail["level"] = "D"
                    else:
                        detail["level"] = "P"

        print(f" ✅ AI found {len(ai_result.get('required_criteria', []))} task-specific criteria.")
        return ai_result

    except Exception as e:
        print(f" ⚠️ AI analysis failed: {e}. Falling back to regex.")
        return analyze_assignment_requirements_regex(assignment_text, known_criteria_list)


def analyze_assignment_requirements_regex(assignment_text: str, known_criteria_list: Optional[List[Dict]] = None) -> Dict:
    """
    Regex-based fallback for assignment requirement analysis.
    """
    import re
    from .criteria_extractor import extract_required_criteria_from_text

    required_criteria = extract_required_criteria_from_text(assignment_text)

    topic_match = re.search(r'(?:الوحدة|Unit|UNIT)\s*(\d+)[:\s-]+([^\n]+)', assignment_text)
    topic = topic_match.group(2).strip() if topic_match else "General Topic"

    from typing import Any
    result: Dict[str, Any] = {
        "topic": topic,
        "required_criteria": required_criteria,
        "criteria_details": {},
        "special_instructions": []
    }

    official_specs = {c["code"]: c for c in known_criteria_list if "code" in c} if known_criteria_list else {}

    for criterion_code in required_criteria:
        if criterion_code in official_specs:
            spec = official_specs[criterion_code]
            result["criteria_details"][criterion_code] = {
                "name": f"المعيار {criterion_code}",
                "description": spec.get("description", ""),
                "key_requirements": spec.get("requirements", []),
                "level": spec.get("level", "P")
            }
        else:
            result["criteria_details"][criterion_code] = {
                "name": f"المعيار {criterion_code}",
                "description": f"متطلبات المعيار {criterion_code}",
                "key_requirements": [],
                "level": "P"
            }

    return result


def create_grading_criteria_from_solution(reference_solution: Dict, assignment_analysis: Dict) -> List[Dict]:
    """
    Create grading criteria based on the assignment_analysis
    """
    criteria_list = []

    if not assignment_analysis:
        print("⚠️ Warning: assignment_analysis is empty or None in create_grading_criteria")
        return []

    criteria_details = assignment_analysis.get("criteria_details", {})
    if not criteria_details:
        print("⚠️ Warning: criteria_details is empty")
        return []

    for criterion_code, criteria_data in criteria_details.items():
        criteria_list.append({
            "criteria_level": criterion_code,
            "criteria_name": criteria_data.get("name", f"المعيار {criterion_code}"),
            "criteria_description": criteria_data.get("description", ""),
            "key_points": criteria_data.get("key_requirements", []),
            "weight": 25  # Equal weight for all criteria
        })

    return criteria_list


async def process_textbook_and_assignment(
    textbook_path: str,
    page_from: int,
    page_to: int,
    assignment_text: str,
    known_criteria_list: Optional[List[Dict]] = None,  # NEW argument
    assignment_file_path: Optional[str] = None,  # NEW - path to assignment file for image extraction
) -> Tuple[Dict, Dict, List[Dict]]:
    """
    Complete workflow: extract textbook content, analyze assignment, generate reference solution
    Returns:
        - assignment_analysis: Analysis of assignment requirements
        - reference_solution: Generated reference solution
        - grading_criteria: List of grading criteria
    """
    _wall = time.perf_counter()
    _tb_path = str(Path(textbook_path).resolve())
    _asg_path = (
        str(Path(assignment_file_path).resolve())
        if assignment_file_path
        else None
    )

    # Parallel stage: PDF extract + assignment AI analysis + optional vision (independent work)
    print(f"📖 استخراج الكتاب (صفحات {page_from}–{page_to}) + تحليل الواجب + صور الملف — بالتوازي")
    textbook_content, assignment_analysis, assignment_images_analysis = await asyncio.gather(
        asyncio.to_thread(extract_text_from_pdf, _tb_path, page_from, page_to),
        asyncio.to_thread(
            analyze_assignment_requirements,
            assignment_text,
            known_criteria_list,
        ),
        asyncio.to_thread(_extract_images_and_analyze_sync, _asg_path),
    )

    if not textbook_content or len(textbook_content) < 100:
        raise Exception("لم يتم استخراج محتوى كافٍ من الكتاب")

    print(f"⏱️ انتهى التحضير المتوازي: {time.perf_counter() - _wall:.1f}s")

    # Generate reference solution (slim_v3: 1 AI call, section 1 only)
    print("✍️ إنشاء دليل المهمة...")
    reference_solution = await asyncio.to_thread(
        generate_reference_solution,
        textbook_content,
        assignment_analysis,
        assignment_text,
        assignment_images_analysis,
    )

    # Step 4: Create grading criteria
    print("📋 إنشاء معايير التقييم...")
    grading_criteria = create_grading_criteria_from_solution(reference_solution, assignment_analysis)

    print(f"✅ تم إنشاء دليل المهمة بنجاح! (إجمالي تقريبي: {time.perf_counter() - _wall:.1f}s)")

    return assignment_analysis, reference_solution, grading_criteria
