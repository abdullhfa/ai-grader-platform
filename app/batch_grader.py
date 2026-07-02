"""
Batch grading system with parallel processing
"""
import json
import asyncio
import math
import threading
from typing import List, Dict, Optional, Callable, Any
from dotenv import load_dotenv  # type: ignore
from pathlib import Path
from .ai_provider import get_global_provider, get_grading_provider, get_vision_provider  # type: ignore
from .document_processor import DocumentProcessor  # type: ignore
import hashlib
import os
from app.models import PlagiarismCheck, Submission, GradingSummary  # type: ignore
from app.graders.game_analyzer import (  # type: ignore
    build_dual_version_grading_addon,
    build_plagiarism_corpus,
)
from app.artifact_inventory import (  # type: ignore
    EXECUTABLE_ARTIFACT_EXTENSIONS,
    build_artifact_inventory,
    build_evidence_coverage_matrix,
    format_artifact_context_for_grading,
    persist_artifact_inventory_json,
)
from app.evidence_authority_mapping import (  # type: ignore
    check_claim_authority,
    format_authority_mapping_for_grading,
    sanitize_claim_text,
)
from app.archive_extraction_utils import hash_submission_file  # type: ignore
from app.cross_artifact_consistency import format_consistency_report_for_grading  # type: ignore
from app.plagiarism_boilerplate import strip_plagiarism_boilerplate  # type: ignore
import difflib
import re

load_dotenv(override=True)


def extract_text_from_file(file_path: str) -> str:
    """
    Extract text using DocumentProcessor
    """
    return DocumentProcessor.extract_text(file_path)


