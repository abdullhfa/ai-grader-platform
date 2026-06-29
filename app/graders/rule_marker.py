"""
Rule-Based Marker for BTEC Assessment
Deterministic evaluation based on:
  1. Command Verb indicators (describe/explain/analyse/evaluate)
  2. Keyword presence from reference solution
  3. Structural analysis (sections, paragraphs, depth)
"""
import re
from typing import Any, Dict, List, Optional


# ─── BTEC Command Verb Indicators ───────────────────────────────────────
# Each level has specific linguistic markers that indicate the student
# performed the required cognitive task.

BTEC_INDICATORS: Dict[str, Dict[str, Any]] = {
    "P": {
        # Pass = Describe / Explain — listing concepts, naming things, basic coverage
        "ar_verbs": [
            "يوصف", "وصف", "يصف", "يشرح", "شرح", "يوضح", "وضح",
            "يعرف", "عرف", "تعريف", "مفهوم", "ماهو", "ما هو", "ما هي",
            "يعني", "هو عبارة عن", "يتكون من", "أنواع", "تطبيقات",
            "استخدام", "استخدامات", "يستخدم", "أمثلة", "مثال", "مثل",
        ],
        "en_verbs": [
            "describe", "explain", "outline", "identify", "define",
            "list", "state", "name", "example", "such as", "type",
            "application", "concept", "used for", "used in",
        ],
        "structural": {
            "min_words": 150,
            "min_paragraphs": 2,
            "min_concepts": 2,  # Must mention at least 2 distinct concepts
        },
    },
    "M": {
        # Merit = Analyse — cause-effect, comparison, how/why, impact analysis
        "ar_verbs": [
            "تحليل", "حلل", "يحلل", "تأثير", "يؤثر", "أثر", "بسبب",
            "نتيجة", "يؤدي", "أدى", "مقارنة", "قارن", "يقارن",
            "الفرق بين", "من ناحية أخرى", "بينما", "على عكس",
            "العلاقة بين", "يرتبط", "كيف يؤثر", "لماذا",
            "سبب", "أسباب", "عامل", "عوامل",
            "ايجابيات وسلبيات", "مزايا وعيوب", "فوائد ومخاطر",
        ],
        "en_verbs": [
            "analy", "impact", "effect", "cause", "result",
            "compare", "contrast", "difference", "whereas", "while",
            "relationship", "how does", "why does", "factor",
            "advantage", "disadvantage", "benefit", "risk", "drawback",
            "pros and cons", "on the other hand",
        ],
        "structural": {
            "min_words": 300,
            "min_paragraphs": 3,
            "min_comparisons": 1,  # At least one comparison/contrast
        },
    },
    "D": {
        # Distinction = Evaluate — judgement, justification, recommendation
        "ar_verbs": [
            "تقييم", "قيم", "يقيم", "حكم", "نستنتج", "استنتاج",
            "أوصي", "توصية", "توصيات", "اقتراح", "أقترح",
            "في رأيي", "من وجهة نظري", "أعتقد", "يمكن القول",
            "الأفضل", "أفضل من", "الأكثر فعالية",
            "بالمجمل", "بشكل عام", "خلاصة",
            "تبرير", "مبرر", "لأن", "الدليل على ذلك",
            "نقاط القوة", "نقاط الضعف", "محددات", "قيود",
        ],
        "en_verbs": [
            "evaluat", "assess", "judg", "justif", "recommend",
            "suggest", "in my opinion", "i believe", "overall",
            "conclude", "conclusion", "therefore", "thus",
            "most effective", "best approach", "preferable",
            "strength", "weakness", "limitation", "constraint",
            "evidence suggest", "based on", "critical",
        ],
        "structural": {
            "min_words": 400,
            "min_paragraphs": 4,
            "min_judgements": 1,  # At least one evaluative statement
        },
    },
}

