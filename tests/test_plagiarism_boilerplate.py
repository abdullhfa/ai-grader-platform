"""Tests for BTEC boilerplate filtering in plagiarism scoring."""
from __future__ import annotations

from app.batch_grader import calculate_text_similarity
from app.plagiarism_boilerplate import is_boilerplate_phrase, strip_plagiarism_boilerplate


def _shared_btec_shell(game_name: str, unique_body: str) -> str:
    return (
        "وثائق التصميم والاختبار ومراجعة التعليقات لتحسين اللعبة\n"
        "8/C.P3: إعداد التصميمات الفنية والبصرية\n"
        "مقدمة\n"
        "يطلب منك إعداد التصميمات الفنية والبصرية الخاصة بلعبتك "
        f"{game_name} والموجهة للأطفال من عمر 8 إلى 12 سنة.\n"
        f"{unique_body}\n"
        "متطلبات العميل\n"
        "الجمهور المستهدف\n"
    )


def test_strip_removes_criterion_headings_and_brief():
    raw = _shared_btec_shell("لعبة أ", "محتوى الطالب الخاص هنا")
    stripped = strip_plagiarism_boilerplate(raw)
    assert "8/C.P3" not in stripped
    assert "وثائق التصميم والاختبار" not in stripped
    assert "لعبة أ" in stripped
    assert "محتوى الطالب الخاص هنا" in stripped


def test_boilerplate_inflation_reduced_between_classmates():
    unique_a = (
        "القط يجمع الجبن في شوارع المدينة ويتفادى الصناديق الكرتونية "
        "ويتسلق الأسلاك الكهربائية في الليل."
    )
    unique_b = (
        "السلايم يهرب عبر ثلاث مراحل ويجمع المفاتيح الذهبية "
        "ويتجنب الأشواك الحمراء في كل مستوى."
    )
    a = _shared_btec_shell("Cat Runner", unique_a)
    b = _shared_btec_shell("Slime Escape", unique_b)
    different_sim = calculate_text_similarity(a, b)["total"]

    copied = (
        "القط يجمع الجبن في شوارع المدينة ويتفادى الصناديق الكرتونية "
        "ويتسلق الأسلاك الكهربائية في الليل."
    )
    copy_a = _shared_btec_shell("Cat Runner", copied)
    copy_b = _shared_btec_shell("Other Game", copied)
    copied_sim = calculate_text_similarity(copy_a, copy_b)["total"]

    assert different_sim < copied_sim - 15
    assert different_sim < 40


def test_copied_unique_prose_still_high_similarity():
    unique = (
        "الشخصية الرئيسية تدعى زيد وتتحكم بمفتاح space للقفز "
        "وتجمع عملات ذهبية في مستوى الغابة المظلمة."
    )
    a = _shared_btec_shell("Game A", unique)
    b = _shared_btec_shell("Game B", unique)
    sim = calculate_text_similarity(a, b)
    assert sim["total"] >= 25
    assert sim["details"].get("boilerplate_filtered") is True


def test_is_boilerplate_phrase_detects_assignment_lines():
    assert is_boilerplate_phrase("إعداد التصميمات الفنية والبصرية")
    assert is_boilerplate_phrase("=== Slide 3 ===")
    assert not is_boilerplate_phrase("القط يجمع الجبن في شوارع المدينة")
