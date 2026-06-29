"""
Hybrid Grader — Deterministic BTEC Assessment
Combines Rule-Based pre-evaluation with AI grading:
  1. Rules run FIRST (deterministic, fast)
  2. Rule evidence is injected INTO the AI prompt (anchoring)
  3. If Rules give CLEAR verdict, AI cannot override it
  4. If BORDERLINE, AI decides but with rule context
"""
from typing import Dict, List, Any, Optional
from .rule_marker import RuleBasedMarker


class HybridGrader:
    """
    Orchestrates deterministic + AI grading for BTEC criteria.
    """

    @staticmethod
    def pre_evaluate_all(
        student_text: str,
        grading_criteria: List[Dict[str, Any]],
        selected_criteria: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Run rule-based evaluation on ALL criteria before AI call.
        Returns a dict keyed by criteria_level with rule results.
        """
        if selected_criteria is None:
            selected_criteria = ["P1", "P2", "M1", "D1"]

        def matches_selected(level: str) -> bool:
            short = level.split(".")[-1] if "." in level else level
            return level in selected_criteria or short in selected_criteria

        results = {}
        for criterion in grading_criteria:
            level = criterion["criteria_level"]
            if not matches_selected(level):
                continue

            rule_result = RuleBasedMarker.evaluate_criterion(
                text=student_text,
                criteria_level=level,
                criteria_description=criterion.get("criteria_description", ""),
                reference_keywords=criterion.get("key_points", []) if isinstance(criterion.get("key_points"), list) else [],
            )
            results[level] = rule_result

            short = level.split(".")[-1] if "." in level else level
            verdict = rule_result["verdict"]
            conf = rule_result["confidence"]
            print(f"   📐 [RULE] {short}: {verdict} (confidence={conf:.2f}, verbs={rule_result['evidence']['verb_count']}, domain={rule_result['evidence']['domain_count']})")

        return results

    @staticmethod
    def build_rule_context(rule_results: Dict[str, Dict[str, Any]]) -> str:
        """
        Build a text summary of rule findings to inject into AI prompt.
        This ANCHORS the AI evaluation with deterministic evidence.
        """
        lines = []
        lines.append("═══════════════════════════════════════════════════════════")
        lines.append("نتائج الفحص الأولي (تحليل حتمي للنص - يجب مراعاتها):")
        lines.append("═══════════════════════════════════════════════════════════")

        for level, result in rule_results.items():
            short = level.split(".")[-1] if "." in level else level
            ev = result["evidence"]
            verdict_ar = {
                "CLEAR_PASS": "✅ أدلة قوية على التحقيق",
                "CLEAR_FAIL": "❌ لا توجد أدلة كافية",
                "BORDERLINE": "⚠️ حالة حدّية - يحتاج تحليل عميق",
            }.get(result["verdict"], "⚠️ غير محدد")

            lines.append(f"\n{short} — {verdict_ar} (ثقة: {result['confidence']:.0%})")
            if ev["verb_indicators"]:
                lines.append(f"  مؤشرات فعل الأمر: {', '.join(ev['verb_indicators'][:6])}")
            if ev["domain_keywords"]:
                lines.append(f"  مصطلحات المجال: {', '.join(ev['domain_keywords'][:6])}")
            lines.append(f"  الهيكل: {ev['word_count']} كلمة، {ev['paragraph_count']} فقرة")

            if ev.get("comparison_count", 0) > 0 or ev.get("cause_effect_count", 0) > 0:
                lines.append(f"  تحليل: {ev.get('comparison_count', 0)} مقارنة، {ev.get('cause_effect_count', 0)} سبب-نتيجة")
            if ev.get("judgement_count", 0) > 0:
                lines.append(f"  تقييم: {ev.get('judgement_count', 0)} حكم/توصية")

        lines.append("")
        lines.append("تعليمات: إذا كان الفحص الأولي يشير إلى 'أدلة قوية على التحقيق'، يجب أن تجد دليلاً واضحاً في النص لتأكيد ذلك.")
        lines.append("إذا كان يشير إلى 'لا توجد أدلة كافية'، تحقق بعناية — قد يكون النص لا يحتوي فعلاً على ما هو مطلوب.")
        lines.append("في الحالات الحدّية، اعتمد على حكمك المهني بناءً على أدلة النص الفعلية.")

        return "\n".join(lines)

    @staticmethod
    def merge_results(
        ai_criteria_eval: Dict[str, Any],
        rule_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Merge AI evaluation with rule results.
        CLEAR verdicts from rules override AI borderline decisions.
        """
        merged = {}

        for level, ai_eval in ai_criteria_eval.items():
            # Find matching rule result
            rule_result = rule_results.get(level)
            if not rule_result:
                # Try short level match
                for rl_key, rl_val in rule_results.items():
                    short_rl = rl_key.split(".")[-1] if "." in rl_key else rl_key
                    short_lv = level.split(".")[-1] if "." in level else level
                    if short_rl == short_lv:
                        rule_result = rl_val
                        break

            if not rule_result:
                merged[level] = ai_eval
                continue

            verdict = rule_result["verdict"]
            ai_achieved = ai_eval.get("achieved", False)
            merged_eval = dict(ai_eval)

            # ─── Strict override: rules bind when verdict is not ambiguous ───
            try:
                from app.strict_grading_policy import strict_deterministic_enabled

                strict = strict_deterministic_enabled()
            except Exception:
                strict = True

            if strict:
                if verdict == "CLEAR_FAIL" and ai_achieved:
                    merged_eval["achieved"] = False
                    merged_eval["ai_proposed_achieved"] = True
                    merged_eval["achievement_authority"] = "RULE_STRICT"
                    print(
                        f"   🔒 [HYBRID-STRICT] {level}: Rules FAIL → Not Achieved "
                        f"(overrode AI, confidence={rule_result['confidence']:.2f})"
                    )
                elif verdict == "BORDERLINE" and ai_achieved:
                    merged_eval["achievement_authority"] = merged_eval.get(
                        "achievement_authority", "AI"
                    )
                    print(
                        f"   ℹ️ [HYBRID-STRICT] {level}: BORDERLINE → trusting AI "
                        f"(achieved={ai_achieved})"
                    )
                elif verdict == "CLEAR_PASS" and not ai_achieved:
                    print(
                        f"   ℹ️ [HYBRID-STRICT] {level}: Rules PASS hint but AI NOT Achieved → keeping AI"
                    )
            else:
                if verdict == "CLEAR_PASS" and not ai_achieved:
                    print(
                        f"   ℹ️ [HYBRID] {level}: Rules suggest PASS but AI says NOT Achieved → Trusting AI"
                    )
                elif verdict == "CLEAR_FAIL" and ai_achieved:
                    print(
                        f"   ℹ️ [HYBRID] {level}: Rules suggest FAIL but AI says Achieved → Trusting AI "
                        f"(confidence={rule_result['confidence']:.2f})"
                    )

            merged[level] = merged_eval

        return merged