# ─── Unit-specific domain keywords (audit: extend beyond Unit 21 AI) ───
IT_UNIT1_DOMAIN_KEYWORDS = {
    "ar": [
        "تقنية المعلومات", "حاسوب", "شبكة", "برمجيات", "أجهزة", "نظام تشغيل",
        "قاعدة بيانات", "أمن معلومات", "مستخدم", "خادم", "تخزين", "سحابة",
        "تطبيق", "موقع", "متصفح", "بيانات", "معلومات", "رقمي",
    ],
    "en": [
        "information technology", "computer", "software", "hardware", "operating system",
        "database", "cybersecurity", "user", "server", "storage", "cloud",
        "application", "website", "browser", "digital", "data",
    ],
}

PROGRAMMING_UNIT4_DOMAIN_KEYWORDS = {
    "ar": [
        "برمجة", "خوارزمية", "متغير", "دالة", "حلقة", "شرط", "كود", "مصدر",
        "python", "java", "c#", "debug", "تصحيح", "اختبار", "برنامج", "تطبيق",
        "كائن", "class", "loop", "function", "array", "قائمة",
    ],
    "en": [
        "programming", "algorithm", "variable", "function", "loop", "condition",
        "source code", "debug", "unit test", "application", "class", "object",
        "array", "string", "integer", "compile", "runtime", "api",
    ],
}

NETWORKING_UNIT5_DOMAIN_KEYWORDS = {
    "ar": [
        "شبكة", "بروتوكول", "tcp", "ip", "dns", "dhcp", "router", "switch",
        "firewall", "subnet", "vlan", "wifi", "ethernet", "packet", "عنوان",
        "topolog", "أمن شبكات", "vpn", "lan", "wan",
    ],
    "en": [
        "network", "protocol", "tcp", "ip", "dns", "dhcp", "router", "switch",
        "firewall", "subnet", "vlan", "wifi", "ethernet", "packet", "topology",
        "vpn", "lan", "wan", "osi", "bandwidth",
    ],
}

GAME_UNIT8_DOMAIN_KEYWORDS = {
    "ar": [
        "لعبة", "game", "unity", "godot", "gamemaker", "scratch", "محرك",
        "player", "enemy", "level", "score", "collision", "sprite", "asset",
        "gameplay", "تصميم لعبة", "فيزياء", "animation", "ui", "hud",
        "build", "export", "playtest", "gdd", "مستوى", "شخصية",
    ],
    "en": [
        "game", "unity", "godot", "gamemaker", "scratch", "engine", "player",
        "enemy", "level", "score", "collision", "sprite", "asset", "gameplay",
        "game design", "physics", "animation", "hud", "build", "export",
        "playtest", "gdd", "prefab", "scene", "script",
    ],
}

AI_DOMAIN_KEYWORDS = {
    "ar": [
        "ذكاء اصطناعي", "تعلم آلي", "تعلم الالي", "التعلم العميق",
        "شبكة عصبية", "شبكات عصبية", "معالجة اللغة", "رؤية حاسوبية",
        "أنظمة خبيرة", "نظام خبير", "روبوت", "خوارزمية", "بيانات",
        "نموذج", "تدريب", "تصنيف", "التنبؤ", "أتمتة",
        "قطاع الصحة", "قطاع التعليم", "قطاع النقل", "قطاع المالية",
        "أخلاقيات", "خصوصية", "تحيز", "وظائف",
    ],
    "en": [
        "artificial intelligence", "machine learning", "deep learning",
        "neural network", "natural language", "nlp", "computer vision",
        "expert system", "robot", "algorithm", "data", "model",
        "training", "classification", "prediction", "automation",
        "healthcare", "education", "transport", "finance",
        "ethics", "privacy", "bias", "employment",
    ],
}

UNIT_DOMAIN_KEYWORDS = {
    "1": IT_UNIT1_DOMAIN_KEYWORDS,
    "4": PROGRAMMING_UNIT4_DOMAIN_KEYWORDS,
    "5": NETWORKING_UNIT5_DOMAIN_KEYWORDS,
    "8": GAME_UNIT8_DOMAIN_KEYWORDS,
    "21": AI_DOMAIN_KEYWORDS,
}