def generate_content_fingerprint(text: str) -> Dict:
    """
    Generate a descriptive content fingerprint per Section 2.1 of btec_grading_prompt.
    Includes: word count, page count, sections, images/tables, first/last 50 words, references.
    """
    import re as _re
    clean_text = text.strip()
    words = _re.findall(r'\b\w+\b', clean_text)
    word_count = len(words)

    # Estimate page count (~300 words per page)
    page_count = max(1, word_count // 300)

    # Count sections/headings
    heading_patterns = [
        r'^#+\s',           # Markdown headings
        r'^[A-Z][^.!?]*:$',  # Title-like lines ending with colon
        r'^\d+[\.\)]\s+\S',  # Numbered sections
        r'^(أولاً|ثانياً|ثالثاً|رابعاً|خامساً)',  # Arabic ordinals
    ]
    section_count = sum(
        len(_re.findall(p, clean_text, _re.MULTILINE)) for p in heading_patterns
    )

    # Count images/tables references
    image_refs = len(_re.findall(r'(صورة|شكل|figure|image|screenshot|لقطة)\s*\d*', clean_text, _re.IGNORECASE))
    table_refs = len(_re.findall(r'(جدول|table)\s*\d*', clean_text, _re.IGNORECASE))

    # First and last 50 words
    first_50 = ' '.join(words[:50]) if word_count >= 50 else ' '.join(words)
    last_50 = ' '.join(words[-50:]) if word_count >= 50 else ' '.join(words)

    # References detection
    ref_patterns = [
        r'(المراجع|References|Bibliography|مصادر)',
        r'(https?://\S+)',
        r'\(\d{4}\)',  # Year citations like (2023)
    ]
    references_found = []
    for p in ref_patterns:
        matches = _re.findall(p, clean_text, _re.IGNORECASE)
        references_found.extend(matches[:5])

    # SHA256 hash for deduplication
    content_hash = hashlib.sha256(clean_text.encode('utf-8')).hexdigest()

    return {
        "content_hash": content_hash,
        "word_count": word_count,
        "page_count": page_count,
        "section_count": section_count,
        "image_count": image_refs,
        "table_count": table_refs,
        "first_50_words": first_50,
        "last_50_words": last_50,
        "references": references_found[:10],
        "fingerprint_id": content_hash[:16],
    }


def classify_ai_risk(score: float) -> Dict:
    """
    Classify AI risk per Section 3.3 of btec_grading_prompt (5-tier system).
    0-20%: ✅ Human content (high probability)
    21-40%: 🟡 Human with minor assistance
    41-60%: 🟠 Suspected content - needs review
    61-80%: 🔴 AI content (high probability)
    81-100%: ⛔ AI content (near certain)
    """
    if score <= 20:
        return {
            "level": "HUMAN",
            "icon": "✅",
            "label_ar": "محتوى بشري (احتمال عالٍ)",
            "label_en": "Human content (high probability)",
            "color": "green",
        }
    elif score <= 40:
        return {
            "level": "HUMAN_ASSISTED",
            "icon": "🟡",
            "label_ar": "محتوى بشري مع مساعدة بسيطة",
            "label_en": "Human content with minor AI assistance",
            "color": "yellow",
        }
    elif score <= 60:
        return {
            "level": "SUSPECTED",
            "icon": "🟠",
            "label_ar": "محتوى مشتبه به - يحتاج مراجعة",
            "label_en": "Suspected content - needs review",
            "color": "orange",
        }
    elif score <= 80:
        return {
            "level": "AI_HIGH",
            "icon": "🔴",
            "label_ar": "محتوى ذكاء اصطناعي (احتمال عالٍ)",
            "label_en": "AI content (high probability)",
            "color": "red",
        }
    else:
        return {
            "level": "AI_CERTAIN",
            "icon": "⛔",
            "label_ar": "محتوى ذكاء اصطناعي (شبه مؤكد)",
            "label_en": "AI content (near certain)",
            "color": "darkred",
        }


def analyze_text_metrics(text: str) -> Dict:
    """
    Analyze text using the 16 indicators from btec_grading_prompt Section 3.1.
    Organized in 3 levels: Linguistic (6), Structural (4), Content (6).
    Score = (sum of indicators / 16) × 100
    """
    import re
    import statistics

    # Clean text
    clean_text = text.strip()
    words = re.findall(r'\b\w+\b', clean_text)
    sentences = re.split(r'[.!?؟。]+', clean_text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(words) < 20:
        return {"total_score": 0, "metrics": {}, "indicator_count": 0, "indicators_detected": []}

    metrics = {}
    indicators_detected = []

    # 1. تكرار أنماط جمل متشابهة في البنية (Repetitive sentence patterns)
    if len(sentences) >= 3:
        sentence_lengths = [len(s.split()) for s in sentences if s]
        if sentence_lengths:
            try:
                variation = statistics.stdev(sentence_lengths) if len(sentence_lengths) > 1 else 0
                avg_len = statistics.mean(sentence_lengths)
                variation_ratio = variation / avg_len if avg_len > 0 else 0
                metrics['repetitive_patterns'] = 1 if variation_ratio < 0.3 else (0.5 if variation_ratio < 0.4 else 0)
            except Exception:
                metrics['repetitive_patterns'] = 0
    else:
        metrics['repetitive_patterns'] = 0
    if metrics['repetitive_patterns'] > 0:
        indicators_detected.append("تكرار أنماط جمل متشابهة في البنية")

    # 2. استخدام مفرط لكلمات انتقالية (Excessive transitional words)
    transitional_words = [
        'Furthermore', 'Moreover', 'Additionally', 'In conclusion',
        'علاوة على ذلك', 'بالإضافة إلى ذلك', 'في الختام', 'من ناحية أخرى',
        'وعلى الرغم من ذلك', 'بالتالي', 'لذلك', 'هكذا', 'في هذا السياق',
    ]
    transitional_count = sum(1 for w in transitional_words if w.lower() in clean_text.lower())
    metrics['excessive_transitional'] = 1 if transitional_count >= 5 else (0.5 if transitional_count >= 3 else 0)
    if metrics['excessive_transitional'] > 0:
        indicators_detected.append("استخدام مفرط لكلمات انتقالية")

    # 3. جمل طويلة ومعقدة بقواعد مثالية (Long complex sentences with perfect grammar)
    long_complex = [s for s in sentences if len(s.split()) > 25]
    long_ratio = len(long_complex) / len(sentences) if sentences else 0
    error_patterns = [r'\s{2,}', r'،{2,}', r'\.{4,}', r'(\w)\1{3,}']
    error_count = sum(len(re.findall(p, clean_text)) for p in error_patterns)
    metrics['complex_perfect_grammar'] = 1 if (long_ratio > 0.3 and error_count == 0) else (0.5 if long_ratio > 0.2 else 0)
    if metrics['complex_perfect_grammar'] > 0:
        indicators_detected.append("جمل طويلة ومعقدة بقواعد نحوية مثالية")

    # 4. غياب الأخطاء الإملائية والنحوية (Absence of spelling/grammar errors)
    metrics['no_errors'] = 1 if error_count == 0 else 0
    if metrics['no_errors'] > 0:
        indicators_detected.append("غياب الأخطاء الإملائية والنحوية بشكل كامل")

    # 5. نبرة كتابة موحدة (Uniform writing tone)
    formal_markers = [
        'علاوة على ذلك', 'بالإضافة إلى', 'من ناحية أخرى', 'في هذا السياق',
        'يتضح مما سبق', 'نستنتج أن', 'وفقاً لـ', 'استناداً إلى',
        'تجدر الإشارة', 'لا بد من', 'ثمة', 'إذ أن', 'حيث أن',
        'Furthermore', 'Moreover', 'Additionally', 'In conclusion',
        'significantly', 'demonstrate', 'utilize', 'comprehensive'
    ]
    formal_count = sum(1 for marker in formal_markers if marker in clean_text.lower())
    informal_markers = ['يعني', 'والله', 'طيب', 'هيك', 'كتير', 'اشي', 'هاد',
                        'btw', 'gonna', 'wanna', 'ok', 'yeah', 'idk']
    informal_count = sum(1 for marker in informal_markers if marker in clean_text.lower())
    # Uniform = lots of formal, zero informal
    metrics['uniform_tone'] = 1 if (formal_count >= 5 and informal_count == 0) else (0.5 if formal_count >= 3 else 0)
    if metrics['uniform_tone'] > 0:
        indicators_detected.append("نبرة كتابة موحدة دون تغيير في الأسلوب")

    # 6. استخدام مصطلحات أكاديمية عالية المستوى بشكل متسق (Consistent high-level academic terminology)
    academic_terms = [
        'paradigm', 'methodology', 'framework', 'implementation',
        'infrastructure', 'optimization', 'comprehensive', 'systematic',
        'منهجية', 'إطار عمل', 'بنية تحتية', 'تحسين', 'شامل', 'منهجي',
        'استراتيجية', 'تقنية', 'آلية', 'ديناميكي',
    ]
    academic_count = sum(1 for t in academic_terms if t.lower() in clean_text.lower())
    metrics['academic_terminology'] = 1 if academic_count >= 6 else (0.5 if academic_count >= 3 else 0)
    if metrics['academic_terminology'] > 0:
        indicators_detected.append("استخدام مصطلحات أكاديمية عالية المستوى بشكل متسق")

    # ═══════════════════════════════════════════════════════
    # المستوى 2 - التحليل الهيكلي (Structural Analysis) - 4 indicators
    # ═══════════════════════════════════════════════════════

    # 7. تنظيم مثالي للفقرات (Perfect paragraph organization)
    paragraphs = [p.strip() for p in clean_text.split('\n\n') if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in clean_text.split('\n') if p.strip()]
    structure_markers_list = [
        r'^[0-9]+[-.)]\s', r'^[-•*]\s', r'\*\*[^*]+\*\*', r'^#+\s',
        'أولاً', 'ثانياً', 'ثالثاً', 'أخيراً',
    ]
    structure_count = sum(len(re.findall(p, clean_text, re.MULTILINE)) for p in structure_markers_list)
    text_lines = [line for line in clean_text.split('\n') if line.strip()]
    total_lines = len(text_lines)
    structure_ratio = structure_count / total_lines if total_lines > 0 else 0
    metrics['perfect_organization'] = 1 if structure_ratio > 0.3 else (0.5 if structure_ratio > 0.15 else 0)
    if metrics['perfect_organization'] > 0:
        indicators_detected.append("تنظيم مثالي جداً للفقرات")

    # 8. كل فقرة تتبع نمط: مقدمة → شرح → مثال → خاتمة (Pattern following)
    pattern_score = 0.0
    if len(paragraphs) >= 3:
        para_lengths = [len(p.split()) for p in paragraphs]
        if para_lengths:
            try:
                avg_para = statistics.mean(para_lengths)
                std_para = statistics.stdev(para_lengths) if len(para_lengths) > 1 else 0
                cv_para = std_para / avg_para if avg_para > 0 else 1.0
                # Very uniform paragraph lengths = AI pattern
                if cv_para < 0.25:
                    pattern_score = 1.0
                elif cv_para < 0.4:
                    pattern_score = 0.5
            except Exception:
                pass
    metrics['paragraph_pattern'] = pattern_score
    if metrics['paragraph_pattern'] > 0:
        indicators_detected.append("كل فقرة تتبع نمط: مقدمة → شرح → مثال → خاتمة")

    # 9. انتقالات سلسة جداً بين الأقسام (Very smooth transitions)
    transition_phrases = [
        'في البداية', 'بعد ذلك', 'وعلاوة على', 'من جهة أخرى',
        'أما بالنسبة', 'فيما يتعلق', 'بالانتقال إلى', 'كما ذكرنا',
        'First', 'Second', 'Next', 'Finally', 'Moving on', 'As mentioned',
    ]
    transition_count = sum(1 for t in transition_phrases if t.lower() in clean_text.lower())
    metrics['smooth_transitions'] = 1 if transition_count >= 5 else (0.5 if transition_count >= 3 else 0)
    if metrics['smooth_transitions'] > 0:
        indicators_detected.append("انتقالات سلسة جداً بين الأقسام")

    # 10. توازن متساوٍ في طول الفقرات (Equal paragraph length balance)
    if len(paragraphs) >= 3:
        para_lengths = [len(p.split()) for p in paragraphs]
        try:
            avg_p = statistics.mean(para_lengths)
            max_dev = max(abs(pl - avg_p) for pl in para_lengths) if para_lengths else 0
            balance_ratio = max_dev / avg_p if avg_p > 0 else 1.0
            metrics['balanced_paragraphs'] = 1 if balance_ratio < 0.3 else (0.5 if balance_ratio < 0.5 else 0)
        except Exception:
            metrics['balanced_paragraphs'] = 0
    else:
        metrics['balanced_paragraphs'] = 0
    if metrics['balanced_paragraphs'] > 0:
        indicators_detected.append("توازن متساوٍ في طول الفقرات")

    # ═══════════════════════════════════════════════════════
    # المستوى 3 - تحليل المحتوى (Content Analysis) - 6 indicators
    # ═══════════════════════════════════════════════════════

    # 11. معلومات عامة دون تفاصيل شخصية (General info without personal details)
    personal_markers = [
        'في تجربتي', 'شخصياً', 'رأيي', 'أعتقد أن', 'بالنسبة لي',
        'in my experience', 'personally', 'i think', 'i believe', 'for me',
        'مشروعي', 'فصلي', 'مدرستي', 'my project', 'my class',
    ]
    personal_count = sum(1 for m in personal_markers if m.lower() in clean_text.lower())
    metrics['no_personal_details'] = 1 if personal_count == 0 else (0.5 if personal_count <= 1 else 0)
    if metrics['no_personal_details'] > 0:
        indicators_detected.append("معلومات عامة دون تفاصيل شخصية أو تجارب حقيقية")

    # 12. أمثلة نموذجية بدلاً من واقعية (Typical examples instead of real ones)
    specific_example_markers = [
        r'مثل شركة \w+', r'مثل برنامج \w+', r'مثل تطبيق \w+',
        r'such as \w+ company', r'for example,? \w+',
        r'في مدرسة', r'في شركة', r'YouTube|Google|Amazon|Netflix',
    ]
    specific_count = sum(1 for p in specific_example_markers if re.search(p, clean_text, re.IGNORECASE))
    generic_example = ['على سبيل المثال', 'for example', 'for instance', 'such as']
    generic_count = sum(1 for g in generic_example if g.lower() in clean_text.lower())
    # Many generic references but few specific = AI
    metrics['generic_examples'] = 1 if (generic_count >= 3 and specific_count <= 1) else (0.5 if generic_count >= 2 else 0)
    if metrics['generic_examples'] > 0:
        indicators_detected.append("أمثلة نموذجية بدلاً من أمثلة واقعية محددة")

    # 13. غياب المراجع الشخصية أو السياق المحلي (No personal references or local context)
    local_markers = [
        'الأردن', 'السعودية', 'مصر', 'الإمارات', 'فلسطين', 'العراق',
        'عمان', 'الرياض', 'القاهرة', 'دبي', 'بغداد',
        'jordan', 'saudi', 'egypt', 'uae', 'dubai',
        'معلمي', 'أستاذي', 'زميلي', 'صديقي',
        'my teacher', 'my friend', 'my colleague',
    ]
    local_count = sum(1 for m in local_markers if m.lower() in clean_text.lower())
    metrics['no_local_context'] = 1 if local_count == 0 else (0.5 if local_count <= 1 else 0)
    if metrics['no_local_context'] > 0:
        indicators_detected.append("غياب المراجع الشخصية أو السياق المحلي")

    # 14. معلومات دقيقة لكن سطحية (Accurate but superficial information)
    unique_words = set(words)
    word_diversity = len(unique_words) / len(words) if words else 0
    # High diversity + moderate length = broad but shallow coverage
    avg_sentence_len = len(words) / len(sentences) if sentences else 0
    metrics['accurate_superficial'] = 1 if (word_diversity > 0.7 and avg_sentence_len > 12) else (0.5 if word_diversity > 0.6 else 0)
    if metrics['accurate_superficial'] > 0:
        indicators_detected.append("معلومات دقيقة لكن سطحية")

    # 15. No repetition (AI is precise, humans repeat)
    phrases_list = re.findall(r'\b\w+\s+\w+\s+\w+\b', clean_text)
    unique_phrases_set = set(phrases_list)
    repetition_ratio = len(unique_phrases_set) / len(phrases_list) if phrases_list else 1
    metrics['no_repetition'] = 1 if repetition_ratio > 0.95 else (0.5 if repetition_ratio > 0.90 else 0)
    if metrics['no_repetition'] > 0:
        indicators_detected.append("عدم وجود تكرار (دقة عالية غير طبيعية)")

    # 16. Sentence uniformity (AI starts sentences similarly)
    uniformity_ratio = 0
    if len(sentences) >= 5:
        sentence_starts = [s.split()[0][:3] if s.split() else '' for s in sentences]  # type: ignore
        unique_starts = len(set(sentence_starts))
        uniformity_ratio = unique_starts / len(sentences) if sentences else 1
        metrics['sentence_uniformity'] = 1 if uniformity_ratio > 0.85 else (0.5 if uniformity_ratio > 0.75 else 0)
    else:
        metrics['sentence_uniformity'] = 0
    if metrics['sentence_uniformity'] > 0:
        indicators_detected.append("تجانس بنية الجمل")

    # ═══════════════════════════════════════════════════════
    # Calculate total score: (sum / 16) × 100 per btec_grading_prompt
    # ═══════════════════════════════════════════════════════
    indicator_values = [
        metrics.get('repetitive_patterns', 0),
        metrics.get('excessive_transitional', 0),
        metrics.get('complex_perfect_grammar', 0),
        metrics.get('no_errors', 0),
        metrics.get('uniform_tone', 0),
        metrics.get('academic_terminology', 0),
        metrics.get('perfect_organization', 0),
        metrics.get('paragraph_pattern', 0),
        metrics.get('smooth_transitions', 0),
        metrics.get('balanced_paragraphs', 0),
        metrics.get('no_personal_details', 0),
        metrics.get('generic_examples', 0),
        metrics.get('no_local_context', 0),
        metrics.get('accurate_superficial', 0),
        metrics.get('no_repetition', 0),
        metrics.get('sentence_uniformity', 0),
    ]

    total_score = round((sum(indicator_values) / 16) * 100, 1)

    return {
        "total_score": total_score,
        "metrics": metrics,
        "indicator_count": len([v for v in indicator_values if v > 0]),
        "indicators_detected": indicators_detected,
        "breakdown": {
            "linguistic": {
                "repetitive_patterns": indicator_values[0],
                "excessive_transitional": indicator_values[1],
                "complex_perfect_grammar": indicator_values[2],
                "no_errors": indicator_values[3],
                "uniform_tone": indicator_values[4],
                "academic_terminology": indicator_values[5],
            },
            "structural": {
                "perfect_organization": indicator_values[6],
                "paragraph_pattern": indicator_values[7],
                "smooth_transitions": indicator_values[8],
                "balanced_paragraphs": indicator_values[9],
            },
            "content": {
                "no_personal_details": indicator_values[10],
                "generic_examples": indicator_values[11],
                "no_local_context": indicator_values[12],
                "accurate_superficial": indicator_values[13],
                "no_repetition": indicator_values[14],
                "sentence_uniformity": indicator_values[15],
            },
        },
        "debug_info": {
            "repetition_ratio": round(repetition_ratio, 3) if 'repetition_ratio' in locals() else 0,  # type: ignore
            "word_diversity": round(word_diversity, 3) if 'word_diversity' in locals() else 0,  # type: ignore
            "uniformity_ratio": round(uniformity_ratio, 3) if 'uniformity_ratio' in locals() else 0  # type: ignore
        }
    }


_AI_DETECTION_PROMPT = """You are a strict AI Content Authenticity Analyzer for Arabic and English academic assignments.

Your task: estimate the probability that the following text was generated or heavily assisted by AI (e.g., ChatGPT, Gemini, Claude).

CRITICAL RULES:
- Be STRICT and realistic. Most student AI-assisted submissions score 60-90%.
- If the text reads like a Wikipedia article or textbook summary, it IS likely AI-generated.
- Do NOT be lenient. A well-structured, error-free, formal text with no personal voice is a STRONG indicator of AI.
- Give percentages that match the evidence: if 5+ indicators point to AI, the score MUST be above 70%.

ARABIC-SPECIFIC AI INDICATORS (very important):
- Use of formal Modern Standard Arabic (فصحى) without any colloquial expressions
- Phrases like: "في هذا السياق", "علاوة على ذلك", "تجدر الإشارة", "من ناحية أخرى", "يتضح مما سبق"
- Perfect comma and punctuation usage in Arabic (students typically make punctuation errors)
- Mechanical paragraph structure: definition → explanation → example → conclusion
- Generic content that reads like a textbook summary without personal experiences
- No spelling mistakes in Arabic (real students make spelling errors like تكنلوجيا vs تكنولوجيا)
- Overly balanced coverage of all topics (real students focus on what they understand)

ENGLISH AI INDICATORS:
- Phrases like: "it is important to note", "furthermore", "in conclusion", "comprehensive"
- Perfect grammar with no contractions or informal language
- Generic examples that could apply to any topic

ANALYSIS CRITERIA:

1. Writing Style: Is the tone unnaturally consistent? Is grammar too perfect for a student?
2. Linguistic Patterns: Repetitive AI expressions, generic academic connectors?
3. Original Thought: Is it all general knowledge? No personal insight or real examples?
4. Structure: Predictable definition→explanation→example? Mechanically balanced paragraphs?
5. Content Depth: Surface-level coverage of many topics vs deep understanding of few?
6. Human Signals: ANY minor errors, personal opinions, colloquial words, unique phrasing?

SCORING GUIDE:
- 0-20%: Clearly human — contains errors, personal voice, unique structure
- 20-40%: Mostly human — some AI-like phrases but has personal elements
- 40-60%: Mixed — significant AI assistance with some human editing
- 60-80%: Mostly AI — reads like AI output with minor human touches
- 80-100%: Clearly AI — textbook-like, perfect structure, no personal voice

OUTPUT FORMAT (respond in EXACTLY this format):

- Estimated AI Usage Probability: XX%
- Confidence Level: Low / Medium / High

- Detailed Justification:
  (Explain WHY with specific quotes/examples from the text)

- Final Verdict:
  One of: Likely Human Written / Mixed (Human + AI) / Likely AI Generated

Now analyze the following text:
"""

_AI_DETECTION_CACHE_VERSION = "v1"


def _ai_detection_sample_chars() -> int:
    try:
        return max(2000, int(os.getenv("AI_DETECTION_SAMPLE_CHARS", "12000")))
    except ValueError:
        return 12000


def build_ai_detection_cache_key(
    *,
    source_file_path: Optional[str] = None,
    core_text: str = "",
) -> str:
    """Stable cache key from submission file bytes or core document text only."""
    from app.archive_extraction_utils import hash_submission_file

    file_hash = hash_submission_file(source_file_path or "", "")
    if file_hash:
        return f"ai_det:{_AI_DETECTION_CACHE_VERSION}:file:{file_hash}"
    content_hash = generate_content_fingerprint(core_text or "").get("content_hash") or ""
    if content_hash:
        return f"ai_det:{_AI_DETECTION_CACHE_VERSION}:text:{content_hash}"
    sample = (core_text or "").strip()[: _ai_detection_sample_chars()]
    return f"ai_det:{_AI_DETECTION_CACHE_VERSION}:sample:{hashlib.sha256(sample.encode('utf-8')).hexdigest()}"


def _lookup_ai_detection_cache(cache_key: str) -> Optional[Dict]:
    if not cache_key:
        return None
    try:
        from app.database import SessionLocal
        from app.models import GradingCache

        db = SessionLocal()
        try:
            row = db.query(GradingCache).filter(GradingCache.fingerprint == cache_key).first()
            if row and row.result_json:
                data = json.loads(str(row.result_json))
                if isinstance(data, dict) and "ai_probability" in data:
                    return data
        finally:
            db.close()
    except Exception as exc:
        print(f"⚠️ [AI DETECTION CACHE] lookup failed: {exc}")
    return None


def _store_ai_detection_cache(cache_key: str, payload: Dict) -> None:
    if not cache_key:
        return
    try:
        from app.database import SessionLocal
        from app.models import GradingCache

        db = SessionLocal()
        try:
            blob = json.dumps(payload, ensure_ascii=False)
            existing = db.query(GradingCache).filter(GradingCache.fingerprint == cache_key).first()
            if existing:
                existing.result_json = blob  # type: ignore
                existing.prompt_hash = _AI_DETECTION_CACHE_VERSION  # type: ignore
            else:
                db.add(
                    GradingCache(
                        fingerprint=cache_key,
                        prompt_hash=_AI_DETECTION_CACHE_VERSION,
                        result_json=blob,
                    )
                )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        print(f"⚠️ [AI DETECTION CACHE] save failed: {exc}")


def _call_ai_for_detection(text: str, *, cache_key: Optional[str] = None) -> Dict:
    """
    AI likelihood score for Word-only detection text.
    In strict deterministic mode: metrics-only (no LLM, no DB cache).
    """
    from app.strict_grading_policy import (
        persist_ai_detection_cache,
        use_deterministic_ai_detection_only,
    )

    deterministic = analyze_text_metrics(text)
    det_score = deterministic.get("total_score", 0)

    if use_deterministic_ai_detection_only():
        risk_class = classify_ai_risk(det_score)
        result = {
            "ai_probability": det_score,
            "verdict": risk_class["label_en"],
            "confidence": "High",
            "full_response": "",
            "method": "deterministic_strict",
            "deterministic_score": det_score,
            "risk_classification": risk_class,
            "indicators_detected": deterministic.get("indicators_detected", []),
        }
        print(f"📐 [AI DETECTION] Strict deterministic score={det_score}% (no cache/LLM)")
        return result

    if cache_key:
        cached = _lookup_ai_detection_cache(cache_key)
        if cached:
            score = int(cached.get("ai_probability") or 0)
            print(f"✅ [AI DETECTION CACHE HIT] score={score}% key={cache_key[:28]}...")
            return cached

    # Always compute deterministic score for hybrid blending

    try:
        provider = get_global_provider()
        if not provider:
            raise RuntimeError("No AI provider available")

        sample_len = _ai_detection_sample_chars()
        sample_text = text[:sample_len] if len(text) > sample_len else text

        messages = [
            {"role": "system", "content": "You are a strict AI content detector for academic assignments. You must give HIGH percentages (70-95%) when texts show clear AI patterns: perfect grammar, formal tone, no personal voice, textbook-like structure. Be strict, not lenient. Respond in the exact format requested."},
            {"role": "user", "content": _AI_DETECTION_PROMPT + "\n\n" + sample_text}
        ]

        # Retry with fallback on connection errors
        max_detection_retries = 3
        for det_attempt in range(max_detection_retries):
            try:
                response = provider.chat_completion(
                    messages=messages,
                    temperature=0.0,
                    max_tokens=2000,
                )
                break
            except Exception as retry_err:
                err_str = str(retry_err).lower()
                conn_keywords = ["connection error", "connection refused", "connect", "timeout",
                                 "system memory", "refused", "503", "502"]
                if any(kw in err_str for kw in conn_keywords):
                    from .ai_provider import get_fallback_provider
                    fb = get_fallback_provider()
                    if fb:
                        provider = fb
                        print(f"🔄 [AI Detection] Switching to fallback provider: {fb.provider}")
                        continue
                raise retry_err
        else:
            raise RuntimeError("All providers failed for AI detection")

        if not response:
            raise RuntimeError("Empty AI response")

        # Parse probability from response
        ai_score = _parse_ai_probability(response)
        verdict = _parse_verdict(response)
        confidence = _parse_confidence(response)

        # HYBRID SCORING: blend AI opinion (60%) with deterministic metrics (40%)
        # This prevents the AI model from being too lenient
        hybrid_score = round(ai_score * 0.6 + det_score * 0.4)
        # If deterministic is very high (>=70), ensure hybrid doesn't drop below 50
        if det_score >= 70 and hybrid_score < 50:
            hybrid_score = max(hybrid_score, 50)
        # If AI says high but deterministic is low, trust the average
        hybrid_score = min(hybrid_score, 100)

        print("🤖 [AI Detection] Hybrid Analysis:")
        print(f"   📊 AI Score: {ai_score}% | Deterministic Score: {det_score}%")
        print(f"   📊 Hybrid Score: {hybrid_score}%")
        print(f"   📊 Confidence: {confidence}")
        print(f"   📊 Verdict: {verdict}")

        # Adjust verdict based on hybrid score using 5-tier classification (Section 3.3)
        risk_class = classify_ai_risk(hybrid_score)
        verdict = risk_class["label_en"]

        result = {
            "ai_probability": hybrid_score,
            "verdict": verdict,
            "confidence": confidence,
            "full_response": response,
            "method": "hybrid",
            "ai_raw_score": ai_score,
            "deterministic_score": det_score,
            "risk_classification": risk_class,
            "indicators_detected": deterministic.get("indicators_detected", []),
        }
        if cache_key and persist_ai_detection_cache():
            _store_ai_detection_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"⚠️ [AI Detection] AI call failed ({e}), falling back to deterministic analysis")
        risk_class = classify_ai_risk(det_score)
        result = {
            "ai_probability": det_score,
            "verdict": risk_class["label_en"],
            "confidence": "Low",
            "full_response": "",
            "method": "deterministic_fallback",
            "risk_classification": risk_class,
            "indicators_detected": deterministic.get("indicators_detected", []),
        }
        if cache_key and persist_ai_detection_cache():
            _store_ai_detection_cache(cache_key, result)
        return result


def _parse_ai_probability(response: str) -> int:
    """Extract AI Usage Probability percentage from AI response."""
    import re as _re
    # Match patterns like "Estimated AI Usage Probability: 35%" or "AI Usage Probability: 35%"
    match = _re.search(r'(?:Estimated\s+)?AI\s+Usage\s+Probability[:\s]*(\d{1,3})\s*%', response, _re.IGNORECASE)
    if match:
        return min(int(match.group(1)), 100)
    # Fallback: find any "XX%" near "probability" or "احتمالية"
    match = _re.search(r'(\d{1,3})\s*%', response)
    if match:
        return min(int(match.group(1)), 100)
    return 0


def _parse_verdict(response: str) -> str:
    """Extract Final Verdict from AI response."""
    import re as _re
    for verdict in ["Likely AI Generated", "Mixed (Human + AI)", "Likely Human Written",
                    "Mixed \\(Human \\+ AI\\)"]:
        if _re.search(verdict, response, _re.IGNORECASE):
            return verdict.replace("\\(", "(").replace("\\)", ")").replace("\\+", "+")
    return "Unknown"


def _parse_confidence(response: str) -> str:
    """Extract Confidence Level from AI response."""
    import re as _re
    match = _re.search(r'Confidence\s+Level[:\s]*(Low|Medium|High)', response, _re.IGNORECASE)
    if match:
        return match.group(1).capitalize()
    return "Medium"


def calculate_text_similarity(text1: str, text2: str) -> Dict:
    """
    Calculate similarity between two texts using multiple deterministic metrics.
    1. Sequence Matcher (LCS)
    2. Word Overlap (Jaccard)
    3. N-gram Overlap (3-grams)
    """
    if not text1 or not text2:
        return {"total": 0.0, "details": {}}

    # Preprocess — strip shared BTEC brief / criterion headings before scoring
    def clean(t):
        return re.sub(r'[^\w\s]', '', t.lower()).strip()

    t1_clean = clean(strip_plagiarism_boilerplate(text1))
    t2_clean = clean(strip_plagiarism_boilerplate(text2))

    if len(t1_clean) < 50 or len(t2_clean) < 50:
        return {"total": 0.0, "details": "Text too short"}

    # 1. Sequence Matcher (Standard Python - Deterministic)
    seq = difflib.SequenceMatcher(None, t1_clean, t2_clean)
    seq_ratio = seq.ratio() * 100

    # 2. Word Overlap
    words1 = set(t1_clean.split())
    words2 = set(t2_clean.split())
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    word_overlap = (len(intersection) / len(union) * 100) if union else 0

    # 3. N-gram (Trigram) Similarity
    def get_ngrams(text, n=3):
        return [text[i:i + n] for i in range(len(text) - n + 1)]

    ngrams1 = set(get_ngrams(t1_clean))
    ngrams2 = set(get_ngrams(t2_clean))

    if not ngrams1 or not ngrams2:
        ngram_sim = 0
    else:
        n_inter = ngrams1.intersection(ngrams2)
        n_union = ngrams1.union(ngrams2)
        ngram_sim = (len(n_inter) / len(n_union) * 100)

    # Weighted Average
    # Sequence is most important for direct copying
    # N-gram handles reordering well
    total = (seq_ratio * 0.5) + (ngram_sim * 0.3) + (word_overlap * 0.2)

    return {
        "total": round(total, 2),  # type: ignore
        "details": {
            "sequence": round(seq_ratio, 2),  # type: ignore
            "ngram": round(ngram_sim, 2),  # type: ignore
            "word_overlap": round(word_overlap, 2),  # type: ignore
            "matching_blocks": [b.size for b in seq.get_matching_blocks() if b.size > 10],
            "boilerplate_filtered": True,
        }
    }


def check_plagiarism_for_submission(submission_id: int, db_session):
    """
    Compare a specific submission against all other submissions in the same assignment.
    Stores detailed results in plagiarism_checks and summary in grading_summaries.
    """
    try:
        current_sub = db_session.query(Submission).get(submission_id)
        if not current_sub or not current_sub.submission_text:
            return

        print(f"🔍 [Plagiarism] Checking submission {submission_id} ({current_sub.student_name})...")

        db_session.query(PlagiarismCheck).filter(
            PlagiarismCheck.submission_id == submission_id
        ).delete(synchronize_session=False)

        # Normalize student name for comparison (strip whitespace, remove _backup suffix)
        def normalize_name(name: str) -> str:
            if not name:
                return ""
            n = name.strip().lower()
            # Remove common suffixes like _backup, _معدل, (copy), etc.
            for suffix in ['_backup', '_معدل', '_copy', ' backup', ' copy']:
                if n.endswith(suffix):
                    n = n[:-len(suffix)].strip()
            return n

        current_name_normalized = normalize_name(current_sub.student_name)

        # Get all other submissions in the same batch (classmates only — not old re-uploads)
        others = db_session.query(Submission).filter(
            Submission.assignment_id == current_sub.assignment_id,
            Submission.batch_id == current_sub.batch_id,
            Submission.id != submission_id,
            Submission.submission_text.isnot(None),
        ).all()

        # Filter out submissions from the same student (different uploads/backups)
        others = [o for o in others if normalize_name(o.student_name) != current_name_normalized]

        max_similarity = 0.0
        suspicious_count: int = 0

        for other in others:
            sim_result = calculate_text_similarity(current_sub.submission_text, other.submission_text)
            sim_score = sim_result["total"]

            check = PlagiarismCheck(
                submission_id=submission_id,
                compared_submission_id=other.id,
                assignment_id=current_sub.assignment_id,
                similarity_percentage=sim_score,
                similarity_score=sim_score,
                matching_segments=len(sim_result["details"].get("matching_blocks", [])),
                is_suspicious=(sim_score >= 26.0),
                flagged_for_review=(sim_score >= 51.0),
                details_json=json.dumps(sim_result["details"]),
            )
            db_session.add(check)

            if sim_score > max_similarity:
                max_similarity = sim_score

            if sim_score >= 26.0:  # Section 4.3: 26%+ = suspected plagiarism
                suspicious_count = suspicious_count + 1  # type: ignore

        # Update GradingSummary
        summary = db_session.query(GradingSummary).filter(GradingSummary.submission_id == submission_id).first()
        if summary:
            summary.plagiarism_max_similarity = max_similarity
            summary.plagiarism_suspicious_count = suspicious_count
        else:
            # Create if not exists (should usually exist by now or will be created soon)
            pass

        db_session.commit()
        print(f"✅ [Plagiarism] Check complete for {current_sub.student_name}. Max Sim: {max_similarity}%")

    except Exception as e:
        print(f"❌ [Plagiarism] Error checking {submission_id}: {e}")
        db_session.rollback()


async def grade_student_submission(
    student_text: str,
    reference_solution: Dict,
    grading_criteria: List[Dict],
    selected_criteria: Optional[List[str]] = None,
    source_file_path: Optional[str] = None,
    skip_grading_cache: bool = False,
    fast_mode: bool = False,
    grading_mode: Optional[str] = None,
    ai_detection_text: Optional[str] = None,
    ai_detection_cache_key: Optional[str] = None,
) -> Dict:
    """
    Grade all criteria for a single student using precise BTEC criterion-by-criterion evaluation.
    Uses a single AI call with structured output for deterministic results.
    """
    from app.strict_grading_policy import persist_grading_cache, skip_grading_cache_default

    if skip_grading_cache_default():
        skip_grading_cache = True

    if selected_criteria is None:
        # Empty = grade all criteria from assignment (BTEC unit codes like 8/B.P3)
        selected_criteria = []

    from app.archive_extraction_utils import build_grading_fingerprint, hash_submission_file

    source_hash = hash_submission_file(source_file_path or "", "")
    # Bind the cache key to the exact grader identity (FAST vs PRO resolve to different
    # models) so a mode/model change can never silently reuse an old grade.
    try:
        from app.ai_provider import resolve_grading_model

        _fp_model_version = f"{(os.getenv('AI_PROVIDER', 'gemini') or 'gemini').strip().lower()}:{resolve_grading_model(grading_mode)}"
    except Exception:
        _fp_model_version = ""
    cache_fingerprint = build_grading_fingerprint(
        source_hash,
        reference_solution,
        grading_criteria,
        selected_criteria,
        model_version=_fp_model_version,
    )

    if not skip_grading_cache:
        try:
            from app.database import SessionLocal
            from app.models import GradingCache
            _cdb = SessionLocal()
            try:
                cached = _cdb.query(GradingCache).filter(GradingCache.fingerprint == cache_fingerprint).first()
                if cached:
                    print(f"✅ [GRADING CACHE HIT] Returning cached grade (fingerprint={cache_fingerprint[:12]}...)")
                    return json.loads(cached.result_json)
            finally:
                _cdb.close()
        except Exception as e:
            print(f"⚠️ Cache lookup failed (non-fatal): {e}")
    else:
        print(f"🔄 [FORCE REGRADE] Skipping grading cache (fingerprint={cache_fingerprint[:12]}...)")

    # Helper: check if a criteria level matches selected criteria
    # Handles prefixed levels like "A.P1" matching against "P1"
    def matches_selected(level: str) -> bool:
        if not selected_criteria:
            return True
        short = level.split(".")[-1] if "." in level else level
        return level in selected_criteria or short in selected_criteria

    _text_for_rules = student_text
    if fast_mode and len(_text_for_rules) > 16_000:
        _text_for_rules = _text_for_rules[:16_000]

    from app.graders.hybrid_grader import HybridGrader
    print("📐 [HYBRID] Running rule-based pre-evaluation...")
    rule_results = HybridGrader.pre_evaluate_all(
        _text_for_rules, grading_criteria, selected_criteria
    )
    rule_context_text = HybridGrader.build_rule_context(rule_results)

    _gm = grading_mode or ("fast" if fast_mode else "deep")
    provider = get_grading_provider(_gm)
    guide_text = reference_solution.get("markdown_guide", json.dumps(reference_solution, ensure_ascii=False))
    if fast_mode and len(guide_text) > 32_000:
        try:
            from app.grading_mode_policy import FAST_MAX_GUIDE_CHARS

            _gcap = FAST_MAX_GUIDE_CHARS
        except Exception:
            _gcap = 32_000
        guide_text = (
            guide_text[:_gcap]
            + "\n\n[… اختُصر دليل المهمة في BASIC — المعايير الأساسية محفوظة …]\n"
        )

    # Build criteria descriptions for the prompt
    criteria_list_text = ""
    for criterion in grading_criteria:
        level = criterion["criteria_level"]
        if not matches_selected(level):
            continue
        desc = criterion.get("criteria_description", "")
        key_pts = criterion.get("key_points", "")
        criteria_list_text += f"\n- **{level}**: {desc}"
        if key_pts:
            criteria_list_text += f"\n  النقاط الرئيسية: {key_pts}"

    system_prompt = """أنت مقيّم Pearson BTEC معتمد في الأردن (Internal Verifier & Lead Assessor). تقوم بتقييم عمل الطالب بناءً على معايير BTEC الرسمية بشكل موضوعي 100%.

تحذير: كن **متوازناً وعادلاً** — لا تتساهل في غياب الأدلة، لكن اعترف صراحةً بالجهد والفهم الظاهر في نص الطالب عندما يغطي المتطلبات **الجوهرية** للمعيار. اقرأ عمل الطالب كاملاً وقارنه بدليل المهمة والمعايير.

═══════════════════════════════════════════════════════════
نظام Pearson BTEC الرسمي للتقييم (Criterion-Referenced):
═══════════════════════════════════════════════════════════

قاعدة أساسية: BTEC لا يستخدم نسب مئوية. كل معيار إما "Achieved" أو "Not Achieved" فقط.

1. لكل معيار، قرر إذا كان "Achieved" أو "Not Achieved" بناءً على الأدلة الفعلية في عمل الطالب.
2. المعيار يكون "Achieved" فقط إذا:
   أ) قدم الطالب أدلة واضحة وكافية تغطي متطلبات المعيار المذكورة في وصف المعيار
   ب) الأدلة تتضمن محتوى حقيقياً وليس مجرد ذكر سطحي أو نسخ
   ج) المحتوى يتوافق مع مستوى المعيار المطلوب (P أو M أو D) حسب الـ Command Verbs
3. الذكر السطحي أو النسخ بدون فهم لا يُعتبر دليلاً كافياً.
4. إذا كان الطالب قريباً من التحقيق لكن ينقصه عنصر **جوهري** من وصف المعيار = "Not Achieved". أما الثغرات **الثانوية** فلا تُنزّل وحده إلى فشل إذا كان جوهر المعيار واضحاً في أدلة الطالب (خصوصاً في معايير **Pass**).

═══════════════════════════════════════════════════════════
مستويات التقييم حسب Pearson BTEC الأردن والـ Command Verbs الرسمية:
═══════════════════════════════════════════════════════════

📌 Pass (P) - المهام الأساسية:
  Command Verbs: describe, explain, outline, identify, create, develop, produce
  ⚠️ تحذير حاسم: مستوى P ليس "سهلاً" — يجب أن يُثبت الطالب فهماً حقيقياً:
  - يتطلب وصفاً/شرحاً واضحاً ومفصلاً (ليس تعميمات أو جمل عامة)
  - يجب ذكر مفاهيم/تقنيات/تخصصات فرعية بأسمائها الصحيحة مع شرح كل منها
  - يجب ربط كل مفهوم بالسياق المطلوب في الواجب (وليس فقط سرد عناوين)
  - الوصف السطحي = Not Achieved. مجرد ذكر أسماء المكونات بدون شرح دورها الفعلي = Not Achieved
  - إذا كان معظم النص وصف عام يمكن نسخه من الإنترنت = Not Achieved
  - يجب أن يُظهر الطالب فهماً خاصاً بمشروعه (لماذا اختار هذا المكون، ما دوره تحديداً في التصميم)
  - لقطات شاشة مع **تفسير قصير يوضح الفهم** أو ربطها بالمشروع قد تُقبل كدليل لـ **Pass** إذا غطت المتطلب؛ أما لقطات بدون أي ربط أو شرح فيظل الحكم أشد صرامة
  - لا يُطلب من Pass اختبار أو تحسين أو تقييم نقدي
  - مثال Achieved: "وصف كل مكون بالتفصيل مع شرح دوره في المشروع وكيف يعمل ولماذا تم اختياره"
  - مثال Not Achieved: "ذكر أسماء المكونات فقط أو وصفها بجمل عامة بدون ربطها بالمشروع"

📌 Merit (M) - الاختبار والتحليل والتحسين:
  Command Verbs: analyze, compare, discuss, assess impact, test, refine, optimize
  - يتطلب كل ما في P بالإضافة إلى:
  - تحليل علاقات سبب-نتيجة مع شرح "كيف" و"لماذا"
  - مقارنة بين جوانب مختلفة مع تحليل التأثيرات
  - اختبار وتنقيح وتحسين الحلول
  - لا يُطلب من Merit تقييم نقدي شامل أو توصيات استراتيجية (هذه للـ Distinction)

  ⚠️ تحذير حاسم للـ Merit: يجب التحقق من "الدليل المطلوب" في المرحلة 4 بدقة:
  - لمعايير M التصميمية: ارجع إلى "التفسير التقني" في الدليل وتحقق من العناصر التقنية المحددة
  - إذا كان الدليل يطلب Subnetting ولم يقم الطالب بأي عنونة فرعية = Not Achieved
  - إذا كان الدليل يطلب خطة اختبار مفصلة مع معايير نجاح ولم توجد = Not Achieved
  - إذا كان الدليل يطلب جمع ملاحظات من الآخرين ولم يوجد دليل واضح عليها = Not Achieved
  - Merit ليس "أحسن من P" بل هو مستوى تقني مختلف تماماً — يجب أن تتوفر العناصر التقنية المحددة في الدليل

  - مثال Achieved: "الطالب قام بـ Subnetting فعلي (مثل /27) مع جدول عنونة وخطة اختبار مفصلة مع معايير نجاح"
  - مثال Not Achieved: "الطالب استخدم DHCP بدون subnetting، أو قدم خطة اختبار بسيطة بدون معايير نجاح"

📌 Distinction (D) - التقييم النقدي الشامل:
  Command Verbs: evaluate, justify, critically analyze, assess risks, recommend
  - يتطلب كل ما في P و M بالإضافة إلى:
  - حكم تقييمي واضح ومبرر (مثلاً: الفوائد تفوق المخاطر لأن...)
  - مقارنة بين قطاعات/سياقات مختلفة
  - توصيات استراتيجية عملية مبنية على التحليل
  - تقييم الفعالية والمخاطر والقيود
  - مثال Achieved: "الطالب أصدر حكماً تقييمياً مبرراً مع مقارنة بين القطاعات وقدم توصيات عملية"
  - مثال Not Achieved: "الطالب حلل لكن لم يصدر حكماً واضحاً أو لم يقدم توصيات"

═══════════════════════════════════════════════════════════
قاعدة التراكمية (Pearson BTEC الأردن) - مهم جداً:
═══════════════════════════════════════════════════════════
- لا يمكن منح الطالب Merit إلا إذا حقق جميع معايير Pass أولاً.
- لا يمكن منح الطالب Distinction إلا إذا حقق جميع معايير Pass و Merit أولاً.
- هذا يعني: قيّم كل معيار بشكل مستقل بناءً على أدلة الطالب.
- التقدير النهائي يُحدد بعد تقييم كل المعايير وفق التراكمية.

═══════════════════════════════════════════════════════════
قواعد إلزامية:
═══════════════════════════════════════════════════════════
- اقرأ عمل الطالب بالكامل من أوله لآخره قبل إصدار أي حكم.
- ابحث عن أدلة في كامل النص وليس فقط في البداية أو النهاية.
- إذا كتب الطالب بالعربية أو الإنجليزية أو كليهما، المحتوى هو المهم وليس اللغة.
- اقتبس أدلة حقيقية ومحددة من نص الطالب في حقل evidence (جملة أو فقرة فعلية).
- في حقل reasoning، اشرح بالتفصيل لماذا المعيار تحقق أو لم يتحقق بناءً على الأدلة ووصف المعيار.
- لا تُخمّن أو تُكمّل نيابة عن الطالب — إن لم يوجد أي أثر للمعيار في العمل = Not Achieved.
- **التوازن**: عند وجود أدلة حقيقية تغطي متطلبات المعيار حتى لو الصياغة ليست مثالية، فضّل **Achieved** (مع توضيح ما يمكن تحسينه في reasoning). لا ترفض عملاً مقبولاً لمجرد الشكل أو طول النص.
- **حالات التردد**: لمعايير **Pass**، إذا كان الدليل يغطي الجوهر لكنك غير متأكد = يمكن منح **Achieved** مع ذكر النقص بلطف في reasoning. لمعايير **Merit و Distinction** أبقِ العتبة أعلى: التردد هنا يميل إلى **Not Achieved** إذا لم تتوفّر عناصر المستوى بوضوح.

═══════════════════════════════════════════════════════════
🚨 قاعدة حاسمة - تحليل Vision AI ليس دليلاً:
═══════════════════════════════════════════════════════════
إذا وجدت في نص الطالب قسم بعنوان "[تحليل آلي للصور بواسطة Vision AI]":
- هذا القسم تم إنشاؤه تلقائياً بواسطة نظام الذكاء الاصطناعي لوصف الصور.
- ⛔ لا تعتبره أبداً كدليل من كتابة الطالب أو عمله الشخصي.
- ⛔ لا تستشهد بأي جملة من هذا القسم كدليل على إنجاز الطالب.
- الأدلة الحقيقية هي فقط: نص الطالب الفعلي + وجود الصور نفسها كدليل بصري.
- استخدم وصف Vision AI فقط لفهم ماذا تحتوي الصور، لكن الحكم يعتمد على نص الطالب.

═══════════════════════════════════════════════════════════
📝 قاعدة مطابقة نوع الدليل (Evidence Type Matching):
═══════════════════════════════════════════════════════════
كل معيار يتطلب نوعاً محدداً من الأدلة حسب وصفه. يجب أن يكون الدليل دقيقاً:

🔴 معايير تتطلب كود/برنامج فعلي (create, develop, implement, write program):
   → بدون ملفات برمجية (.py, .java, .cs) = Not Achieved حتماً
   → لقطات شاشة لكود داخل وورد ≠ كود فعلي قابل للتشغيل
   → وصف "قمت بإنشاء برنامج..." بدون الكود = Not Achieved

🔴 معايير تتطلب اختبار/تصحيح (test, debug, refine, improve):
   → بدون البرنامج الأصلي (ملف كود) + نتائج = Not Achieved
   → صور نتائج اختبار بدون الكود الأصلي = Not Achieved
   → خطة اختبار مكتوبة بدون تنفيذها = Not Achieved

🟢 معايير تتطلب لقطات شاشة (screenshots, evidence of running):
   → إذا توجد صور في المستند = يمكن التحقيق
   → بدون صور = Not Achieved

🟢 معايير تتطلب كتابة/شرح (describe, explain, analyze, evaluate):
   → النص المكتوب هو الدليل الكافي
   → يمكن تحقيقها من ملف وورد/PDF

🟢 معايير تتطلب تصميم/تخطيط (design, plan, flowchart):
   → يمكن تحقيقها من ملف وورد/PDF

═══════════════════════════════════════════════════════════
🎮 واجبات تطوير الألعاب (Unity / GameMaker / Godot / Scratch) — التنفيذ العملي أولاً:
═══════════════════════════════════════════════════════════
إذا كان الواجب أو دليل المهمة يتعلق بإنشاء/تطوير لعبة أو برمجة سلوك لعب:
1) لا تعتمد على ملف الوورد/الوصف النظري كدليل على التنفيذ. النص يشرح فقط؛ **الإثبات** يكون من: كود مرفوع (يظهر في النص غالباً بعد مرفق النظام الآلي)، ولقطات شاشة للعبة تعمل، ونتائج اختبار/قياس، أو أدلة لعب فعلية.
2) قبل منح Achieved لأي معيار يتطلب تنفيذاً أو اختباراً أو تحسيناً، **افحص صراحةً** في مادة الطالب (نص + مرفق كود + وصف الصور إن وُجد) ما يلي — واذكر في reasoning ما وجدته أو ما فُقد:
   • آليات اللعب (Gameplay mechanics) — هل تظهر في كود/لقطات وليس بالادعاء فقط؟
   • السكربتات (Scripts) — أسماء ملفات/دوال/أحداث واضحة في المرفق أم مجرد «تمت البرمجة»؟
   • واجهة المستخدم (UI) — لقطات HUD/قائمة/أزرار أم وصف عام؟
   • نظام النقاط (Score) — متغيرات/عرض/منطق في الكود أو لقطة تُظهر النقاط؟
   • نظام الحيوات (Lives) — نفس المعيار أعلاه.
   • المؤقت (Timer) — منطق زمني أو واجهة عدّاد؟
   • مستويات الصعوبة (Difficulty) — تفرعات كود أو إعدادات واضحة؟
   • اكتشاف التصادم (Collision) — استدعاءات فيزياء/تصادم في الكود أو سلوك ظاهر في اللقطة؟
   • أدلة الاختبار (Testing evidence) — جداول، لقطات نتائج، سجلات، حالات نجاح/فشل — **لا تقبل** «تم الاختبار» بدون أثر مادي.
   • تغذية راجعة من المستخدم (User feedback) — استبانة، تعليقات، مقابلة موثقة، لقطات — لا تقبل ادعاءً بلا أثر.
   • أدلة التحسين أو ضبط الأداء (Optimization / refinement) — مقارنة قبل/بعد، قياس أداء، إعادة هيكلة كود، نسخة ثانية في المسار — لا تقبل «تم التحسين» بلا أثر.

3) ⛔ عبارات الادعاء بدون أثر مادي = **ليست أدلة** (Not Achieved للمعيار المعني):
   «تم تنفيذ»، «تم تحسين»، «تم اختبار»، «اللعبة تعمل»، «أضفت ميزة» — **لا تعتبرها إثباتاً** إلا إذا رافقها أحد: لقطة شاشة ذات صلة، كود مطابق في المرفق، نتيجة اختبار، أو دليل لعب يظهر الميزة.

4) كشف الأدلة الضعيفة أو المزيفة (يجب الإشارة في reasoning عند الاشتباه):
   • لقطات عامة، شعارات فقط، صور من الإنترنت/متجر/بحث، صور تعليمية لا تخص المشروع.
   • لقطات لا تطابق المحرك/اللغة المذكورة في النص (مثلاً وصف Godot ولقطة Unity بدون تبرير).
   • تناقض بين ما يصفه الطالب وما يظهر في الكود المرفق أو في وصف الصور.
   • تكرار نفس اللقطة كدليل لمهام مختلفة دون تنويع.
   في هذه الحالات: **امنح Not Achieved** للمعيار الذي يعتمد على تلك اللقطة، واذكر السبب صراحةً.

5) تحليل Vision AI للصور **ليس** كتابة الطالب — استخدمه فقط لرصد ما يظهر فعلياً؛ الحكم النهائي يبقى على تطابق النص/الكود/اللقطات مع المعيار.

6) إذا وُجد في أعلى نص الطالب مرفق «تحليل كود مشروع اللعبة» آلياً: اعتبره **مصدراً تقنياً مساعداً** يجب الربط بينه وبين ادعاءات الطالب؛ إذا تعارض المرفق مع الوصف → Not Achieved مع توضيح التعارض.

7) إذا وُجد [سجل artifacts — runtime evidence governance] في نص الطالب:
   • **presence ≠ authority**: رصد .exe/.apk/.pck/build **لا يمنح** Achieved تلقائياً.
   • **runtime_evidence_level** (L0–L5) يصف ما رُصد — **ليس** verdict معيار.
   • **لا تقل** «لم يُقدّم دليل» إذا وُجدت runtime-capable artifacts — قل: «artifacts مرفقة لكن بدون runtime verification».
   • استدلال Phase 3 (screenshot intelligence) **استشاري فقط** — لا يُسمى «game verified».
   • L3 gameplay video: frame sampling + temporal hints فقط — «gameplay activity inferred» لا «gameplay verified».
   • temporal_evidence_authority ≠ runtime authority — الفيديو يرفع plausibility لا verification.
   • [Temporal Consistency]: contradictions تُخفّض authority — **لا** Not Achieved تلقائي.
   • [Evidence Trace Graph]: كل claim يجب أن يكون traceable عبر artifact → hint → authority.
   • راجع [Evidence-Authority Mapping]: claims تتجاوز max_level **ممنوعة** (game verified / criterion confirmed).
   • عند [Cross-Artifact Consistency]: ambiguity ≠ كذب تلقائي — اذكر التعارض واطلب corroboration.
   • C.P5/C.P6 قد تبقى Not Achieved إن لم يثبت التوثيق/اللقطات/الاختبار أن اللعبة تعمل — وجود الملف وحده لا يكفي.

⚠️ إذا كان الواجب يتطلب إنشاء برنامج/تطبيق/كود:
- معايير التنفيذ والبرمجة = Not Achieved (حتى لو الوصف النظري جيد)
- يمكن فقط تحقيق معايير التصميم والتخطيط النظري (إن وجدت)
- لا يمكن أن يحصل على Merit أو Distinction بدون التنفيذ العملي

═══════════════════════════════════════════════════════════
⛔ أنماط مرفوضة (= Not Achieved حتى لو ذكر الطالب المصطلحات):
═══════════════════════════════════════════════════════════
1. وصف سطحي/عام: "الراوتر من أهم الأجهزة ويستخدم في الشبكات" — هذا وصف من الإنترنت وليس دليلاً على فهم
2. سرد مكونات بدون شرح دورها: "تم استخدام Switch 2960 وRouter 2911 و5 PC" — مجرد قائمة بدون تفصيل
3. وصف ما يظهر على الشاشة: "تم إدخال عنوان IP وضغط Apply" — وصف خطوات بدون فهم
4. نسخ تعريفات: "الذكاء الاصطناعي هو محاكاة الذكاء البشري" — تعريف منسوخ بدون تطبيق
5. نقص جوهري: إذا المعيار يطلب 3 عناصر والطالب غطى عنصراً واحداً فقط = Not Achieved

═══════════════════════════════════════════════════════════
✅ أنماط مقبولة (= Achieved):
═══════════════════════════════════════════════════════════
1. شرح مفصل مع ربط بالمشروع: "اخترت Router 2911 لأنه يدعم 3 منافذ GigabitEthernet وهو مناسب لشبكتنا التي تربط 3 شبكات فرعية"
2. تحليل المتطلبات مع تبرير: "الشركة تحتاج 5 أجهزة + خادم، لذلك اخترت Switch 24-port لأنه يوفر منافذ كافية مع إمكانية التوسع"
3. فهم واضح للمفاهيم: "DHCP يوزع عناوين IP تلقائياً مما يمنع تكرار العناوين في شبكتنا المكونة من 5 أجهزة"

═══════════════════════════════════════════════════════════
📊 نظام النقاط (Score) لكل معيار:
═══════════════════════════════════════════════════════════
لكل معيار، أعطِ نقاطاً من 0 إلى 100 تعكس مدى تغطية الطالب لمتطلبات المعيار:
- 0-20: لم يذكر المعيار أو ذكر عناوين فقط بدون أي محتوى
- 21-40: ذكر سطحي أو جزئي جداً، يغطي أقل من ربع المتطلبات
- 41-60: تغطية متوسطة، بعض المتطلبات موجودة لكن ينقص محتوى جوهري
- 61-79: تغطية جيدة لكن ينقص عنصر أو عنصرين مهمين (Not Achieved لكن قريب)
- 80-100: تغطية كاملة أو شبه كاملة لجميع متطلبات المعيار (Achieved)

⚠️ النقاط مستقلة عن قرار Achieved/Not Achieved:
- معيار Achieved: لمعايير **Pass** يكفي score ≥ 70 عندما تغطي الأدلة المتطلبات الجوهرية؛ لمعايير **Merit و Distinction** فضّل score ≥ 80
- معيار Not Achieved يمكن أن يكون score بين 0-79 حسب مدى التغطية
- هذا يساعد الطالب على معرفة مستواه الحقيقي وما ينقصه

═══════════════════════════════════════════════════════════
⚖️ القاعدة الذهبية: دليل المهمة هو المرجع الأساسي (وليس وصف المعيار فقط):
═══════════════════════════════════════════════════════════
دليل المهمة المرفق ("دليل المعلم") يحتوي على قسم "المرحلة 4: تفسير معايير التقييم" وقسم "المرحلة 8: الحل النموذجي".
لكل معيار، الدليل يحدد:
1. "التفسير التقني" = ما يجب أن يفعله الطالب تحديداً (وليس فقط وصف المعيار القصير)
2. "الدليل المطلوب" = قائمة بالأدلة/المخرجات المحددة التي يجب تقديمها

⚠️ يجب عليك:
- لكل معيار، ارجع إلى "التفسير التقني" و "الدليل المطلوب" في دليل المهمة
- تحقق من كل بند محدد في "الدليل المطلوب" — هل قدم الطالب هذا الدليل فعلاً؟
- إذا افتقد لعدة **بنود جوهرية** من "الدليل المطلوب" دون تعويض واضح في النص = Not Achieved؛ أما بند ثانوي واحد مع تغطية واضحة لبقية الدليل فلا يكفي وحده لرفض المعيار
- وصف المعيار القصير (مثل "تحديد المتطلبات") ليس كافياً للحكم — الدليل هو المرجع التفصيلي

مثال تطبيقي:
- المعيار B.P3 وصفه القصير: "تحديد متطلبات المستخدم ومكونات الأجهزة والبرامج"
- لكن الدليل يحدد أن الطالب يجب أن يقدم: قائمة متطلبات منظمة + قائمة مكونات أجهزة محددة (راوتر، سويتش، نقطة وصول، كابلات، أجهزة PC، طابعة) + قائمة برمجيات محددة (Windows Server، Windows 10/11، برنامج مكافحة فيروسات)
- إذا لم يحدد الطالب البرمجيات المطلوبة بأسمائها أو لم ينظم المتطلبات = Not Achieved

مثال آخر:
- المعيار C.P5: "توصيل وتكوين واختبار بيئة شبكة أساسية"
- الدليل يحدد: توصيل كابلات + تكوين IP + إنشاء 5 حسابات مستخدمين و3 مجموعات + أذونات NTFS أساسية + تثبيت مكافحة فيروسات + اختبار ping + لقطات شاشة لكل خطوة
- إذا الطالب فقط وصف الشبكة بشكل عام دون إنشاء الحسابات والمجموعات والأذونات = Not Achieved

═══════════════════════════════════════════════════════════
☸️ فحص التحقق النهائي (يجب تنفيذه قبل إرسال الإجابة):
═══════════════════════════════════════════════════════════
1. لكل معيار P: هل راجعت "الدليل المطلوب" في دليل المهمة وتحققت من كل بند؟
2. لكل معيار P: هل الطالب فعلاً شرح/نفذ/صمم أم مجرد ذكر/سرد سطحي؟
3. لكل معيار P: هل يوجد دليل مادي (لقطات شاشة، جداول، مخططات) على التنفيذ الفعلي؟
4. هل معايير M مقيّمة بناءً على التحليل/المقارنة/الاختبار المنهجي فقط؟
5. هل معايير D مقيّمة بناءً على التقييم النقدي/التبرير/التوصيات فقط؟
6. هل أعطيت Not Achieved فقط عندما يغيب الدليل الجوهري أو الوصف سطحي حقاً دون ربط بالمشروع؟
7. هل طبّقت التردد بصرامة أكبر على **M/D** فقط، بينما عاملت **Pass** بانفتاح معقول عند وجود أدلة تغطي المتطلب؟

═══════════════════════════════════════════════════════════
📷 تحقق الأدلة العملية والأكواد (Screenshots & Code Evidence Check - دقيق ومنصف):
═══════════════════════════════════════════════════════════
بيانات الملف في أول سطر من عمل الطالب تحتوي على عدد الصور المضمنة وعدد الإشارات النصية.

قواعد واضحة للأدلة العملية (تجنّب منح تنفيذ دون أي أثر مادي):
1. إذا كان المعيار يعتمد على التنفيذ العملي أو البرمجة (مثل إنشاء برنامج، تكوين شبكة، تصميم قاعدة بيانات، اختبار):
   - إذا كان عدد الصور المضمنة = 0 ولم يرفق الطالب أي أكواد برمجية واضحة ← الطالب لم يقدم البرنامج نهائياً!
   - ⛔ الحكم الحتمي: المعيار Not Achieved مباشرة (achieved = false).
   - ⛔ الدرجة: score = 0 (أو نسبة منخفضة جداً تعكس الرسوب).
   - التبرير: "لا يمكن منح التقييم لمجرد الوصف النظري من دون إرفاق لقطات الشاشة للتطبيق العملي أو الأكواد البرمجية المطلوبة."

2. حتى لو وُجدت صور مضمنة:
   - تحقق أن الصور تُظهر فعلاً البرنامج يعمل أو نتائج التنفيذ أو أكواد حقيقية.
   - صور عامة أو ديكورية أو لقطات شاشة لا علاقة لها بالبرنامج = لا تُعتبر دليلاً على التنفيذ.
   - إذا كل الصور تُظهر واجهة البرنامج التعليمي أو تعريفات نظرية = ليست دليلاً على عمل الطالب العملي.

3. كيف تفرّق بين الوصف النظري والتطبيق الفعلي؟
   - التطبيق الفعلي يرافقه (1) لقطات شاشة للنتائج أو واجهة البرنامج، أو (2) أكواد برمجية فعلية، أو (3) مخططات فعلية.
   - قيام الطالب بكتابة "لقد قمت بإنشاء التطبيق وشغّلته" دون أي صور أو كود يُعد دليلاً نظرياً غير كافٍ = Not Achieved.

4. التراكمية (الرسوب في مستوى Pass لمنع Merit و Distinction):
   - عدم وجود العمل العملي (التطبيق/البرنامج) يعني عدم تحقيق معايير الـ Pass المرتبطة بالتنفيذ.
   - إذا لم تتحقق معايير P المتعلقة بالتنفيذ = لا يمكن منح M أو D نهائياً!

5. ⚠️ مهم: لا تعتبر النص الوصفي بديلاً كاملاً عن التطبيق الفعلي أبداً.
   - ملف وورد وحده بدون برنامج لا يمكن أن يحصل على Merit أو Distinction في واجب يتطلب برمجة.

أجب بصيغة JSON فقط بدون أي نص إضافي."""

    # Build dynamic JSON example using actual criteria levels
    active_levels = []
    for criterion in grading_criteria:
        level = criterion["criteria_level"]
        if not matches_selected(level):
            continue
        active_levels.append(level)

    json_example_items = ",\n    ".join(
        f'"{lvl}": {{"achieved": true, "score": 75, "evidence": "اقتباس من عمل الطالب كدليل", "reasoning": "تفسير القرار"}}'
        for lvl in active_levels
    ) if active_levels else '"P1": {"achieved": true, "score": 75, "evidence": "اقتباس", "reasoning": "تفسير"}'

    print("═══════════════════════════════════════")
    print("🤖 جاري التقييم الشامل...")
    print(f"📊 حجم النص: دليل={len(guide_text)} حرف، طالب={len(student_text)} حرف")
    print("═══════════════════════════════════════")

    loop = asyncio.get_running_loop()

    code_addon_instructions = ""
    if (
        "تحليل كود مشروع اللعبة" in student_text
        or "[مرفق تلقائي — تحليل كود" in student_text
    ):
        code_addon_instructions = """
═══════════════════════════════════════════════════════════
[تعليمات إضافية — مرفق تحليل كود اللعبة آلياً]
يوجد أعلى «عمل الطالب» مرفقٌ يجمع مقتطفات من ملفات المشروع (.cs / .gml / .gd / …).
- اعتمد على هذا المرفق مع لقطات الشاشة وأي جداول اختبار لاستنتاج **التنفيذ الفعلي**؛ لا تكتفِ بصياغة الوورد.
- إن تعارض ادعاء في الوورد مع الكود المرفق أو مع وصف الصور → المعيار المعني **Not Achieved** مع ذكر التعارض صراحةً.
- في حقل reasoning للمعايير التقنية، اذكر مصدر الدليل: (مرفق الكود / لقطة شاشة / جدول اختبار / …) وليس مجرد «ذكر الطالب».
═══════════════════════════════════════════════════════════
"""

    user_prompt = f"""⚠️ تعليمات إلزامية: استخدم دليل المهمة أدناه كمرجع أساسي. لكل معيار، ارجع إلى "التفسير التقني" و "الدليل المطلوب" في المرحلة 4 من الدليل. إذا افتقد الطالب **بنوداً جوهرية** من "الدليل المطلوب" دون أن يُغطيها عمله بطريقة أخرى واضحة = Not Achieved.

دليل المهمة (المرجع الأساسي للتقييم):
{guide_text}

المعايير المطلوب تقييمها:
{criteria_list_text}

{rule_context_text}
{code_addon_instructions}
==============================
عمل الطالب (اقرأه بالكامل قبل الحكم):
{student_text}
==============================

قيّم كل معيار وأجب بـ JSON فقط بالشكل التالي (استخدم نفس أسماء المعايير بالضبط):
{{
  "criteria_evaluation": {{
    {json_example_items}
  }},
  "overall_feedback": "ملخص أداء الطالب باللغة العربية",
  "strengths": ["نقطة قوة 1", "نقطة قوة 2"],
  "improvements": ["نقطة تحسين 1", "نقطة تحسين 2"]
}}"""

    if fast_mode:
        try:
            from app.grading_mode_policy import FAST_AI_MAX_RETRIES

            max_retries = FAST_AI_MAX_RETRIES
        except Exception:
            max_retries = 2
    else:
        try:
            from app.core.production_config import get_production_config

            max_retries = max(1, (get_production_config().grading_max_retries))
        except Exception:
            max_retries = 2
    response_text = None
    use_ollama_json = getattr(provider, "provider", "") == "ollama"
    json_response_format = {"type": "json_object"} if use_ollama_json else None

    for attempt in range(max_retries):
        try:
            def do_chat(extra_suffix: str = ""):
                user_content = user_prompt + extra_suffix
                return provider.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.0,
                    seed=42,  # DETERMINISTIC
                    response_format=json_response_format,
                )

            response_text = await loop.run_in_executor(None, do_chat)  # type: ignore
            break  # Success

        except Exception as e:
            error_msg = str(e)

            # 402 = insufficient credits — fail immediately, retrying won't help
            is_credits_error = "402" in error_msg
            if is_credits_error:
                print(f"❌ رصيد غير كافٍ في مزود AI: {error_msg}")
                raise RuntimeError(f"رصيد غير كافٍ في مزود AI. يرجى شحن الرصيد. التفاصيل: {error_msg}")

            is_rate_limit = any(kw in error_msg.lower() for kw in [
                "rate_limit", "413", "too large", "tokens per minute",
                "request too large", "token", "context_length", "max_tokens",
                "rate limit", "resource_exhausted"
            ])

            if is_rate_limit and attempt < max_retries - 1:
                wait_secs = 65  # 65 seconds to ensure TPM window resets
                print(f"⏳ [{attempt + 1}/{max_retries}] حد التوكن - انتظار {wait_secs} ثانية ثم إعادة محاولة...")
                await asyncio.sleep(wait_secs)
                continue
            else:
                # Try fallback provider before giving up
                is_connection_error = any(kw in error_msg.lower() for kw in [
                    "connection error", "connection refused", "connect", "timeout",
                    "system memory", "refused", "503", "502",
                ])
                if is_connection_error:
                    from .ai_provider import get_fallback_provider
                    fb = get_fallback_provider()
                    if fb:
                        provider = fb
                        print(f"🔄 [{attempt + 1}/{max_retries}] جاري المحاولة مع مزود بديل: {fb.provider}")
                        continue

                print(f"❌ خطأ أثناء التقييم: {error_msg}")
                try:
                    debug_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "recent_grade_response.txt")
                    with open(debug_path, "w", encoding="utf-8") as f:
                        f.write(f"حدث خطأ أثناء الاتصال بالمزود: {error_msg}")
                except Exception:
                    pass
                raise RuntimeError(f"فشل الاتصال بمزود AI: {error_msg}")

    if response_text is None:
        raise RuntimeError("فشل الحصول على رد من مزود AI بعد عدة محاولات")

    # Parse the structured JSON response
    from app.llm_json_utils import parse_llm_grading_json

    criteria_eval = {}
    overall_feedback = ""
    strengths = []
    improvements = []

    json_parse_attempts = 3 if use_ollama_json else 1
    parsed = None
    last_parse_err: Exception | None = None

    for parse_attempt in range(json_parse_attempts):
        try:
            parsed = parse_llm_grading_json(response_text or "")
            break
        except Exception as e:
            last_parse_err = e
            print(f"⚠️ فشل تحليل JSON (محاولة {parse_attempt + 1}/{json_parse_attempts}): {e}")
            if parse_attempt >= json_parse_attempts - 1:
                break
            retry_suffix = (
                "\n\n⚠️ الرد السابق لم يكن JSON صالحاً. "
                "أخرج كائناً JSON واحداً فقط بدون markdown. "
                "أغلق كل قوس معقوف { بـ } وليس ]. "
                "لا تضع فواصل زائدة أو نصاً خارج JSON."
            )
            try:
                def do_chat_retry():
                    return provider.chat_completion(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt + retry_suffix},
                        ],
                        temperature=0.0,
                        seed=42,
                        response_format=json_response_format,
                    )

                response_text = await loop.run_in_executor(None, do_chat_retry)  # type: ignore
            except Exception as chat_err:
                last_parse_err = chat_err
                break

    try:
        if parsed is None:
            raise last_parse_err or RuntimeError("empty AI JSON")

        criteria_eval = parsed.get("criteria_evaluation", {})
        overall_feedback = parsed.get("overall_feedback", "")
        strengths = parsed.get("strengths", [])
        improvements = parsed.get("improvements", [])
        print(f"✅ تم تحليل نتائج التقييم: {list(criteria_eval.keys())}")
    except Exception as e:
        print(f"❌ فشل تحليل JSON من رد AI: {e}")
        print(f"   Response (أول 500 حرف): {response_text[:500]}")
        # Save raw response for debugging
        try:
            debug_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "recent_grade_response.txt")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(response_text)
        except Exception:
            pass
        raise RuntimeError(f"فشل تحليل استجابة AI كـ JSON. الرجاء إعادة المحاولة. الخطأ: {e}")

    # ── Validate: AI must return at least some criteria ──
    if not criteria_eval:
        print("❌ AI أرجع criteria_evaluation فارغ!")
        raise RuntimeError("AI أرجع تقييماً فارغاً بدون أي معايير. الرجاء إعادة المحاولة.")

    # ── Normalize achieved values to proper booleans ──
    for level_key, eval_data in criteria_eval.items():
        if "achieved" in eval_data:
            val = eval_data["achieved"]
            if isinstance(val, str):
                eval_data["achieved"] = val.lower() in ("true", "yes", "1", "نعم")
            elif isinstance(val, (int, float)):
                eval_data["achieved"] = bool(val)
            # else: already bool — leave as-is

    # ── HYBRID STEP 2: Merge AI results with rule-based verdicts ──
    if criteria_eval and rule_results:
        print("🔀 [HYBRID] Merging AI evaluation with rule-based verdicts...")
        criteria_eval = HybridGrader.merge_results(criteria_eval, rule_results)

    # ── Build lookup: normalize all AI criteria keys for flexible matching ──
    def _normalize_level(lv: str) -> str:
        """Extract short level (e.g. 'A.P1' -> 'P1', 'P1' -> 'P1')"""
        return lv.split(".")[-1].strip().upper() if "." in lv else lv.strip().upper()

    ai_eval_by_short = {}
    for ai_key, ai_val in criteria_eval.items():
        short = _normalize_level(ai_key)
        ai_eval_by_short[short] = ai_val
        ai_eval_by_short[ai_key] = ai_val  # Also keep original

    # Build criteria_results from structured evaluation
    criteria_results = []
    for criterion in grading_criteria:
        level = criterion["criteria_level"]
        if not matches_selected(level):
            continue

        # Flexible matching: try exact, then short, then normalized
        eval_data = criteria_eval.get(level, {})
        if not eval_data and "." in level:
            short_level = level.split(".")[-1]
            eval_data = criteria_eval.get(short_level, {})
        if not eval_data:
            # Reverse: try normalized lookup
            norm = _normalize_level(level)
            eval_data = ai_eval_by_short.get(norm, {})

        is_achieved = eval_data.get("achieved", False)
        evidence = eval_data.get("evidence", "")
        reasoning = eval_data.get("reasoning", "")
        ai_score = eval_data.get("score", None)

        # Use AI's partial score if available, otherwise binary
        if ai_score is not None:
            try:
                ai_score = int(ai_score)
                ai_score = max(0, min(100, ai_score))  # Clamp 0-100
            except (ValueError, TypeError):
                ai_score = 100 if is_achieved else 0
        else:
            ai_score = 100 if is_achieved else 0

        feedback = reasoning if reasoning else ("تم اجتياز المعيار." if is_achieved else "لم يتم اجتياز المعيار.")

        criteria_results.append({
            "criteria_level": level,
            "achieved": is_achieved,
            "score": ai_score,
            "feedback": feedback,
            "decision_matrix": [{"requirement": level, "met": is_achieved, "evidence": evidence, "reasoning": reasoning}],
            "covered_points": [evidence] if is_achieved and evidence else [],
            "missing_points": [reasoning] if not is_achieved and reasoning else []
        })

        print(f"   📋 {level}: {'✅ Achieved' if is_achieved else '❌ Not Achieved'} - {reasoning[:80]}")

    # ── Safety check: warn if no criteria matched AI response ──
    matched_count = sum(1 for r in criteria_results if r.get("feedback", "") != "لم يتم اجتياز المعيار." or r["achieved"])
    if criteria_results and matched_count == 0:
        print("⚠️ تحذير: لم يتطابق أي معيار مع استجابة AI!")
        print(f"   معايير مطلوبة: {[r['criteria_level'] for r in criteria_results]}")
        print(f"   معايير من AI: {list(criteria_eval.keys())}")

    # Sort criteria P → M → D for consistent display order
    def _criteria_sort_key(r):
        lv = r.get('criteria_level', '')
        short = lv.split('.')[-1] if '.' in lv else lv
        _order = {'P': 0, 'M': 1, 'D': 2}
        letter = short[0].upper() if short else 'Z'
        try:
            num = int(short[1:]) if len(short) > 1 else 0
        except ValueError:
            num = 99
        return (_order.get(letter, 9), num)

    criteria_results.sort(key=_criteria_sort_key)

    _pre_gov_grade = determine_grade_level(criteria_results)
    _pre_gov_pct = int(
        sum(r.get("score", 0) for r in criteria_results) / (len(criteria_results) or 1)
    )
    _gov_stub = {
        "grade_level": _pre_gov_grade,
        "percentage": _pre_gov_pct,
        "total_score": _pre_gov_pct,
        "criteria_results": criteria_results,
        "overall_feedback": overall_feedback if overall_feedback else response_text,
    }
    try:
        from app.btec_criteria_governance import apply_btec_criteria_governance

        apply_btec_criteria_governance(_gov_stub)
        criteria_results = _gov_stub["criteria_results"]
        overall_feedback = _gov_stub.get("overall_feedback") or overall_feedback
    except Exception as _gov_err:
        print(f"⚠️ [BTEC-GOV] single-grade path skipped: {_gov_err}")

    # Normalize grade_level using determine_grade_level for consistency
    grade_level = _gov_stub.get("grade_level") or determine_grade_level(criteria_results)

    # Calculate percentage from actual criterion scores (partial credit)
    achieved_count = sum(1 for r in criteria_results if r["achieved"])
    total_count = len(criteria_results) if criteria_results else 1
    percentage = _gov_stub.get("percentage") or 0
    if not percentage:
        total_score_sum = sum(r.get("score", 0) for r in criteria_results)
        percentage = int(total_score_sum / total_count) if total_count > 0 else 0

    print(f"🎯 Grade Level: {grade_level} | Achieved: {achieved_count}/{total_count} | Avg Score: {percentage}%")

    # Generate content fingerprint (Section 2.1)
    content_fp = generate_content_fingerprint(student_text)

    # AI detection uses core document text only (stable across regrades / vision / code addons)
    det_text = (ai_detection_text or student_text).strip()
    det_cache_key = ai_detection_cache_key or build_ai_detection_cache_key(
        source_file_path=source_file_path,
        core_text=det_text,
    )
    ai_detection = _call_ai_for_detection(det_text, cache_key=det_cache_key)
    ai_likelihood_score = ai_detection.get("ai_probability", 0)

    final_result = {
        "total_score": percentage,
        "max_score": 100,
        "percentage": percentage,
        "grade_level": grade_level,
        "criteria_results": criteria_results,
        "overall_feedback": overall_feedback if overall_feedback else response_text,
        "strengths": strengths,
        "improvements": improvements,
        "ai_likelihood": ai_likelihood_score,
        "content_fingerprint": content_fp,
        "ai_detection_info": {
            "score": ai_likelihood_score,
            "risk_classification": ai_detection.get("risk_classification", classify_ai_risk(ai_likelihood_score)),
            "indicators_detected": ai_detection.get("indicators_detected", []),
            "verdict": ai_detection.get("verdict", ""),
            "confidence": ai_detection.get("confidence", ""),
            "method": ai_detection.get("method", ""),
            "cache_key": det_cache_key,
        },
    }

    # ── GRADING CACHE: save result for future determinism (disabled in strict mode) ──
    try:
        from app.strict_grading_policy import persist_grading_cache

        if not persist_grading_cache():
            print("📐 [GRADING CACHE] Skipped save — strict deterministic mode")
        else:
            from app.database import SessionLocal
            from app.models import GradingCache
            _cdb = SessionLocal()
            try:
                result_payload = json.dumps(final_result, ensure_ascii=False)
                existing = _cdb.query(GradingCache).filter(GradingCache.fingerprint == cache_fingerprint).first()
                if existing:
                    if skip_grading_cache:
                        existing.result_json = result_payload  # type: ignore
                        existing.prompt_hash = cache_fingerprint[:16]  # type: ignore
                        _cdb.commit()
                        print(
                            f"💾 [GRADING CACHE UPDATE] Replaced cache after force regrade "
                            f"(fingerprint={cache_fingerprint[:12]}...)"
                        )
                else:
                    _cdb.add(GradingCache(
                        fingerprint=cache_fingerprint,
                        prompt_hash=cache_fingerprint[:16],
                        result_json=result_payload,
                    ))
                    _cdb.commit()
                    print(f"💾 [GRADING CACHE SAVE] Stored grade (fingerprint={cache_fingerprint[:12]}...)")
            finally:
                _cdb.close()
    except Exception as e:
        print(f"⚠️ Cache save failed (non-fatal): {e}")

    return final_result


from app.btec_grade_resolution import determine_grade_level


_IMAGE_FILE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_EXECUTABLE_EXT = set(EXECUTABLE_ARTIFACT_EXTENSIONS)
_GAME_ENGINE_IDS = frozenset(
    {"unity", "godot", "gamemaker", "unreal", "construct", "scratch", "pygame"}
)


def build_grading_coverage_notice(
    *,
    image_count: int,
    vision_extracted_count: int,
    image_analysis_text: str,
    vision_error: Optional[str],
    is_document_only: bool,
    has_code_files: bool,
    submission_paths: List[str],
    project_profile: Dict,
    artifact_inventory: Optional[Dict] = None,
) -> Dict:
    """
    Arabic transparency block: what was NOT analyzed or used in grading.
    Returned dict is stored on grading_snapshot_json as grading_coverage_notice.
    """
    lines: List[str] = []

    folder_image_names: List[str] = []
    executable_names: List[str] = []
    for raw in submission_paths or []:
        try:
            fp = Path(raw)
            if not fp.is_file():
                continue
            suf = fp.suffix.lower()
            if suf in _IMAGE_FILE_EXT:
                folder_image_names.append(fp.name)
            elif suf in _EXECUTABLE_EXT:
                executable_names.append(fp.name)
        except (OSError, ValueError):
            continue

    profile = project_profile or {}
    rt = profile.get("runtime_evidence") or {}
    runtime_shots = rt.get("screenshot_candidates") or []
    runtime_shot_count = len(runtime_shots)

    # ── Images (embedded in Word/PDF) ──
    if image_count > 0:
        if vision_error:
            lines.append(
                f"الصور المضمّنة في المستند ({image_count}) لم تُصحَّح بصرياً: فشل تحليل Vision ({vision_error})."
            )
        elif vision_extracted_count == 0:
            lines.append(
                f"الصور المضمّنة في المستند ({image_count}) لم تُستخرج أو لم تُحلَّل (قد تكون أيقونات صغيرة)."
            )
        elif not (image_analysis_text or "").strip():
            lines.append(
                f"الصور المضمّنة في المستند ({image_count}) لم تُصحَّح بصرياً (مزود Vision لم يُرجع وصفاً)."
            )
        elif is_document_only and not (image_analysis_text or "").strip():
            lines.append(
                f"وُجدت {image_count} صورة مضمّنة في مستند Word/PDF؛ تحليل الصور **لم يُستخدم** في التصحيح "
                "لأن التسليم «مستند فقط» دون ملفات مشروع/كود مرفقة خارج المستند."
            )
        elif (image_analysis_text or "").strip():
            lines.append(
                f"تم تحليل {vision_extracted_count or 'بعض'} صورة/لقطة **مضمّنة داخل Word/PDF** "
                f"من أصل {image_count} — أدلة Person BTEC بصرية."
            )

    # ── Images in submission folders (e.g. سكرينات / صور تشغيل) ──
    folder_only = len(folder_image_names)
    l2_block = (artifact_inventory or {}).get("l2_l3_corroborative_runtime") or {}
    l2_ingested = int(l2_block.get("l2_count") or 0)
    if l2_ingested > 0:
        sample = "، ".join(
            str(x.get("basename") or "")
            for x in (l2_block.get("l2_folder_screenshots") or [])[:4]
            if isinstance(x, dict) and x.get("basename")
        )
        lines.append(
            f"لقطات L2 corroborative ({l2_ingested}): ({sample}) **دخلت** سلسلة الأدلة التشغيلية — "
            f"{l2_block.get('institutional_phrasing_ar', '')} "
            "**لم تُمنح** سلطة معيار تلقائياً."
        )
        for amb in (l2_block.get("ambiguity_flags") or [])[:3]:
            if isinstance(amb, dict) and amb.get("message_ar"):
                lines.append(f"[ambiguity preserved] {amb['message_ar']}")
    elif folder_only > 0 and runtime_shot_count == 0:
        sample = "، ".join(folder_image_names[:4])
        if folder_only > 4:
            sample += f" (+{folder_only - 4} أخرى)"
        lines.append(
            f"توجد {folder_only} صورة في ملفات التسليم ({sample}) **لم تُصحَّح** ولم تُؤخذ في الاعتبار عند التصحيح "
            "(النظام يحلّل صور Word المضمّنة فقط، ولقطات المجلدات لا تُعامل تلقائياً إلا إذا طابقت مسار لقطات التشغيل)."
        )
    elif runtime_shot_count > 0 and not has_code_files and is_document_only:
        names = "، ".join(
            str(r.get("basename") or "") for r in runtime_shots[:4] if isinstance(r, dict)
        )
        lines.append(
            f"وُجدت {runtime_shot_count} لقطة شاشة في المجلد ({names}) **لم تُحلَّل بصرياً** في التصحيح "
            "(تسليم مستند فقط)."
        )

    # ── Packet Tracer / network programs ──
    pt = profile.get("packet_tracer_evidence") or {}
    pkt_files = pt.get("pkt_files") or []
    extractions = pt.get("extractions") or []
    if pkt_files:
        readable = [e for e in extractions if e.get("readable")]
        unreadable = [e for e in extractions if not e.get("readable")]
        pkt_names = "، ".join(Path(str(p)).name for p in pkt_files[:3])
        if unreadable and not readable:
            err = (unreadable[0].get("decode_error") or "صيغة غير مدعومة أو ملف مشفّر")
            lines.append(
                f"ملف(ات) Packet Tracer ({pkt_names}) **لم تُصحَّح**: تعذّر فك الملف واستخراج دليل الشبكة ({err}). "
                "لم يُشغَّل المحاكي."
            )
        else:
            lines.append(
                f"ملف(ات) Packet Tracer ({pkt_names}) فُحصت بنيتها آلياً فقط؛ **لم يُشغَّل** Cisco Packet Tracer "
                "ولم يُتحقق من التشغيل الفعلي للشبكة."
            )

    engines = profile.get("engines_detected") or []
    if has_code_files and any(str(e).lower() in _GAME_ENGINE_IDS for e in engines):
        lines.append(
            "وُجدت ملفات مشروع/كود؛ التصحيح يعتمد على قراءة الملفات والنص **دون تشغيل** اللعبة أو المحاكي."
        )
    elif has_code_files and "cisco_packet_tracer" not in engines:
        lines.append(
            "وُجدت ملفات برمجية؛ التصحيح يعتمد على قراءة الشفرة **دون تشغيل** البرنامج للتحقق من السلوك."
        )

    if executable_names:
        sample = "، ".join(executable_names[:3])
        lines.append(
            f"ملف(ات) تنفيذية ({sample}) **رُصدت** ضمن التسليم — "
            "**لم تُشغَّل** ولم يُتحقق من التشغيل الفعلي (runtime verification unavailable)."
        )

    inv = artifact_inventory or {}
    exec_block = inv.get("executable_artifacts") or {}
    if exec_block.get("status") == "detected_not_executed" and not executable_names:
        sample = "، ".join(f["name"] for f in exec_block.get("files", [])[:3])
        lines.append(
            f"ملف(ات) تنفيذية ({sample}) **رُصدت** في artifact_inventory — "
            "**لم تُشغَّل** ولم يُمنح أي معيار سلطة تشغيل."
        )

    consistency = inv.get("cross_artifact_consistency") or {}
    for amb in (consistency.get("ambiguities") or [])[:4]:
        msg = amb.get("message_ar")
        if msg:
            lines.append(f"[consistency ambiguity] {msg}")

    gvi = inv.get("gameplay_video_inference") or {}
    if (gvi.get("videos_analyzed") or 0) > 0:
        hints = (gvi.get("video_analysis") or {}).get("runtime_hints") or []
        uncorroborated = sum(1 for h in hints if not h.get("corroboration_present"))
        if hints:
            lines.append(
                f"فيديو gameplay (L3): {gvi.get('frames_sampled')} frame(s) — "
                f"{len(hints)} runtime hint(s) — "
                f"{'بدون corroboration' if uncorroborated == len(hints) else 'corroboration جزئي'} — "
                "**plausibility ≠ authority**."
            )
    elif l2_block.get("entered_chain") and (l2_block.get("l3_video_evidence") or {}).get("videos_detected"):
        l3 = l2_block.get("l3_video_evidence") or {}
        lines.append(
            f"فيديو L3 ({l3.get('videos_detected', 0)}): "
            f"{l3.get('institutional_label_ar', 'نشاط تشغيلي مُلاحَظ ضمن شروط أدلة محدودة')} — "
            "**temporal hint ≠ criterion confirmation**."
        )

    tc = inv.get("temporal_consistency") or {}
    for sig in (tc.get("temporal_consistency_signals") or [])[:3]:
        msg = sig.get("message_ar")
        if msg:
            lines.append(f"[temporal consistency] {msg}")

    if not lines:
        return {"text_ar": "", "items": [], "has_gaps": False, "evidence_coverage_matrix": []}

    header = "📋 نطاق التصحيح الآلي (حدود السلطة — presence ≠ authority)"
    body = "\n".join(f"• {ln}" for ln in lines)
    matrix = inv.get("evidence_coverage_matrix") or build_evidence_coverage_matrix(inv)
    return {
        "text_ar": f"{header}\n{body}",
        "items": [{"message": ln} for ln in lines],
        "has_gaps": True,
        "evidence_coverage_matrix": matrix,
        "artifact_inventory": inv,
    }