def _domain_keywords_for(criteria_level: str) -> Dict[str, list]:
    m = re.match(r"(\d+)[/.]", criteria_level or "")
    if m:
        pack = UNIT_DOMAIN_KEYWORDS.get(m.group(1))
        if pack:
            return pack
    return IT_UNIT1_DOMAIN_KEYWORDS


class RuleBasedMarker:
    """
    Deterministic BTEC criterion evaluator.
    Produces a confidence score and evidence for each criteria level.
    """

    @staticmethod
    def evaluate_criterion(
        text: str,
        criteria_level: str,
        criteria_description: str = "",
        reference_keywords: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a single BTEC criterion using deterministic rules.

        Returns:
            {
                "rule_achieved": bool,
                "confidence": float (0.0-1.0),
                "evidence": { ... detailed metrics ... },
                "verdict": str ("CLEAR_PASS" | "CLEAR_FAIL" | "BORDERLINE"),
                "feedback": str,
            }
        """
        if reference_keywords is None:
            reference_keywords = []

        text_clean = text.strip()
        text_lower = text_clean.lower()

        # Determine criterion type (P, M, D) from level
        short_level = criteria_level.split(".")[-1] if "." in criteria_level else criteria_level
        ctype = short_level[0].upper()  # "P", "M", or "D"
        indicators = BTEC_INDICATORS.get(ctype, BTEC_INDICATORS["P"])

        # ─── 1. Word & Structure Metrics ───
        words = text_clean.split()
        word_count = len(words)
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text_clean) if p.strip() and len(p.strip()) > 20]
        para_count = len(paragraphs)
        sentences = re.split(r'[.!?。؟!]\s+', text_clean)
        sentence_count = len([s for s in sentences if len(s.split()) > 3])

        struct_reqs = indicators["structural"]

        # ─── 2. Command Verb Indicator Count ───
        ar_hits = []
        for v in indicators["ar_verbs"]:
            if v in text_lower:
                ar_hits.append(v)
        en_hits = []
        for v in indicators["en_verbs"]:
            if v in text_lower:
                en_hits.append(v)
        verb_hits = list(set(ar_hits + en_hits))
        verb_count = len(verb_hits)

        # ─── 3. Domain Keyword Coverage ───
        domain_pack = _domain_keywords_for(criteria_level)
        domain_hits_ar = [k for k in domain_pack["ar"] if k in text_lower]
        domain_hits_en = [k for k in domain_pack["en"] if k in text_lower]
        domain_hits = list(set(domain_hits_ar + domain_hits_en))
        domain_count = len(domain_hits)

        # ─── 4. Reference Solution Keyword Match ───
        ref_hits = []
        for kw in reference_keywords:
            kw_lower = kw.lower().strip()
            if kw_lower and kw_lower in text_lower:
                ref_hits.append(kw)
        ref_match_ratio = len(ref_hits) / max(len(reference_keywords), 1)

        # ─── 5. Higher-Level Indicators (for M and D) ───
        # Comparison patterns for M
        comparison_patterns = [
            r'بينما|على عكس|الفرق بين|من ناحية أخرى|مقارنة|compared|whereas|while|on the other hand|difference',
            r'أكثر من|أقل من|أفضل من|more than|less than|better than',
        ]
        comparison_count = sum(
            len(re.findall(p, text_lower)) for p in comparison_patterns
        )

        # Cause-effect for M
        cause_effect_patterns = [
            r'بسبب|نتيجة|يؤدي|أدى|لأن|مما|because|therefore|leads to|results in|due to|consequently',
        ]
        cause_effect_count = sum(
            len(re.findall(p, text_lower)) for p in cause_effect_patterns
        )

        # Judgement/evaluation for D
        judgement_patterns = [
            r'في رأيي|أعتقد|نستنتج|يمكن القول|بالمجمل|الأفضل|أوصي|توصية|in my opinion|i believe|overall|recommend|conclude|therefore',
        ]
        judgement_count = sum(
            len(re.findall(p, text_lower)) for p in judgement_patterns
        )

        # ─── 6. Calculate Confidence Score ───
        scores = []

        # Word count score (0-1)
        min_w = struct_reqs["min_words"]
        word_score = min(1.0, word_count / max(min_w, 1))
        scores.append(("word_count", word_score, 0.15))

        # Paragraph score (0-1)
        min_p = struct_reqs["min_paragraphs"]
        para_score = min(1.0, para_count / max(min_p, 1))
        scores.append(("paragraphs", para_score, 0.10))

        # Command verb indicator score (0-1)
        # Higher levels need MORE specific indicators to count
        verb_threshold = 4 if ctype == "P" else 12 if ctype == "M" else 12
        verb_score = min(1.0, verb_count / verb_threshold)
        scores.append(("verb_indicators", verb_score, 0.20))

        # Domain coverage score (0-1)
        domain_threshold = 5 if ctype == "P" else 10 if ctype == "M" else 12
        domain_score = min(1.0, domain_count / domain_threshold)
        scores.append(("domain_coverage", domain_score, 0.15))

        # Level-specific scores — higher levels need MUCH stronger evidence
        if ctype == "M":
            # M requires BOTH comparisons AND cause-effect in sufficient quantity
            analysis_score = min(1.0, (comparison_count + cause_effect_count) / 15)
            scores.append(("analysis_depth", analysis_score, 0.40))
        elif ctype == "D":
            # D requires multiple distinct judgements/recommendations
            eval_score = min(1.0, judgement_count / 12)
            scores.append(("evaluation_depth", eval_score, 0.40))
        else:
            # For P, reference keyword match matters more
            scores.append(("ref_coverage", ref_match_ratio, 0.40))

        # Weighted confidence
        confidence = sum(s * w for _, s, w in scores)

        # ─── 7. Determine Verdict ───
        # P: keyword presence is a reliable indicator → CLEAR_PASS allowed
        # M/D: require comprehension/quality assessment → NEVER CLEAR_PASS
        #       (rules still detect CLEAR_FAIL for obviously bad submissions,
        #        and provide evidence context to anchor the AI for BORDERLINE)
        fail_threshold = 0.25 if ctype == "P" else 0.30 if ctype == "M" else 0.35

        if ctype == "P" and confidence >= 0.60:
            verdict = "CLEAR_PASS"
            rule_achieved = True
        elif confidence <= fail_threshold:
            verdict = "CLEAR_FAIL"
            rule_achieved = False
        else:
            verdict = "BORDERLINE"
            rule_achieved = confidence >= 0.50

        # ─── 8. Build Feedback ───
        feedback_parts = []
        if verb_count > 0:
            feedback_parts.append(f"عثر على {verb_count} مؤشر لفعل الأمر المطلوب ({ctype})")
        else:
            feedback_parts.append(f"لم يُعثر على مؤشرات لفعل الأمر المطلوب ({ctype})")
        if domain_count > 0:
            feedback_parts.append(f"تغطية {domain_count} مصطلح من المجال")
        feedback_parts.append(f"عدد الكلمات: {word_count}")
        feedback = " | ".join(feedback_parts)

        return {
            "rule_achieved": rule_achieved,
            "confidence": round(confidence, 3),
            "verdict": verdict,
            "evidence": {
                "word_count": word_count,
                "paragraph_count": para_count,
                "sentence_count": sentence_count,
                "verb_indicators": verb_hits[:10],
                "verb_count": verb_count,
                "domain_keywords": domain_hits[:10],
                "domain_count": domain_count,
                "ref_match_ratio": round(ref_match_ratio, 2),
                "comparison_count": comparison_count,
                "cause_effect_count": cause_effect_count,
                "judgement_count": judgement_count,
                "score_breakdown": {name: round(s, 2) for name, s, _ in scores},
            },
            "feedback": feedback,
        }