async def grade_batch_async(
    student_files: List[Dict],  # [{"name": "...", "path": "...", "email": "..."}]
    reference_solution: Dict,
    grading_criteria: List[Dict],
    selected_criteria: Optional[List[str]] = None,
    max_workers: int = 5,
    progress_callback=None,
    start_callback=None,
    phase_callback: Optional[Callable[[str, str, float], Any]] = None,
    skip_grading_cache: bool = False,
    grading_mode: str = "deep",
    cancel_check: Optional[Callable[[], bool]] = None,
) -> List[Dict]:
    """
    Grade multiple students in parallel

    Returns list of results with student info
    """
    results = []

    def _phase(name: str, phase: str, progress: float) -> None:
        if phase_callback:
            phase_callback(name, phase, progress)

    fast_mode = (grading_mode or "deep").strip().lower() == "fast"
    try:
        from app.grading_mode_policy import grading_flags

        _mode_flags = grading_flags(grading_mode)
    except Exception:
        _mode_flags = {
            "skip_runtime_observation": False,
            "fast_runtime_smoke": fast_mode,
            "skip_godot_pck_analysis": fast_mode,
            "skip_gameplay_video_inference": fast_mode,
            "skip_l2_l3_corroborative": fast_mode,
            "skip_heavy_governance_graphs": fast_mode,
            "skip_ai_evidence_reasoning": fast_mode,
            "skip_visual_verification": fast_mode,
            "light_project_profile": fast_mode,
            "compact_code_addon": fast_mode,
            "parallel_batch_grading": fast_mode,
            "skip_post_grade_artifact_rebuild": fast_mode,
        }
    # PRO batch: skip slow secondary AI layers (main grade + runtime/vision kept).
    if not fast_mode and len(student_files) > 1:
        _mode_flags["skip_ai_evidence_reasoning"] = True
        if len(student_files) > 8:
            _mode_flags["skip_institutional_resolution"] = True
    if fast_mode:
        print("⚡ [STANDARD] Fast path — Word Vision + lightweight Runtime smoke (no gameplay agent)")
    elif len(student_files) > 1:
        print(
            "🔬 [PRO] gemini-pro + Runtime/Vision; "
            "compact code; skip L2/L3 corroborative + governance graphs/drift"
        )

    async def grade_single_student(student_info: Dict) -> Dict:
        try:
            if cancel_check and cancel_check():
                print(f"⏹️ [BATCH] Abort {student_info.get('name')} — cancel requested")
                return {
                    "student_name": student_info.get("name", ""),
                    "student_email": student_info.get("email", ""),
                    "student_id": student_info.get("student_id", ""),
                    "file_path": student_info.get("path", ""),
                    "success": False,
                    "cancelled": True,
                    "error": "cancelled_by_user",
                    "total_score": 0,
                    "max_score": 0,
                    "percentage": 0,
                }
            from app.grading_mode_policy import (
                enrich_student_submission_flags,
                extract_fast_grading_text,
                resolve_word_document_paths,
            )

            enrich_student_submission_flags(student_info)
            _phase(student_info["name"], "extracting", 0.12)

            submission_paths_early = student_info.get("submission_paths") or [
                str(student_info["path"])
            ]
            _loop = asyncio.get_running_loop()

            async def _run_extract_stage() -> tuple[str, str, int, str, int]:
                word_only_text, word_doc_image_count = await _loop.run_in_executor(
                    None,
                    extract_fast_grading_text,
                    str(student_info.get("path") or ""),
                    list(submission_paths_early),
                )
                word_doc_paths = resolve_word_document_paths(
                    str(student_info.get("path") or ""),
                    list(submission_paths_early),
                )
                word_doc_path = word_doc_paths[0] if word_doc_paths else None

                if fast_mode:
                    student_text = word_only_text
                    image_count = word_doc_image_count
                else:
                    _cached_preview = str(student_info.get("_text_preview") or "").strip()
                    if len(_cached_preview) >= 50:
                        student_text = _cached_preview
                    else:
                        student_text = await _loop.run_in_executor(
                            None,
                            extract_text_from_file,
                            student_info["path"],
                        )
                    image_count = await _loop.run_in_executor(
                        None,
                        DocumentProcessor.count_images,
                        student_info["path"],
                    )
                    if word_doc_image_count > image_count:
                        image_count = word_doc_image_count
                return (
                    word_only_text,
                    student_text,
                    image_count,
                    word_doc_path or "",
                    word_doc_image_count,
                )

            try:
                word_only_text, student_text, image_count, _word_doc_path_str, word_doc_image_count = (
                    await asyncio.wait_for(_run_extract_stage(), timeout=180.0)
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    "انتهت مهلة استخراج نص ملف الطالب (3 دقائق) — "
                    "أغلق Word إن كان الملف مفتوحاً ثم أعد التصحيح."
                )
            word_doc_path = _word_doc_path_str or None
            _phase(student_info["name"], "extracting", 0.22)
            print(f"📄 [DEBUG] Extracted text for {student_info['name']}: {len(student_text)} chars")
            core_ai_detection_text = (word_only_text or student_text).strip()
            print(
                f"🤖 [AI-DETECT] Word-only corpus: {len(core_ai_detection_text)} chars "
                f"(grading prompt may include code/vision separately)"
            )
            print(f"🖼️ [DEBUG] Found {image_count} embedded images/screenshots in {student_info['name']}'s file")

            # Count text references to screenshots/figures
            screenshot_refs = len(re.findall(r'(?:شكل|الشكل|صورة|لقطة|screenshot|figure|fig\.|الصورة)', student_text, re.IGNORECASE))
            print(f"📝 [DEBUG] Found {screenshot_refs} screenshot/figure references in text")

            # ══════════════════════════════════════════════════════════════════
            # IMAGE VISION: Word/PDF/PPTX embedded images only (BASIC + PRO)
            # ══════════════════════════════════════════════════════════════════
            image_analysis_text = ""
            vision_extracted_count = 0
            vision_success_count = 0
            vision_attempted = False
            vision_batches: List[Dict[str, Any]] = []
            vision_error: Optional[str] = None
            vision_completed = False
            _video_kf_meta: Dict[str, Any] = {}
            _pre_has_code = bool(student_info.get("has_code_files"))
            _pre_has_exe = bool(student_info.get("has_executable_artifacts"))
            _pre_ext = Path(student_info["path"]).suffix.lower()
            _pre_doc_only = (
                _pre_ext in (".docx", ".doc", ".pdf", ".pptx")
                and not _pre_has_code
                and not _pre_has_exe
            )
            try:
                from app.grading_mode_policy import (
                    effective_basic_max_vision_images,
                    is_word_embedded_vision_document,
                    pro_max_vision_images_for_submission,
                )

                _primary_is_doc = is_word_embedded_vision_document(str(student_info["path"]))
            except Exception:
                _primary_is_doc = _pre_ext in (".docx", ".doc", ".pdf", ".pptx")
                effective_basic_max_vision_images = lambda: 10  # type: ignore
                pro_max_vision_images_for_submission = lambda **_: 5  # type: ignore

            if fast_mode:
                _run_word_vision = bool(
                    _mode_flags.get("word_embedded_vision")
                    or _mode_flags.get("basic_video_keyframes")
                )
            else:
                _run_word_vision = image_count > 0 and _primary_is_doc

            if _run_word_vision:
                try:
                    from app.ai_provider import get_vision_provider, ollama_model_supports_vision

                    _vision_provider_probe = get_vision_provider(
                        grading_mode or ("fast" if fast_mode else "deep")
                    )
                    if (
                        _vision_provider_probe.provider == "ollama"
                        and not ollama_model_supports_vision(_vision_provider_probe.model)
                    ):
                        print(
                            f"ℹ️ [VISION] Skipping — {_vision_provider_probe.model} "
                            "is text-only (set OLLAMA_VISION_MODEL=qwen3-vl:8b)."
                        )
                        _run_word_vision = False
                        vision_error = "vision_model_not_supported"
                except Exception:
                    pass

            if _run_word_vision:
                _phase(student_info["name"], "vision", 0.28)
                try:
                    _mode_label = "BASIC" if fast_mode else "PRO"
                    print(
                        f"🔍 [VISION/{_mode_label}] Extracting embedded images from "
                        f"{student_info['name']}'s document (Word/PDF only)..."
                    )
                    if fast_mode:
                        from app.grading_mode_policy import (
                            basic_max_video_keyframe_total,
                            basic_max_video_keyframes,
                            effective_basic_max_vision_images,
                        )

                        _word_vision_cap = effective_basic_max_vision_images()
                        _video_kf_per = basic_max_video_keyframes()
                        _video_kf_cap = basic_max_video_keyframe_total()
                    else:
                        _word_vision_cap = pro_max_vision_images_for_submission(
                            has_code_files=_pre_has_code,
                            has_executable_artifacts=_pre_has_exe,
                            document_only=_pre_doc_only,
                        )
                        _video_kf_per = 0
                        _video_kf_cap = 0
                    print(
                        f"🔍 [VISION] word_cap={'all' if _word_vision_cap <= 0 else _word_vision_cap} "
                        f"video_cap={_video_kf_per}/video total={_video_kf_cap} "
                        f"({'Word-only' if _pre_doc_only else 'doc+project'})"
                    )
                    extracted_images: List = []
                    if image_count > 0 and _primary_is_doc:
                        extracted_images = DocumentProcessor.extract_images(
                            student_info["path"], max_images=_word_vision_cap
                        )

                    video_keyframe_images: List = []
                    if fast_mode and _mode_flags.get("basic_video_keyframes") and _video_kf_per > 0:
                        from app.basic_video_keyframes import (
                            extract_basic_video_keyframe_images,
                            merge_basic_vision_images,
                        )

                        video_keyframe_images, _video_kf_meta = extract_basic_video_keyframe_images(
                            student_info,
                            max_frames_per_video=_video_kf_per,
                        )
                        if _video_kf_meta.get("frames_extracted"):
                            print(
                                f"🎬 [BASIC-VIDEO] {student_info['name']}: "
                                f"{_video_kf_meta['frames_extracted']} keyframe(s) "
                                f"({_video_kf_meta.get('frames_per_video', _video_kf_per)}/video) from "
                                f"{_video_kf_meta.get('videos_found', 0)} video(s)"
                            )
                        elif _video_kf_meta.get("errors"):
                            print(
                                f"⚠️ [BASIC-VIDEO] {student_info['name']}: "
                                f"{'; '.join(_video_kf_meta['errors'][:2])}"
                            )

                    _word_vision_take = (
                        extracted_images
                        if _word_vision_cap <= 0
                        else extracted_images[:_word_vision_cap]
                    )
                    if fast_mode:
                        from app.basic_video_keyframes import merge_basic_vision_images

                        word_vision_images = list(_word_vision_take)
                        vision_images, _vision_stats = merge_basic_vision_images(
                            extracted_images,
                            video_keyframe_images,
                            max_word=_word_vision_cap,
                            max_video=_video_kf_cap,
                        )
                        _word_cap_label = "all" if _word_vision_cap <= 0 else str(_word_vision_cap)
                        print(
                            f"🔍 [VISION/BASIC] word={_vision_stats['word_images']}/{_word_cap_label} "
                            f"video={_vision_stats['video_keyframes']}/{_video_kf_cap} "
                            f"total={_vision_stats['total_vision']}"
                        )
                    else:
                        word_vision_images = list(_word_vision_take)
                        vision_images = word_vision_images

                    vision_extracted_count = len(vision_images)
                    print(f"🔍 [VISION] Prepared {vision_extracted_count} image(s) for analysis")

                    if vision_images or word_vision_images or video_keyframe_images:
                        from app.ai_provider import get_vision_provider, merge_vision_lane_results

                        _vision_mode = grading_mode or ("fast" if fast_mode else "deep")
                        vision_provider = get_vision_provider(_vision_mode)
                        print(
                            f"🔍 [VISION] Analyzing docx={len(word_vision_images)} "
                            f"video_kf={len(video_keyframe_images)} "
                            f"with {vision_provider.provider}/{vision_provider.model}..."
                        )

                        loop = asyncio.get_running_loop()
                        _has_code = student_info.get("has_code_files", False)
                        _vision_ctx_doc = (
                            f"واجب طالب BTEC Person: {student_info['name']}. "
                            "هذه لقطات مضمّنة داخل Word/PDF (embedded screenshots)."
                        )
                        _vision_ctx_video = (
                            f"واجب طالب BTEC Person: {student_info['name']}. "
                            "هذه مقتطفات keyframe من فيديو تشغيل اللعبة (BASIC)."
                        )
                        _evidence_mode = "game" if _has_code else None

                        async def _analyze_lane_cancellable(
                            lane_images: List,
                            lane_ctx: str,
                        ) -> Dict[str, Any]:
                            if not lane_images:
                                return {}
                            if cancel_check and cancel_check():
                                return {
                                    "text": "",
                                    "images_submitted": len(lane_images),
                                    "images_analyzed": 0,
                                    "vision_attempted": True,
                                    "vision_completed": False,
                                    "vision_error": "cancelled_by_user",
                                    "vision_batches": [],
                                }
                            _lane_bs = 1 if vision_provider.provider == "ollama" else 2
                            chunks = [
                                lane_images[i : i + _lane_bs]
                                for i in range(0, len(lane_images), _lane_bs)
                            ]
                            parts: List[str] = []
                            analyzed = 0
                            last_err: Optional[str] = None
                            for ci, chunk in enumerate(chunks, start=1):
                                if cancel_check and cancel_check():
                                    return {
                                        "text": "\n\n".join(parts),
                                        "images_submitted": len(lane_images),
                                        "images_analyzed": analyzed,
                                        "vision_attempted": True,
                                        "vision_completed": False,
                                        "vision_error": "cancelled_by_user",
                                        "vision_batches": [],
                                    }

                                def _run_chunk(
                                    _chunk=chunk,
                                    _ctx=lane_ctx,
                                    _ci=ci,
                                    _total=len(chunks),
                                ) -> Dict[str, Any]:
                                    ctx = _ctx
                                    if _total > 1:
                                        ctx += (
                                            f"\n\n(دفعة {_ci}/{_total} — "
                                            f"{len(_chunk)} صورة/لقطة في هذه الدفعة)"
                                        )
                                    return vision_provider.analyze_images_resilient(
                                        _chunk,
                                        context=ctx,
                                        temperature=0.0,
                                        evidence_mode=_evidence_mode,
                                        batch_size=1,
                                    )

                                chunk_res = await loop.run_in_executor(None, _run_chunk)
                                if cancel_check and cancel_check():
                                    return {
                                        "text": "\n\n".join(parts),
                                        "images_submitted": len(lane_images),
                                        "images_analyzed": analyzed,
                                        "vision_attempted": True,
                                        "vision_completed": False,
                                        "vision_error": "cancelled_by_user",
                                        "vision_batches": [],
                                    }
                                t = str(chunk_res.get("text") or "").strip()
                                if t:
                                    parts.append(t)
                                analyzed += int(
                                    chunk_res.get("images_analyzed") or len(chunk)
                                )
                                err = str(chunk_res.get("vision_error") or "").strip()
                                if err:
                                    last_err = err
                            merged_text = "\n\n".join(parts)
                            return {
                                "text": merged_text,
                                "images_submitted": len(lane_images),
                                "images_analyzed": analyzed,
                                "vision_attempted": True,
                                "vision_completed": bool(merged_text),
                                "vision_error": last_err or "",
                                "vision_batches": [],
                            }

                        word_res = await _analyze_lane_cancellable(
                            word_vision_images, _vision_ctx_doc
                        )
                        if cancel_check and cancel_check():
                            return {
                                "student_name": student_info.get("name", ""),
                                "student_email": student_info.get("email", ""),
                                "student_id": student_info.get("student_id", ""),
                                "file_path": student_info.get("path", ""),
                                "success": False,
                                "cancelled": True,
                                "error": "cancelled_by_user",
                                "total_score": 0,
                                "max_score": 0,
                                "percentage": 0,
                            }
                        video_res = (
                            await _analyze_lane_cancellable(
                                video_keyframe_images, _vision_ctx_video
                            )
                            if video_keyframe_images
                            else None
                        )
                        if cancel_check and cancel_check():
                            return {
                                "student_name": student_info.get("name", ""),
                                "student_email": student_info.get("email", ""),
                                "student_id": student_info.get("student_id", ""),
                                "file_path": student_info.get("path", ""),
                                "success": False,
                                "cancelled": True,
                                "error": "cancelled_by_user",
                                "total_score": 0,
                                "max_score": 0,
                                "percentage": 0,
                            }
                        _vision_result = merge_vision_lane_results(word_res, video_res)
                        image_analysis_text = str(_vision_result.get("text") or "")
                        vision_extracted_count = int(_vision_result.get("images_submitted") or len(vision_images))
                        vision_success_count = int(_vision_result.get("images_analyzed") or 0)
                        vision_attempted = bool(_vision_result.get("vision_attempted"))
                        vision_completed = bool(_vision_result.get("vision_completed"))
                        vision_error = str(_vision_result.get("vision_error") or "") or None
                        vision_batches = list(_vision_result.get("vision_batches") or [])

                        if vision_completed and image_analysis_text:
                            print(
                                f"✅ [VISION] Image analysis complete: {len(image_analysis_text)} chars "
                                f"({vision_success_count}/{vision_extracted_count} images)"
                            )
                            try:
                                debug_dir = Path("uploads/debug")
                                debug_dir.mkdir(parents=True, exist_ok=True)
                                img_debug_file = debug_dir / f"{student_info['name']}_images_analysis.txt"
                                with open(img_debug_file, "w", encoding="utf-8") as f:
                                    f.write(image_analysis_text)
                            except Exception:
                                pass
                        elif vision_attempted:
                            print(
                                f"⚠️ [VISION] Attempted {vision_extracted_count} image(s) — "
                                f"analyzed {vision_success_count}; error={vision_error or 'empty_vision_response'}"
                            )
                        else:
                            print("⚠️ [VISION] No analysis returned (provider may not support vision)")
                except Exception as e:
                    vision_error = str(e)
                    print(f"⚠️ [VISION] Image analysis failed (non-fatal): {e}")
                _phase(student_info["name"], "vision", 0.38)
            elif image_count > 0 and fast_mode and not _primary_is_doc:
                vision_error = "basic_vision_word_embedded_only"
            elif image_count > 0 and fast_mode:
                vision_error = "skipped_in_fast_mode"

            submission_paths = student_info.get("submission_paths")
            if not submission_paths:
                submission_paths = [str(student_info["path"])]
            try:
                from app.evidence_completeness_gate import expand_submission_paths

                submission_paths = expand_submission_paths(
                    list(submission_paths),
                    primary_path=str(student_info.get("path") or ""),
                    student_name=str(student_info.get("name") or ""),
                    grading_mode=grading_mode,
                )
            except Exception:
                pass

            project_profile_for_audit: Dict = {}
            if _mode_flags.get("ultra_light_project_profile"):
                try:
                    from app.grading_mode_policy import build_ultra_light_project_profile

                    project_profile_for_audit = build_ultra_light_project_profile(
                        list(submission_paths)
                    )
                except Exception as _pie_early:
                    print(f"⚠️ [PROJECT_INTELLIGENCE] ultra-light skipped: {_pie_early}")
            else:
                try:
                    from app.project_intelligence import build_project_profile

                    project_profile_for_audit = build_project_profile(
                        list(submission_paths),
                        intake_relative_paths=student_info.get("intake_relative_paths"),
                        lightweight=_mode_flags.get("light_project_profile", False),
                    )
                except Exception as _pie_early:
                    print(f"⚠️ [PROJECT_INTELLIGENCE] early profile skipped: {_pie_early}")

            _runtime_enabled = any(
                _mode_flags.get(k)
                for k in (
                    "enable_gamemaker_runtime_verification",
                    "enable_web_browser_automation",
                    "enable_android_emulator_automation",
                    "enable_scratch_runtime_verification",
                )
            )
            if _runtime_enabled:
                _phase(student_info["name"], "runtime", 0.34)
            else:
                _phase(student_info["name"], "inventory", 0.34)
            _inv_loop = asyncio.get_running_loop()
            from functools import partial

            artifact_inventory = await _inv_loop.run_in_executor(
                None,
                partial(
                    build_artifact_inventory,
                    main_document_path=str(student_info["path"]),
                    submission_paths=list(submission_paths),
                    embedded_image_count=image_count,
                    vision_analysis_used=bool(
                        vision_completed
                        and vision_extracted_count > 0
                        and (image_analysis_text or "").strip()
                    ),
                    vision_analysis_text=image_analysis_text or "",
                    vision_extracted_count=vision_extracted_count,
                    project_profile=project_profile_for_audit or None,
                    batch_id=student_info.get("batch_id"),
                    student_name=str(student_info.get("name") or ""),
                    skip_runtime_observation=_mode_flags.get("skip_runtime_observation", False),
                    skip_heavy_enrichment=fast_mode,
                    skip_l2_l3_corroborative=_mode_flags.get("skip_l2_l3_corroborative", False),
                    skip_governance_graphs=_mode_flags.get("skip_heavy_governance_graphs", False),
                    skip_gameplay_video_when_runtime_verified=_mode_flags.get(
                        "skip_gameplay_video_when_runtime_verified", False
                    ),
                    minimal_mode=_mode_flags.get("minimal_artifact_inventory", False),
                    grading_mode=grading_mode,
                ),
            )
            _phase(student_info["name"], "inventory", 0.40)
            has_executable_artifacts = bool(
                student_info.get("has_executable_artifacts")
                or artifact_inventory.get("has_executable_artifacts")
            )
            has_code_files = bool(
                student_info.get("has_code_files")
                or artifact_inventory.get("has_source_code_artifacts")
            )

            # ══════════════════════════════════════════════════════════════════
            # DETECT DOCUMENT-ONLY SUBMISSION (no code / executable artifacts)
            # ══════════════════════════════════════════════════════════════════
            file_ext = Path(student_info["path"]).suffix.lower()
            is_document_only = (
                file_ext in ('.docx', '.doc', '.pdf', '.pptx')
                and not has_code_files
                and not has_executable_artifacts
            )
            print(
                f"📋 [FILE-TYPE] {student_info['name']}: ext={file_ext}, "
                f"has_code_files={has_code_files}, has_executable_artifacts={has_executable_artifacts}, "
                f"document_only={is_document_only}"
            )

            if fast_mode:
                try:
                    from app.grading_mode_policy import format_fast_artifact_context

                    student_text = format_fast_artifact_context(artifact_inventory) + student_text
                except Exception:
                    student_text = format_artifact_context_for_grading(artifact_inventory) + student_text
            else:
                student_text = format_artifact_context_for_grading(artifact_inventory) + student_text
                _obs_ctx = ""
                try:
                    from app.runtime_observation_sandbox import format_observation_for_grading

                    _obs_ctx = format_observation_for_grading(
                        artifact_inventory.get("runtime_observation_report") or {}
                    )
                    if _obs_ctx:
                        student_text = _obs_ctx + "\n\n" + student_text
                except Exception:
                    pass
                _auth_map = artifact_inventory.get("authority_mapping") or {}
                _auth_txt = format_authority_mapping_for_grading(_auth_map)
                if _auth_txt:
                    student_text = _auth_txt + student_text
                _consistency = artifact_inventory.get("cross_artifact_consistency") or {}
                _consistency_txt = format_consistency_report_for_grading(_consistency)
                if _consistency_txt:
                    student_text = _consistency_txt + student_text
                if not _mode_flags.get("skip_l2_l3_corroborative"):
                    try:
                        from app.l2_l3_corroborative_runtime import (
                            format_corroborative_runtime_for_grading_prompt,
                        )

                        _l2l3_txt = format_corroborative_runtime_for_grading_prompt(
                            artifact_inventory.get("l2_l3_corroborative_runtime") or {}
                        )
                        if _l2l3_txt:
                            student_text = _l2l3_txt + student_text
                    except Exception:
                        pass

            # Prepend image metadata AND image analysis to student text
            if image_count > 0 or screenshot_refs > 0:
                image_metadata = f"\n[معلومات الملف: يحتوي المستند على {image_count} صورة/لقطة شاشة مضمنة، و {screenshot_refs} إشارة نصية إلى صور أو أشكال]\n"

                if is_document_only and not (fast_mode and image_analysis_text):
                    # PRO document-only: Vision excluded (no external project files).
                    # BASIC: Word-embedded Vision IS used as Person BTEC evidence.
                    print(
                        f"🚫 [VISION-STRIPPED] {student_info['name']}: "
                        "Document-only PRO — Vision excluded from grading text"
                    )
                    image_metadata += (
                        "\n⚠️ [ملاحظة النظام]: لا توجد ملفات مشروع/كود/تنفيذية مرفقة خارج المستند.\n"
                        "الصور المضمّنة ليست دليل تنفيذي يغني عن تسليم APK/.exe أو كود (.gml، .py، …).\n"
                        "لا تقيّم Achieved للمعايير التي تصرّح صراحةً بوجوب إرفاق كود تنفيذي أو ملف لعبة.\n"
                        "مع ذلك، المعايير المتعلقة بمراجعة التصميم، التغذية الراجعة، والنسخة المحسنة من وثيقة التصميم (GDD v2)،\n"
                        "وخطط ونتائج الاختبار الموصوفة كتابياً، يمكن تحقيقها من النص الوارد في هذا المستند إن كانت كافية.\n\n"
                    )
                elif image_analysis_text:
                    _vision_hdr = (
                        "BASIC — Word/PDF" if fast_mode else "Vision AI"
                    )
                    image_metadata += (
                        f"\n═══════════════════════════════════════════\n"
                        f"⚠️ [تحليل آلي للصور المضمّنة في المستند ({_vision_hdr}) — "
                        f"ليس من كتابة الطالب!]\n"
                        f"📷 وصف الأدلة البصرية (GDD/اختبار/لعبة):\n"
                        f"═══════════════════════════════════════════\n"
                        f"{image_analysis_text}\n"
                        f"═══════════════════════════════════════════\n"
                        f"⚠️ [انتهى التحليل الآلي - ما يلي هو نص الطالب الفعلي]\n\n"
                    )

                student_text = image_metadata + student_text

            # Add document-only warning for AI grader
            if is_document_only:
                if fast_mode:
                    doc_only_warning = (
                        "\n[BASIC — تسليم مستند فقط: لا exe/كود مرفق؛ معايير التنفيذ/الكود → Not Achieved؛ "
                        "معايير GDD/اختبار نصية قابلة للتقييم من الوورد.]\n\n"
                    )
                else:
                    doc_only_warning = (
                        "\n🚫🚫🚫 [تحذير من النظام — تسليم مستند فقط] 🚫🚫🚫\n"
                        "التسليم: ملف وورد/PDF دون مشروع أو ملفات كود خارجية (.gml، .yyz، .py، .apk، إلخ).\n"
                        "لقطات الشاشة داخل الملف لا تعتبر كودًا قابلاً للتسليم وليست دليل تنفيذي كامل.\n"
                        "→ المعايير التي تطلب ملف تنفيذي أو كود مصدري حقيقياً لا يمكن إشباعها؛ امنحها Not Achieved.\n"
                        "→ المعايير النصّية الوثائقية (مراجعات التصميم، تحديث GDD، جداول خطط الاختبار، تحليل تغذية راجعة موصوف)\n"
                        "يمكن تقييمها من النص إن كان الطالب وثّقها بوضوح — لا تجعل «غياب الملف التنفيذي» سبباً لرفض GDD المنقّح وحده.\n"
                        "🚫🚫🚫 [انتهى التحذير] 🚫🚫🚫\n\n"
                    )
                student_text = doc_only_warning + student_text
            elif has_executable_artifacts:
                exe_names = ", ".join(
                    f["name"]
                    for f in (artifact_inventory.get("executable_artifacts") or {}).get("files", [])[:5]
                )
                _obs_rep = artifact_inventory.get("runtime_observation_report") or {}
                if _obs_rep.get("status") == "completed":
                    runtime_warning = (
                        "\n⚠️ [Runtime Observation Sandbox — L4]\n"
                        f"ملفات: {exe_names}\n"
                        f"runtime_verified: {_obs_rep.get('runtime_verified')} | "
                        f"level: L{_obs_rep.get('runtime_evidence_level', 4)}\n"
                        "→ استخدم signals + التوثيق لـ C.P5/C.P6 — observations ≠ verified achievement.\n\n"
                    )
                else:
                    runtime_warning = (
                        "\n⚠️ [حدود السلطة — artifacts تنفيذية مرفقة]\n"
                        f"ملفات تنفيذية مُرصدَة: {exe_names}\n"
                        "→ وجود .exe/.apk **لا يمنح** Achieved تلقائياً لـ C.P5/C.P6.\n\n"
                    )
                student_text = runtime_warning + student_text

            if student_info.get("has_code_files") or artifact_inventory.get("has_source_code_artifacts"):
                if _mode_flags.get("compact_code_addon"):
                    try:
                        from app.grading_mode_policy import (
                            FAST_MAX_CODE_FILES,
                            PRO_COMPACT_CHARS_PER_SIDE,
                            PRO_COMPACT_PER_FILE_CAP,
                            PRO_MAX_CODE_FILES,
                        )

                        if fast_mode:
                            _mcf = FAST_MAX_CODE_FILES
                            _side = 6_000
                            _cap = 1_800
                        else:
                            _mcf = PRO_MAX_CODE_FILES
                            _side = PRO_COMPACT_CHARS_PER_SIDE
                            _cap = PRO_COMPACT_PER_FILE_CAP
                    except Exception:
                        _mcf, _side, _cap = (10 if fast_mode else 16, 6_000, 1_800)
                    code_addon = build_dual_version_grading_addon(
                        submission_paths,
                        max_chars_per_side=_side,
                        per_file_cap=_cap,
                        max_code_files=_mcf,
                        compact=True,
                    )
                else:
                    code_addon = build_dual_version_grading_addon(submission_paths)
                if code_addon.strip():
                    student_text = code_addon + "\n\n" + student_text
                    print(
                        f"💻 [CODE-ADDON] {student_info['name']}: appended "
                        f"dual-version code context ({len(code_addon)} chars)"
                    )

            if not _mode_flags.get("ultra_light_project_profile"):
                try:
                    from app.project_intelligence import format_profile_for_grading_prompt

                    if not project_profile_for_audit:
                        from app.project_intelligence import build_project_profile

                        project_profile_for_audit = build_project_profile(
                            list(submission_paths),
                            intake_relative_paths=student_info.get("intake_relative_paths"),
                            lightweight=_mode_flags.get("light_project_profile", False),
                        )
                    _pi_txt = format_profile_for_grading_prompt(project_profile_for_audit)
                    if _pi_txt:
                        student_text = _pi_txt + "\n\n" + student_text
                        print(
                            f"🧭 [PROJECT_INTELLIGENCE] {student_info['name']}: "
                            f"engines={project_profile_for_audit.get('engines_detected')}"
                        )
                except Exception as _pie:
                    print(f"⚠️ [PROJECT_INTELLIGENCE] skipped: {_pie}")
            elif project_profile_for_audit.get("notes_ar"):
                student_text = (
                    f"[محرك المشروع — BASIC]\n{project_profile_for_audit.get('notes_ar')}\n\n"
                    + student_text
                )

            if not fast_mode:
                try:
                    debug_dir = Path("uploads/debug")
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    debug_file = debug_dir / f"{student_info['name']}_extracted.txt"
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(student_text)
                except Exception as e:
                    print(f"⚠️ Failed to save debug text: {e}")

            if len(student_text.strip()) < 50:
                raise ValueError(f"Extracted text is too short ({len(student_text.strip())} chars). Encrypted PDF or empty file?")

            try:
                from app.grading_mode_policy import truncate_pro_student_text_for_ai

                student_text = truncate_pro_student_text_for_ai(
                    student_text, grading_mode=grading_mode
                )
            except Exception:
                pass

            # Grade the submission (now async) — heartbeat keeps UI moving during long AI calls
            _phase(student_info["name"], "grading", 0.42)
            heartbeat_stop = asyncio.Event()

            async def _grading_heartbeat() -> None:
                t = 0.0
                while not heartbeat_stop.is_set():
                    await asyncio.sleep(3)
                    if heartbeat_stop.is_set():
                        break
                    t += 3.0
                    # Cap UI band during Gemini — real completion is on_student_done (1/1).
                    sp = min(0.72, 0.42 + 0.35 * (1 - math.exp(-t / 45.0)))
                    _phase(student_info["name"], "grading", sp)

            heartbeat_task = asyncio.create_task(_grading_heartbeat())
            try:
                grading_result = await grade_student_submission(
                    student_text,
                    reference_solution,
                    grading_criteria,
                    selected_criteria,
                    source_file_path=word_doc_path or student_info.get("path"),
                    skip_grading_cache=skip_grading_cache,
                    fast_mode=fast_mode,
                    grading_mode=grading_mode,
                    ai_detection_text=core_ai_detection_text,
                    ai_detection_cache_key=build_ai_detection_cache_key(
                        source_file_path=word_doc_path or student_info.get("path"),
                        core_text=core_ai_detection_text,
                    ),
                )
            finally:
                heartbeat_stop.set()
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            _phase(student_info["name"], "grading", 0.92)

            # Post-AI layers (BTEC governance, Pearson PRO, DB) are synchronous and long —
            # keep UI progress moving so 92% does not look frozen.
            _post_ai_stop = threading.Event()

            def _post_ai_progress_pulse() -> None:
                sp = 0.92
                phase_steps = ("grading", "finalizing", "saving")
                step = 0
                while not _post_ai_stop.wait(4.0):
                    sp = min(0.98, sp + 0.012)
                    phase = phase_steps[min(step, len(phase_steps) - 1)]
                    _phase(student_info["name"], phase, sp)
                    if sp >= 0.945 and step < len(phase_steps) - 1:
                        step += 1

            _post_ai_thread = threading.Thread(
                target=_post_ai_progress_pulse,
                name=f"post_ai_progress_{student_info.get('name', '')[:24]}",
                daemon=True,
            )
            _post_ai_thread.start()
            _grade_loop = asyncio.get_running_loop()
            try:
                from functools import partial

                grading_result = await _grade_loop.run_in_executor(
                    None,
                    partial(
                        _finalize_grading_result_after_ai,
                        grading_result=grading_result,
                        student_info=student_info,
                        grading_criteria=grading_criteria,
                        grading_mode=grading_mode,
                        _mode_flags=_mode_flags,
                        artifact_inventory=artifact_inventory,
                        submission_paths=submission_paths,
                        student_text=student_text,
                        word_only_text=word_only_text,
                        image_count=image_count,
                        image_analysis_text=image_analysis_text,
                        vision_extracted_count=vision_extracted_count,
                        vision_success_count=vision_success_count,
                        vision_attempted=vision_attempted,
                        vision_completed=vision_completed,
                        vision_error=vision_error,
                        vision_batches=vision_batches,
                        _video_kf_meta=_video_kf_meta,
                        is_document_only=is_document_only,
                        fast_mode=fast_mode,
                        has_code_files=has_code_files,
                        has_executable_artifacts=has_executable_artifacts,
                        project_profile_for_audit=project_profile_for_audit,
                        core_ai_detection_text=core_ai_detection_text,
                        skip_grading_cache=skip_grading_cache,
                    ),
                )
            finally:
                _post_ai_stop.set()
                _post_ai_thread.join(timeout=2.0)
                _phase(student_info["name"], "saving", 0.98)

            print(f"✅ تم تصحيح: {grading_result['student_name']} - {grading_result.get('percentage', 0)}%")
            return grading_result

        except Exception as e:
            print(f"Error grading {student_info['name']}: {e}")
            return {
                "student_name": student_info["name"],
                "student_email": student_info.get("email", ""),
                "student_id": student_info.get("student_id", ""),
                "file_path": student_info["path"],
                "success": False,
                "error": str(e),
                "total_score": 0,
                "max_score": 0,
                "percentage": 0
            }

    def _finalize_grading_result_after_ai(
        *,
        grading_result: Dict,
        student_info: Dict,
        grading_criteria: List[Dict],
        grading_mode: str,
        _mode_flags: Dict,
        artifact_inventory: Dict,
        submission_paths: List,
        student_text: str,
        word_only_text: str,
        image_count: int,
        image_analysis_text: str,
        vision_extracted_count: int,
        vision_success_count: int,
        vision_attempted: bool,
        vision_completed: bool,
        vision_error: Optional[str],
        vision_batches: List,
        _video_kf_meta: Dict,
        is_document_only: bool,
        fast_mode: bool,
        has_code_files: bool,
        has_executable_artifacts: bool,
        project_profile_for_audit: Dict,
        core_ai_detection_text: str,
        skip_grading_cache: bool,
    ) -> Dict:
        # ==================== VALIDATE GRADING RESULT ====================
            # Ensure all required fields exist with proper values
            print(f"\n🔍 [VALIDATION] Checking grading result for {student_info['name']}")
            print(f"   Keys present: {list(grading_result.keys())}")

            validation_warnings = []

            # Validate and fix total_score
            if "total_score" not in grading_result:
                validation_warnings.append("Missing 'total_score' - setting to 0")
                grading_result["total_score"] = 0
            elif not isinstance(grading_result["total_score"], (int, float)):
                validation_warnings.append(f"Invalid 'total_score' type: {type(grading_result['total_score'])}")
                grading_result["total_score"] = 0

            # Validate and fix max_score
            if "max_score" not in grading_result:
                validation_warnings.append("Missing 'max_score' - setting to 400")
                grading_result["max_score"] = 400  # Default for 4 criteria × 100
            elif not isinstance(grading_result["max_score"], (int, float)) or grading_result["max_score"] <= 0:
                validation_warnings.append(f"Invalid 'max_score': {grading_result.get('max_score')}")
                grading_result["max_score"] = 400

            # Validate and fix percentage
            if "percentage" not in grading_result:
                # Recalculate from total_score and max_score
                if grading_result["max_score"] > 0:
                    grading_result["percentage"] = round((grading_result["total_score"] / grading_result["max_score"]) * 100)
                else:
                    grading_result["percentage"] = 0
                validation_warnings.append(f"Missing 'percentage' - recalculated to {grading_result['percentage']}%")
            elif not isinstance(grading_result["percentage"], (int, float)):
                validation_warnings.append(f"Invalid 'percentage' type: {type(grading_result['percentage'])}")
                grading_result["percentage"] = 0

            # Validate and fix grade_level
            if "grade_level" not in grading_result or not grading_result.get("grade_level"):
                validation_warnings.append("Missing 'grade_level' - will recalculate")
                # Try to determine from criteria_results if available
                criteria_results = grading_result.get("criteria_results", [])
                if criteria_results:
                    grading_result["grade_level"] = determine_grade_level(criteria_results)
                else:
                    grading_result["grade_level"] = "U - غير مصنف (Unclassified)"

            # Validate and fix ai_likelihood
            if "ai_likelihood" not in grading_result:
                validation_warnings.append("Missing 'ai_likelihood' - setting to 0")
                grading_result["ai_likelihood"] = 0
            elif not isinstance(grading_result["ai_likelihood"], (int, float)):
                validation_warnings.append(f"Invalid 'ai_likelihood' type: {type(grading_result['ai_likelihood'])}")
                grading_result["ai_likelihood"] = 0

            # Ensure criteria_results exists
            if "criteria_results" not in grading_result:
                validation_warnings.append("Missing 'criteria_results' - setting to empty list")
                grading_result["criteria_results"] = []

            # Log warnings if any
            if validation_warnings:
                print(f"\n⚠️ [VALIDATION] Found {len(validation_warnings)} issue(s) with grading result:")
                for warning in validation_warnings:
                    print(f"   ⚠️ {warning}")
                print("   ✅ Applied fixes - result should now be valid\n")
            else:
                print("   ✅ All fields valid\n")

            # ══════════════════════════════════════════════════════════════════
            # EVIDENCE TYPE CLASSIFICATION & VALIDATION
            # Analyze each criterion's DESCRIPTION (from BTEC spec) to determine
            # what type of evidence is required, then validate the submission matches.
            #
            # Evidence types:
            # - "code": criterion asks for creating/writing/developing a program/code
            # - "screenshots": criterion asks for screenshots/images as evidence
            # - "test": criterion asks for testing/debugging a program
            # - "text": criterion asks for description/explanation/analysis (writing)
            # - "design": criterion asks for design/plan/flowchart
            #
            # Rules:
            # - If criterion requires "code" but no code files → Not Achieved
            # - If criterion requires "screenshots" and images exist → OK
            # - If criterion requires "test" but no code files → Not Achieved
            # - "text" criteria can be achieved from Word docs
            # - "design" criteria can be achieved from Word docs
            # ══════════════════════════════════════════════════════════════════

            # Build a map of criteria descriptions from the original grading_criteria
            criteria_desc_map = {}
            for gc in grading_criteria:
                lvl = gc.get("criteria_level", "")
                desc = gc.get("criteria_description", "")
                name = gc.get("criteria_name", "")
                kp = gc.get("key_points", [])
                if isinstance(kp, list):
                    kp_text = " ".join(kp)
                else:
                    kp_text = str(kp)
                criteria_desc_map[lvl] = {
                    "description": desc,
                    "name": name,
                    "key_points": kp_text,
                    "full_text": f"{name} {desc} {kp_text}",
                }

            # Patterns to detect evidence type from criterion description
            _DESIGN_PEER_GDD_FOCUS = re.compile(
                r'gdd(?:_v?\d+|v?\s*2\.?0?)?|game\s+design\s+document|'
                r'(?:gdd\s*v?\s*2)|(?:v\s*2\.?\s*(?:محسنة|محسَّنة)?).*تصميم|نسخ(?:ة|\s+)\s*(?:محسنة|محسَّنة|ثانية).*تصميم|'
                r'محسَّن(?:ة|\s|$).*تصميم|مراجع[ةه]\s+(?:التصميم|الوثيق|مع\s+)'
                r'|peer\s+review|revision\s+(?:to|of)?\s*(?:the\s+)?design'
                r'|feedback\s+(?:was\s+)?used\s+(?:to|for)\s+(?:update|revise).*design'
                r'|وثيق[ةه]\s+(?:ب)?تصميم|تصميم\s+(?:إلكترونية\s+)?اللعبة',
                re.IGNORECASE,
            )

            _REQUIRES_SOURCE_OR_EXECUTABLE = re.compile(
                r'source\s+code|(?:full|complete)\s+source|كود\s*مصدر|كود\s*مصدري(?:\s|ات|$)?|ملف(?:ات)?\s*(برمجية|شفرة|مصدر)'
                r'|\bapk\b|\bipa\b|\bexe\b|runnable\b|executable\b|working\s+(?:prototype\s+)?implementation\b'
                r'|\b(?:\.py|\.cs|\.java|\.cpp|\.c|\.gml|\.gd|\.html|\.jsx|\.tsx|\.js)\b'
                r'|قابل(?:ة)?\s*للتشغيل|ملف\s*تنفيذي|التنفيذ\s*الحي',
                re.IGNORECASE,
            )

            _REQUIRES_CODE = re.compile(
                r'creat(?:e|ing)\s+(?:a\s+)?(?:program|application|app|software|code|script|function|class|module)|'
                r'develop\s+(?:a\s+)?(?:program|application|app|software|code|solution)|'
                r'write\s+(?:a\s+)?(?:program|code|script|function)|'
                r'\bimplement\b\s+(?:a\s+|an\s+|the\s+)?(?:software|program|application|solution|interactive\s+)'
                r'(?:game\s+features?)?|'
                r'إنشاء\s*(?:برنامج|تطبيق|كود|برمجة|حل\s*برمجي)|'
                r'كتابة\s*(?:برنامج|كود|شفرة)|'
                r'تطوير\s*(?:برنامج|تطبيق|نظام)|'
                r'\b(?:programming|coding)\b\s+(?:project|skill|task)|'
                r'برمجة(?:\s+ال(?:كود|مشروع|لعبة))?|تنفيذ\s+(?:برنامج|تطبيق|الحل|النظام)\b|'
                r'build\s+(?:a\s+)?(?:program|app|system)',
                re.IGNORECASE,
            )
            _REQUIRES_TEST = re.compile(
                r'test(?:ing)?\s+(?:the\s+)?(?:program|application|code|solution|software)\b|'
                r'debug(?:ging)?\s+(?:the\s+)?(?:program|application|code|solution)\b|'
                r'fix(?:ing)?\s+(?:errors?|bugs?|issues?)\s+(?:in\s+)?(?:the\s+)?(?:program|application|code|solution)\b|'
                r'\bimprove\b\s+(?:the\s+)?(?:code|program|solution)\b|'
                r'\brefin(?:e|ing)\b\s+(?:the\s+)?(?:code|program|solution)\b|'
                r'اختبار\s+(?:البرنامج|التطبيق|الكود|الحل)\b|'
                r'تصحيح\s+(?:الأخطاء\s+في\s+)?(?:البرنامج|الكود|التطبيق)\b|'
                r'تحسين\s+(?:البرنامج|الكود|الحل)\b|'
                r'معالجة\s+(?:الأخطاء|الاستثناءات)\s+(?:في\s+)?(?:البرنامج|الكود)\b',
                re.IGNORECASE
            )
            _REQUIRES_SCREENSHOTS = re.compile(
                r'screenshot|screen\s*shot|capture|لقطة\s*شاشة|صورة\s*(?:للشاشة|للبرنامج|للنتائج|للتنفيذ)|'
                r'provide\s+(?:evidence|proof)\s+(?:of|that)|'
                r'show(?:ing)?\s+(?:the\s+)?(?:output|result|running)|'
                r'دليل\s*(?:على\s*)?(?:التنفيذ|التشغيل|العمل|النتائج)',
                re.IGNORECASE
            )
            _REQUIRES_TEXT = re.compile(
                r'descri(?:be|ption)|explain|discuss|compar(?:e|ison)|analyz|evaluat|'
                r'outline|identify|define|justif|review|assess|'
                r'وصف|شرح|تحليل|مقارنة|تقييم|مناقشة|تحديد|تعريف|تبرير|مراجعة',
                re.IGNORECASE
            )
            _REQUIRES_DESIGN = re.compile(
                r'design|plan(?:ning)?|flowchart|diagram|wireframe|mockup|prototype|'
                r'pseudocode|algorithm|'
                r'تصميم|تخطيط|مخطط|خوارزمية|نموذج\s*أولي',
                re.IGNORECASE
            )

            def classify_evidence_type(criterion_full_text: str) -> list:
                """Classify what type of evidence a criterion requires based on its description."""
                types = []
                if _REQUIRES_CODE.search(criterion_full_text):
                    types.append("code")
                if _REQUIRES_TEST.search(criterion_full_text):
                    types.append("test")
                if _REQUIRES_SCREENSHOTS.search(criterion_full_text):
                    types.append("screenshots")
                if _REQUIRES_DESIGN.search(criterion_full_text):
                    types.append("design")
                if _REQUIRES_TEXT.search(criterion_full_text):
                    types.append("text")
                return types if types else ["text"]  # Default to text

            if is_document_only:
                criteria_results = grading_result.get("criteria_results", [])
                capped_criteria = []
                original_grade = grading_result.get("grade_level", "")

                for cr in criteria_results:
                    if not cr.get("achieved", False):
                        continue  # Already not achieved, skip

                    cr_level = cr.get("criteria_level", "")

                    # Look up the criterion description from original grading_criteria
                    desc_info = criteria_desc_map.get(cr_level, None)
                    if not desc_info:
                        # Try without prefix (e.g., "B.P4" → look for "P4" or vice versa)
                        short_level = cr_level.split(".")[-1] if "." in cr_level else cr_level
                        for k, v in criteria_desc_map.items():
                            if k.endswith(short_level):
                                desc_info = v
                                break

                    if desc_info:
                        full_text_caps = desc_info["full_text"]
                        evidence_types = classify_evidence_type(full_text_caps)
                    else:
                        full_text_caps = (
                            (cr.get("feedback", "") or "")
                            + " "
                            + (cr.get("criteria_name", "") or "")
                        ).strip()
                        evidence_types = classify_evidence_type(full_text_caps)

                    requires_source_or_exe = bool(
                        _REQUIRES_SOURCE_OR_EXECUTABLE.search(full_text_caps)
                    )
                    gdd_design_focus = bool(_DESIGN_PEER_GDD_FOCUS.search(full_text_caps))
                    wants_pure_code = "code" in evidence_types or "test" in evidence_types
                    # Do not downgrade GDD/B.P4-type criteria from vague "test/code" cues alone;
                    # only when the brief explicitly asks for source/APK/etc.
                    needs_attached_program_files = requires_source_or_exe or (
                        wants_pure_code and not gdd_design_focus
                    )
                    can_use_screenshots = "screenshots" in evidence_types
                    has_images = image_count > 0

                    print(
                        f"   📋 {cr_level}: evidence={evidence_types}, "
                        f"needs_program_files={needs_attached_program_files}, "
                        f"gddish={gdd_design_focus}"
                    )

                    # Decision logic:
                    # 1. If criterion genuinely needs runnable/source artefacts and submission is doc-only → Not Achieved
                    #    (Screenshots of code in Word are NOT substitute files)
                    # 2. If criterion requires screenshots and images exist → OK (keep achieved)
                    # 3. If criterion is narrative design / revised GDD / peer review → gradable from Word alone
                    if needs_attached_program_files:
                        # Even if screenshots exist, code/test criteria need ACTUAL code files
                        cr["achieved"] = False
                        cr["score"] = min(cr.get("score", 0), 40)
                        original_feedback = cr.get("feedback", "")
                        if requires_source_or_exe:
                            evidence_needed = "كود مصدري/تشغيل حقيقي (.gml/.apk/…)"
                        elif "code" in evidence_types:
                            evidence_needed = "كود/برنامج"
                        else:
                            evidence_needed = "اختبار/تعديل على البرنامج نفسه"
                        cr["feedback"] = (
                            f"⚠️ [تم تعديل التقدير] صياغة المتطلب تفترض دليلًا تقنيًا مرفقًا ({evidence_needed}). "
                            f"التسليم الحالي مستند Word/PDF فقط بدون ملفات مشروع أو برمجة مرفقة. "
                            f"لقطات شاشة داخل الوورد لا تُعدُّ بديلًا عن وجود مشروع أو كود.\n"
                            f"أنواع الأدلة المستنتجة من وصف المعيار: {', '.join(evidence_types)}\n"
                            f"التقييم الأصلي: {original_feedback}"
                        )
                        capped_criteria.append(f"{cr_level} (يتطلب {evidence_needed})")

                    elif can_use_screenshots and not has_images:
                        # Criterion requires screenshots but no images found
                        cr["achieved"] = False
                        cr["score"] = min(cr.get("score", 0), 40)
                        original_feedback = cr.get("feedback", "")
                        cr["feedback"] = (
                            f"⚠️ [تم تعديل التقدير] هذا المعيار يتطلب لقطات شاشة/صور كدليل. "
                            f"لم يتم العثور على صور في المستند.\n"
                            f"نوع الدليل المطلوب: {', '.join(evidence_types)}\n"
                            f"التقييم الأصلي: {original_feedback}"
                        )
                        capped_criteria.append(f"{cr_level} (يتطلب لقطات شاشة)")

                    # else: text/design criteria → keep as-is (achievable from Word)

                if capped_criteria:
                    # Recalculate grade level
                    new_grade = determine_grade_level(criteria_results)
                    grading_result["grade_level"] = new_grade

                    # Recalculate percentage from scores
                    total = sum(cr.get("score", 0) for cr in criteria_results)
                    max_score = grading_result.get("max_score", 400)
                    if max_score > 0:
                        grading_result["percentage"] = round((total / max_score) * 100)
                    grading_result["total_score"] = total

                    # Add note to overall feedback
                    cap_note = (
                        f"\n\n⚠️ ملاحظة النظام: تم تعديل التقدير من "
                        f"'{original_grade}' إلى '{new_grade}' لأن بعض المعايير تتطلب أدلة غير متوفرة في التسليم:\n"
                        f"المعايير المعدّلة: {', '.join(capped_criteria)}\n"
                        f"التسليم يحتوي على: ملف وورد/PDF"
                        f"{' + ' + str(image_count) + ' صورة مضمنة' if image_count > 0 else ''}"
                        f" (بدون ملفات برمجية)"
                    )
                    grading_result["overall_feedback"] = grading_result.get("overall_feedback", "") + cap_note

                    print(f"\n🚫 [GRADE-CAP] {student_info['name']}: Document-only submission")
                    print(f"   Original grade: '{original_grade}' → New grade: '{new_grade}'")
                    print(f"   Capped criteria: {capped_criteria}")
                    print(f"   New percentage: {grading_result['percentage']}%")
                else:
                    print(f"   ✅ {student_info['name']}: All achieved criteria have valid evidence types for doc-only submission")

            if not _mode_flags.get("skip_evidence_layer"):
                try:
                    from app.project_intelligence.assessment_trace import (
                        build_assessment_trace,
                    )
                    from app.project_intelligence.evidence_schema import (
                        attach_criterion_academic_snapshots,
                        build_evidence_layer_from_profile,
                        slim_profile_for_persistence,
                    )

                    _ev_layer = build_evidence_layer_from_profile(project_profile_for_audit)
                    grading_result["evidence_layer"] = _ev_layer
                    grading_result["project_profile_persisted"] = slim_profile_for_persistence(
                        project_profile_for_audit
                    )
                    attach_criterion_academic_snapshots(
                        grading_result,
                        _ev_layer,
                        project_profile=project_profile_for_audit,
                    )
                    grading_result["assessment_trace"] = build_assessment_trace(
                        _ev_layer, project_profile_for_audit
                    )
                except Exception as _ee:
                    print(f"⚠️ [EVIDENCE_LAYER] skipped: {_ee}")

            if not _mode_flags.get("skip_post_grade_artifact_rebuild"):
                artifact_inventory = build_artifact_inventory(
                    main_document_path=str(student_info["path"]),
                    submission_paths=list(submission_paths),
                    embedded_image_count=image_count,
                    vision_analysis_used=bool(
                        vision_completed and vision_extracted_count > 0 and (image_analysis_text or "").strip()
                    ),
                    vision_analysis_text=image_analysis_text or "",
                    vision_extracted_count=vision_extracted_count,
                    project_profile=project_profile_for_audit,
                    batch_id=student_info.get("batch_id"),
                    student_name=str(student_info.get("name") or ""),
                    skip_runtime_observation=_mode_flags.get("skip_runtime_observation", False),
                    skip_heavy_enrichment=fast_mode,
                    skip_l2_l3_corroborative=_mode_flags.get(
                        "skip_l2_l3_corroborative", False
                    ),
                    skip_governance_graphs=_mode_flags.get(
                        "skip_heavy_governance_graphs", False
                    ),
                    skip_gameplay_video_when_runtime_verified=_mode_flags.get(
                        "skip_gameplay_video_when_runtime_verified", False
                    ),
                    grading_mode=grading_mode,
                )
                if isinstance(artifact_inventory.get("gameplay_verification"), dict):
                    grading_result["gameplay_verification"] = artifact_inventory[
                        "gameplay_verification"
                    ]
            try:
                from app.grading_mode_policy import (
                    enrich_artifact_inventory_from_snapshot_meta,
                    slim_artifact_inventory_for_snapshot,
                )

                _inv = slim_artifact_inventory_for_snapshot(artifact_inventory)
                _inv = enrich_artifact_inventory_from_snapshot_meta(_inv, grading_result)
                # Explainability runs after visual authority ledger (below).
                grading_result["artifact_inventory"] = _inv
            except Exception:
                grading_result["artifact_inventory"] = artifact_inventory
            if not _mode_flags.get("skip_evidence_gate"):
                try:
                    from app.evidence_completeness_gate import (
                        attach_evidence_completeness_to_snapshot,
                        evaluate_evidence_completeness,
                    )

                    _gate = evaluate_evidence_completeness(
                        grading_criteria=grading_criteria,
                        submission_paths=list(submission_paths),
                        primary_path=str(student_info.get("path") or ""),
                        student_name=str(student_info.get("name") or ""),
                        strict_block=not _mode_flags.get("skip_evidence_gate"),
                        artifact_inventory=artifact_inventory,
                        intake_relative_paths=student_info.get("intake_relative_paths"),
                    )
                    grading_result["submission_paths"] = list(submission_paths)
                    grading_result["intake_relative_paths"] = list(
                        student_info.get("intake_relative_paths") or []
                    )
                    attach_evidence_completeness_to_snapshot(grading_result, _gate)
                    if _gate.get("has_gaps"):
                        print(
                            f"📋 [EVIDENCE-GATE] {student_info['name']}: "
                            f"{len(_gate.get('missing_summary_ar') or [])} missing artifact note(s)"
                        )
                except Exception as _eg_err:
                    print(f"⚠️ [EVIDENCE-GATE] skipped: {_eg_err}")

            # Deterministic rubric always runs in strict mode (including BASIC)
            try:
                from app.strict_grading_policy import strict_deterministic_enabled

                _run_det_rubric = strict_deterministic_enabled()
            except Exception:
                _run_det_rubric = True
            if not _run_det_rubric and not _mode_flags.get("skip_production_layers"):
                from app.core.production_config import get_production_config

                _run_det_rubric = get_production_config().enable_deterministic_rubric

            if _run_det_rubric:
                try:
                    from app.rubric.deterministic_engine import run_deterministic_rubric

                    _eg = grading_result.get("evidence_completeness_gate") or {}
                    _rv = artifact_inventory.get("runtime_validation") or (
                        (artifact_inventory.get("runtime_observation_report") or {}).get(
                            "runtime_validation"
                        )
                    )
                    _obs_report = artifact_inventory.get("runtime_observation_report") or {}
                    if isinstance(_rv, dict) and _obs_report.get("status") == "skipped":
                        _rv = {
                            **_rv,
                            "observation": {
                                "engine": _obs_report.get("engine"),
                                "status": _obs_report.get("status"),
                            },
                        }
                        if not (_rv.get("functional_smoke") or {}).get("functional_smoke_pass") is True:
                            _rv["functional_smoke"] = {
                                "functional_smoke_pass": None,
                                "reason": f"status_{_obs_report.get('status', 'skipped')}",
                            }
                    grading_result = run_deterministic_rubric(
                        grading_result,
                        grading_criteria=grading_criteria,
                        student_text=grading_result.get("student_text") or student_text,
                        evidence_gate=_eg,
                        runtime_validation=_rv,
                        grading_mode=grading_mode,
                    )
                    try:
                        from app.visual_evidence_registry import apply_game_criteria_pro_gate

                        apply_game_criteria_pro_gate(grading_result, grading_mode=grading_mode)
                    except Exception as _pro_gate_err:
                        print(f"⚠️ [GAME-PRO-GATE] skipped: {_pro_gate_err}")
                    try:
                        from app.visual_evidence_registry import attach_visual_evidence_to_grading_result

                        _obs_inv = artifact_inventory.get("runtime_observation_report") or {}
                        _crit_desc = {
                            str(c.get("criteria_level") or ""): str(
                                c.get("criteria_description") or c.get("criteria_name") or ""
                            )
                            for c in (grading_criteria or [])
                            if isinstance(c, dict)
                        }
                        attach_visual_evidence_to_grading_result(
                            grading_result,
                            images_found=max(
                                vision_extracted_count,
                                image_count if not vision_attempted else vision_extracted_count,
                            ),
                            images_submitted=vision_extracted_count,
                            images_analyzed=vision_success_count,
                            vision_attempted=vision_attempted,
                            vision_completed=vision_completed,
                            vision_error=vision_error,
                            vision_batches=vision_batches,
                            video_keyframes_found=int(_video_kf_meta.get("videos_found") or 0),
                            video_keyframes_analyzed=int(_video_kf_meta.get("frames_extracted") or 0),
                            runtime_verified=bool(_obs_inv.get("runtime_verified")),
                            artifact_inventory=artifact_inventory,
                            criteria_descriptions=_crit_desc,
                        )
                    except Exception as _vis_reg_err:
                        print(f"⚠️ [VISUAL-EVIDENCE-REG] skipped: {_vis_reg_err}")
                    try:
                        from app.visual_evidence_registry import sync_visual_evidence_to_inventory
                        from app.academic_explainability import attach_academic_explainability

                        _inv_sync = grading_result.get("artifact_inventory") or artifact_inventory
                        sync_visual_evidence_to_inventory(
                            _inv_sync,
                            grading_result.get("visual_evidence_summary"),
                        )
                        _inv_sync["criteria_results"] = grading_result.get("criteria_results") or []
                        _inv_sync["criterion_authority"] = (
                            grading_result.get("criterion_authority")
                            or _inv_sync.get("criterion_authority")
                            or []
                        )
                        if grading_result.get("decision_provenance"):
                            _inv_sync["decision_provenance"] = grading_result["decision_provenance"]
                        attach_academic_explainability(_inv_sync, grading_mode=grading_mode)
                        grading_result["artifact_inventory"] = _inv_sync
                    except Exception as _vis_sync_err:
                        print(f"⚠️ [VISUAL-EVIDENCE-SYNC] skipped: {_vis_sync_err}")
                    criteria_results = grading_result.get("criteria_results") or []
                    grading_result["grade_level"] = determine_grade_level(criteria_results)
                except Exception as _det_err:
                    print(f"⚠️ [DETERMINISTIC-RUBRIC] skipped: {_det_err}")

            if not _mode_flags.get("skip_production_layers"):
                try:
                    from app.core.production_config import get_production_config

                    _pcfg = get_production_config()
                    _eg = grading_result.get("evidence_completeness_gate") or {}
                    _rv = artifact_inventory.get("runtime_validation") or (
                        (artifact_inventory.get("runtime_observation_report") or {}).get(
                            "runtime_validation"
                        )
                    )
                    if _pcfg.enable_ai_reliability_layer:
                        from app.ai.reliability_layer import apply_ai_reliability_layer

                        grading_result = apply_ai_reliability_layer(
                            grading_result,
                            evidence_gate=_eg,
                            runtime_validation=_rv,
                        )
                    _skip_runtime_visual = (
                        not fast_mode
                        and _mode_flags.get("skip_visual_verification_when_doc_vision_done")
                        and vision_completed
                        and is_document_only
                        and not has_executable_artifacts
                    )
                    if _skip_runtime_visual:
                        print(
                            f"⏭️ [VISUAL-VERIFY] {student_info['name']}: "
                            "skipped — Word Vision complete; no runtime sandbox"
                        )
                    if _pcfg.enable_visual_verification and not (
                        _mode_flags.get("skip_visual_verification")
                        or fast_mode
                        or _skip_runtime_visual
                    ):
                        from app.vision.verification_layer import attach_visual_verification

                        grading_result = attach_visual_verification(
                            grading_result,
                            observation=artifact_inventory.get("runtime_observation_report"),
                        )
                except Exception as _prod_err:
                    print(f"⚠️ [PRODUCTION-LAYERS] skipped: {_prod_err}")

            if not fast_mode:
                try:
                    from app.runtime_criterion_mapping import evaluate_operational_support

                    _rt_support = evaluate_operational_support(
                        artifact_inventory.get("runtime_observation_report"),
                        artifact_inventory,
                    )
                    artifact_inventory["runtime_criterion_support"] = _rt_support
                    grading_result["runtime_criterion_support"] = _rt_support
                except Exception:
                    pass
            if not fast_mode:
                _inv_path = persist_artifact_inventory_json(
                    artifact_inventory,
                    student_name=student_info["name"],
                    batch_id=student_info.get("batch_id"),
                )
                if _inv_path:
                    grading_result["artifact_inventory_path"] = _inv_path

            # Runtime observation → criterion adjudication (C.P5/C.P6)
            if not fast_mode:
                try:
                    from app.runtime_criterion_mapping import apply_runtime_criterion_adjudication

                    _adj = apply_runtime_criterion_adjudication(
                        grading_result,
                        observation=artifact_inventory.get("runtime_observation_report"),
                        inventory=artifact_inventory,
                    )
                    if _adj.get("applied") and _adj.get("changes"):
                        print(
                            f"🎮 [RUNTIME-ADJ] {student_info['name']}: "
                            f"{len(_adj['changes'])} criterion adjudication(s)"
                        )
                except Exception as _adj_err:
                    print(f"⚠️ [RUNTIME-ADJ] skipped: {_adj_err}")

            # Phase 4: AI Evidence Reasoning (async when Celery + AI_GRADER_ASYNC_REASONING)
            if not _mode_flags.get("skip_ai_evidence_reasoning"):
                try:
                    from app.ai_reasoning.orchestrator import (
                        async_reasoning_enabled,
                        attach_evidence_reasoning_to_grading_result,
                        queue_evidence_reasoning,
                    )

                    _sub_key = str(student_info.get("name") or "")
                    if async_reasoning_enabled():
                        _queued = queue_evidence_reasoning(
                            submission_key=_sub_key,
                            grading_result=grading_result,
                            artifact_inventory=artifact_inventory,
                            grading_criteria=grading_criteria,
                        )
                        grading_result["ai_evidence_reasoning"] = _queued
                        if _queued.get("status") == "queued":
                            print(
                                f"🧠 [EVIDENCE-REASONING] {student_info['name']}: "
                                f"queued task={_queued.get('task_id')}"
                            )
                        elif _queued.get("status") == "celery_disabled":
                            grading_result = attach_evidence_reasoning_to_grading_result(
                                grading_result,
                                artifact_inventory=artifact_inventory,
                                grading_criteria=grading_criteria,
                                submission_key=_sub_key,
                            )
                    else:
                        grading_result = attach_evidence_reasoning_to_grading_result(
                            grading_result,
                            artifact_inventory=artifact_inventory,
                            grading_criteria=grading_criteria,
                            submission_key=_sub_key,
                        )
                    _er = grading_result.get("ai_evidence_reasoning") or {}
                    if _er.get("status") == "completed":
                        print(
                            f"🧠 [EVIDENCE-REASONING] {student_info['name']}: "
                            f"decision={((_er.get('final_decision') or {}).get('decision'))}"
                        )
                except Exception as _reason_err:
                    print(f"⚠️ [EVIDENCE-REASONING] skipped: {_reason_err}")
            else:
                grading_result.setdefault(
                    "ai_evidence_reasoning",
                    {
                        "status": "skipped_fast_mode",
                        "reason_ar": "وضع BASIC — بدون طبقة reasoning إضافية",
                    },
                )

            # Institutional hard gate — block autonomous Achieved escalation (not advisory)
            try:
                from app.criterion_authority_guardrails import apply_criterion_authority_guardrails

                _gr = apply_criterion_authority_guardrails(
                    grading_result,
                    artifact_inventory=artifact_inventory,
                )
                if _gr.get("blocked_count", 0) > 0:
                    print(
                        f"⏸ [AUTH-GUARDRAIL] {student_info['name']}: "
                        f"{_gr['blocked_count']} escalation(s) blocked — HUMAN_REVIEW_REQUIRED"
                    )
            except Exception as _ag_err:
                print(f"⚠️ [AUTH-GUARDRAIL] skipped: {_ag_err}")

            try:
                from app.btec_criteria_governance import apply_btec_criteria_governance

                _btec_gov = apply_btec_criteria_governance(
                    grading_result,
                    artifact_inventory=artifact_inventory,
                )
                if _btec_gov.get("applied"):
                    print(
                        f"📐 [BTEC-GOV] {student_info['name']}: "
                        f"{_btec_gov.get('change_count', 0)} correction(s) — "
                        f"{_btec_gov.get('original_grade_level')} → "
                        f"{_btec_gov.get('institutional_grade_level')}"
                    )
            except Exception as _btec_err:
                print(f"⚠️ [BTEC-GOV] skipped: {_btec_err}")

            if not _mode_flags.get("skip_evidence_gate"):
                try:
                    from app.pro_btec_pearson import apply_pro_pearson_btec_package

                    _pearson = apply_pro_pearson_btec_package(
                        grading_result,
                        grading_criteria=grading_criteria,
                        artifact_inventory=artifact_inventory,
                        grading_mode=grading_mode,
                    )
                    if _pearson.get("change_count", 0) > 0:
                        print(
                            f"📘 [PEARSON-PRO] {student_info['name']}: "
                            f"{_pearson['change_count']} BTEC hardening adjustment(s)"
                        )
                except Exception as _pearson_err:
                    print(f"⚠️ [PEARSON-PRO] skipped: {_pearson_err}")

            if not _mode_flags.get("skip_institutional_resolution"):
                try:
                    from app.institutional_grade_resolution import attach_institutional_grade_resolution

                    attach_institutional_grade_resolution(
                        grading_result,
                        artifact_inventory=artifact_inventory,
                    )
                    _ir = grading_result.get("institutional_resolution") or {}
                    print(
                        f"📊 [INST-RESOLUTION] {student_info['name']}: "
                        f"{_ir.get('outcome_band')} / BTEC {_ir.get('btec_grade')} "
                        f"({(_ir.get('runtime_resolution') or {}).get('summary_ar', '')[:60]}…)"
                    )
                except Exception as _ires_err:
                    print(f"⚠️ [INST-RESOLUTION] skipped: {_ires_err}")

            if not _mode_flags.get("skip_post_grade_layers"):
                try:
                    from app.evidence_lineage import attach_evidence_lineage_to_snapshot

                    attach_evidence_lineage_to_snapshot(grading_result)
                except Exception as _el_err:
                    print(f"⚠️ [EVIDENCE-LINEAGE] skipped: {_el_err}")

                try:
                    from app.academic_event_replay import seed_academic_event_log

                    seed_academic_event_log(grading_result)
                except Exception as _ae_err:
                    print(f"⚠️ [ACADEMIC-EVENTS] skipped: {_ae_err}")

            if not _mode_flags.get("skip_post_grade_layers"):
                overclaim_flags: List[Dict[str, Any]] = []
                for cr in grading_result.get("criteria_results") or []:
                    if not isinstance(cr, dict):
                        continue
                    reasoning = str(cr.get("reasoning") or cr.get("feedback") or "")
                    check = check_claim_authority(reasoning, inventory=artifact_inventory)
                    if not check.get("allowed"):
                        overclaim_flags.append({
                            "kind": "overclaim_drift",
                            "criterion": cr.get("criteria_level") or cr.get("criterion"),
                            "violations": check.get("violations"),
                            "sanitized_preview": (check.get("sanitized_text") or "")[:300],
                        })

                temporal_signals = (
                    (artifact_inventory.get("temporal_consistency") or {}).get(
                        "temporal_consistency_signals"
                    )
                    or []
                )
                claim_flags: Dict[str, Any] = {}
                if overclaim_flags:
                    claim_flags["overclaims"] = overclaim_flags
                if temporal_signals:
                    claim_flags["temporal_consistency"] = [
                        {**sig, "kind": "temporal_consistency_signal"} for sig in temporal_signals
                    ]
                if claim_flags:
                    grading_result["claim_authority_flags"] = claim_flags
                    total = len(overclaim_flags) + len(temporal_signals)
                    print(
                        f"⚠️ [CLAIM-AUTHORITY] {student_info['name']}: "
                        f"{total} governance signal(s)"
                    )

                try:
                    from app.authority_replay import build_authority_replay

                    grading_result["authority_replay"] = build_authority_replay(grading_result)
                except Exception:
                    pass

            if not _mode_flags.get("skip_governance_drift"):
                try:
                    from app.governance_drift_monitor import analyze_submission_governance_drift

                    grading_result["governance_drift"] = analyze_submission_governance_drift(
                        grading_result
                    )
                    if grading_result["governance_drift"].get("drift_signal_count", 0) > 0:
                        print(
                            f"⚠️ [GOV-DRIFT] {student_info['name']}: "
                            f"{grading_result['governance_drift']['drift_signal_count']} signal(s) "
                            f"({grading_result['governance_drift'].get('status')})"
                        )
                    try:
                        from app.governance_mitigation_memory import (
                            check_recurrence_for_submission,
                            record_mitigation_from_drift,
                        )

                        _sub_id = student_info.get("submission_id")
                        if _sub_id:
                            check_recurrence_for_submission(
                                submission_id=int(_sub_id),
                                current_drift=grading_result["governance_drift"],
                            )
                        _mit_records = record_mitigation_from_drift(
                            submission_id=_sub_id,
                            student_name=student_info.get("name", ""),
                            batch_id=student_info.get("batch_id"),
                            governance_drift=grading_result["governance_drift"],
                        )
                        if _mit_records:
                            grading_result["mitigation_records"] = _mit_records
                    except Exception:
                        pass
                except Exception:
                    pass

            grading_result["evidence_trace_graph"] = artifact_inventory.get(
                "evidence_trace_graph"
            )

            if not _mode_flags.get("skip_coverage_notice"):
                _coverage = build_grading_coverage_notice(
                    image_count=image_count,
                    vision_extracted_count=vision_extracted_count,
                    image_analysis_text=image_analysis_text,
                    vision_error=vision_error,
                    is_document_only=is_document_only,
                    has_code_files=has_code_files,
                    submission_paths=list(submission_paths),
                    project_profile=project_profile_for_audit,
                    artifact_inventory=artifact_inventory,
                )
                if _coverage.get("has_gaps"):
                    grading_result["grading_coverage_notice"] = _coverage
                    print(
                        f"📋 [COVERAGE] {student_info['name']}: "
                        f"{len(_coverage.get('items') or [])} transparency note(s)"
                    )

            # Evidence fingerprint + academic digest (audit anchor)
            try:
                if _video_kf_meta:
                    grading_result["basic_video_keyframes_meta"] = _video_kf_meta
                    artifact_inventory["basic_video_keyframes_meta"] = _video_kf_meta
                from app.evidence_fingerprint import attach_evidence_fingerprint
                from app.explainability_migration import compute_academic_decision_digest
                from app.rule_bundle import provenance_from_payload

                attach_evidence_fingerprint(
                    grading_result,
                    artifact_inventory=artifact_inventory,
                )
                try:
                    from app.evidence_drift_audit import attach_evidence_drift_audit

                    _prior = student_info.get("prior_evidence_anchor")
                    _drift = attach_evidence_drift_audit(
                        grading_result, prior_anchor=_prior if isinstance(_prior, dict) else None
                    )
                    if _drift:
                        print(
                            f"🚨 [CRITICAL_EVIDENCE_DRIFT] {student_info['name']}: "
                            f"{_drift.get('drift_class')} "
                            f"prev={str(_drift.get('previous_evidence_hash', ''))[:12]}… "
                            f"now={str(_drift.get('current_evidence_hash', ''))[:12]}…"
                        )
                except Exception as _drift_err:
                    print(f"⚠️ [EVIDENCE-DRIFT] skipped: {_drift_err}")
                grading_result["academic_decision_digest"] = compute_academic_decision_digest(
                    grade_level=grading_result.get("grade_level"),
                    total_score=grading_result.get("total_score"),
                    max_score=grading_result.get("max_score"),
                    percentage=grading_result.get("percentage"),
                    criteria_results=grading_result.get("criteria_results"),
                    decision_provenance=provenance_from_payload(grading_result),
                    evidence_fingerprint=grading_result.get("evidence_fingerprint"),
                )
                _fp = grading_result.get("evidence_fingerprint") or {}
                _prov = grading_result.get("decision_provenance") or {}
                print(
                    f"🔐 [AUDIT-ANCHOR] {student_info['name']}: "
                    f"bundle={str(_prov.get('bundle_hash', ''))[:12]}… "
                    f"evidence={str(_fp.get('evidence_hash', ''))[:12]}…"
                )
            except Exception as _ef_err:
                print(f"⚠️ [EVIDENCE-FP] skipped: {_ef_err}")

            try:
                from app.criteria_result_finalizer import finalize_grading_criteria_results

                _fin = finalize_grading_criteria_results(
                    grading_result,
                    artifact_inventory=artifact_inventory,
                )
                try:
                    from app.btec_criteria_governance import ensure_clean_grading_result_feedback

                    _san = ensure_clean_grading_result_feedback(grading_result)
                    if _san:
                        _fin.setdefault("changes", []).extend(_san)
                        _fin["change_count"] = len(_fin.get("changes") or [])
                except Exception:
                    pass
                if _fin.get("change_count", 0) > 0:
                    print(
                        f"✅ [CRITERIA-FINALIZER] {student_info['name']}: "
                        f"{_fin['change_count']} adjustment(s) — "
                        f"grade={grading_result.get('grade_level')}"
                    )
            except Exception as _fin_err:
                print(f"⚠️ [CRITERIA-FINALIZER] skipped: {_fin_err}")

            if not _mode_flags.get("skip_production_layers"):
                try:
                    from app.requirement_checklist import build_requirement_checklist
                    from app.runtime_evidence_package import attach_runtime_evidence_package

                    _req_checklist = build_requirement_checklist(
                        student_text=student_text or "",
                        reference_solution=reference_solution,
                    )
                    _rt_pkg = attach_runtime_evidence_package(
                        grading_result,
                        artifact_inventory=artifact_inventory,
                        requirement_checklist=_req_checklist,
                        submission_paths=list(submission_paths),
                    )
                    _pkg = _rt_pkg.get("package") or {}
                    print(
                        f"🎮 [RUNTIME-EVIDENCE] {student_info['name']}: "
                        f"status={_pkg.get('runtime_status')} "
                        f"strength={_pkg.get('runtime_evidence_strength')} "
                        f"events={len(_pkg.get('events') or [])}"
                    )
                except Exception as _rt_err:
                    print(f"⚠️ [RUNTIME-EVIDENCE] skipped: {_rt_err}")

            if not _mode_flags.get("skip_production_layers"):
                try:
                    from app.evidence_coverage_score import attach_evidence_coverage_package

                    _cov_pkg = attach_evidence_coverage_package(
                        grading_result,
                        artifact_inventory=artifact_inventory,
                        student_text=student_text or "",
                        word_only_text=word_only_text or "",
                        submission_paths=list(submission_paths),
                    )
                    if _cov_pkg.get("changes"):
                        print(
                            f"📊 [EVIDENCE-COVERAGE] {student_info['name']}: "
                            f"CP6={(_cov_pkg.get('report') or {}).get('cp6_coverage_pct')}% — "
                            f"{len(_cov_pkg['changes'])} award block(s)"
                        )
                except Exception as _cov_err:
                    print(f"⚠️ [EVIDENCE-COVERAGE] skipped: {_cov_err}")

            # Final check: Log what we're about to return
            print(f"📊 [FINAL RESULT] {student_info['name']}:")
            print(f"   total_score: {grading_result['total_score']}")
            print(f"   max_score: {grading_result['max_score']}")
            print(f"   percentage: {grading_result['percentage']}%")
            print(f"   grade_level: {grading_result['grade_level']}")
            print(f"   ai_likelihood: {grading_result['ai_likelihood']}%")
            print(f"   criteria_results: {len(grading_result.get('criteria_results', []))} items\n")

            # Add student info
            grading_result["student_name"] = student_info["name"]
            grading_result["student_email"] = student_info.get("email", "")
            grading_result["student_id"] = student_info.get("student_id", "")
            grading_result["file_path"] = student_info["path"]
            grading_result["grading_hash"] = hash_submission_file(
                student_info["path"], ""
            )

            _plag_vision_parts: List[str] = []
            if image_analysis_text and image_analysis_text.strip():
                _plag_vision_parts.append(image_analysis_text.strip())
            gvi = artifact_inventory.get("gameplay_video_inference") or {}
            for hint in (gvi.get("video_analysis") or {}).get("runtime_hints") or []:
                if isinstance(hint, dict):
                    for key in ("hint", "description", "label", "message"):
                        val = hint.get(key)
                        if val and str(val).strip():
                            _plag_vision_parts.append(str(val).strip())
                            break
            plagiarism_text = build_plagiarism_corpus(
                (word_only_text or student_text).strip(),
                list(submission_paths),
                per_file_cap=15_000,
                vision_analysis_text="\n".join(_plag_vision_parts),
            )
            grading_result["plagiarism_text"] = plagiarism_text
            grading_result["student_text"] = plagiarism_text
            grading_result["success"] = True
            return grading_result

    from difflib import SequenceMatcher

    graded_texts: List = []
    DUPLICATE_THRESHOLD = 0.85

    async def _grade_one(idx: int, student: Dict) -> Dict:
        if cancel_check and cancel_check():
            print(f"⏹️ [BATCH] Skip {student['name']} — cancel requested")
            return {
                "student_name": student["name"],
                "student_email": student.get("email", ""),
                "student_id": student.get("student_id", ""),
                "file_path": student["path"],
                "success": False,
                "cancelled": True,
                "error": "cancelled_by_user",
                "total_score": 0,
                "max_score": 0,
                "percentage": 0,
            }
        _phase(student["name"], "extracting", 0.08)
        if start_callback:
            start_callback(student["name"])

        student_text_preview = ""
        if not fast_mode and len(student_files) > 1:
            try:
                _loop = asyncio.get_running_loop()
                student_text_preview = await asyncio.wait_for(
                    _loop.run_in_executor(
                        None,
                        extract_text_from_file,
                        student["path"],
                    ),
                    timeout=120.0,
                )
            except Exception:
                student_text_preview = ""

        duplicate_of = None
        if student_text_preview and len(student_text_preview.strip()) >= 50:
            for prev_name, prev_text, prev_result in graded_texts:
                len_ratio = min(len(student_text_preview), len(prev_text)) / max(
                    len(student_text_preview), len(prev_text), 1
                )
                if len_ratio < 0.7:
                    continue
                similarity = SequenceMatcher(
                    None, student_text_preview[:5000], prev_text[:5000]
                ).ratio()
                if similarity >= DUPLICATE_THRESHOLD:
                    duplicate_of = (prev_name, prev_result, similarity)
                    break

        if duplicate_of:
            prev_name, prev_result, similarity = duplicate_of
            print(
                f"\n⚠️ [DUPLICATE] {student['name']} متشابه بنسبة {similarity * 100:.1f}% مع {prev_name}"
            )
            import copy

            result = copy.deepcopy(prev_result)
            result["student_name"] = student["name"]
            result["student_email"] = student.get("email", "")
            result["student_id"] = student.get("student_id", "")
            result["file_path"] = student["path"]
            result["student_text"] = student_text_preview
            result["duplicate_of"] = prev_name
            result["duplicate_similarity"] = round(similarity * 100, 1)
        else:
            if student_text_preview and len(student_text_preview.strip()) >= 50:
                student["_text_preview"] = student_text_preview
            result = await grade_single_student(student)
            result_text = result.get("student_text", student_text_preview)
            if result.get("success") and result_text:
                graded_texts.append((student["name"], result_text, result))

        if progress_callback:
            progress_callback(student["name"], result.get("success", False))
            if result.get("success"):
                print(
                    f"✅ [{idx + 1}/{len(student_files)}] تم تصحيح: "
                    f"{result.get('student_name', '?')}"
                )
        return result

    use_parallel = bool(
        _mode_flags.get("parallel_batch_grading") and len(student_files) > 1
    )
    if use_parallel:
        try:
            from app.grading_mode_policy import batch_parallel_workers

            _parallel = batch_parallel_workers(grading_mode)
        except Exception:
            _parallel = 8 if fast_mode else 6
        _parallel = max(1, min(max_workers or _parallel, _parallel))
        _mode_label = "BASIC" if fast_mode else "PRO"
        print(
            f"⚡ [{_mode_label}] Parallel grading: "
            f"{len(student_files)} students, workers={_parallel}"
        )
        sem = asyncio.Semaphore(_parallel)

        async def _run_guarded(idx: int, student: Dict) -> tuple[int, Dict]:
            async with sem:
                res = await _grade_one(idx, student)
                return idx, res

        tasks = [
            asyncio.create_task(_run_guarded(i, s))
            for i, s in enumerate(student_files)
        ]
        ordered: List[Optional[Dict]] = [None] * len(student_files)
        for coro in asyncio.as_completed(tasks):
            if cancel_check and cancel_check():
                for t in tasks:
                    if not t.done():
                        t.cancel()
            idx, res = await coro
            ordered[idx] = res
        results = [r for r in ordered if r is not None]
    else:
        for idx, student in enumerate(student_files):
            if cancel_check and cancel_check():
                print(f"⏹️ [BATCH] Stopping batch — cancel after {idx} students")
                break
            results.append(await _grade_one(idx, student))

    return results
