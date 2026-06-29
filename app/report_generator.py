"""
Individual student report generation with Arabic support
"""
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4  # type: ignore
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # type: ignore
from reportlab.lib.units import inch  # type: ignore
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle  # type: ignore
from reportlab.lib import colors  # type: ignore
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_JUSTIFY  # type: ignore
from reportlab.pdfbase import pdfmetrics  # type: ignore
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
from typing import Dict, List
from arabic_reshaper import reshape  # type: ignore
from bidi.algorithm import get_display  # type: ignore
import html
import re
from xml.sax.saxutils import escape as _xml_escape

# Register Arabic font
FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansArabic-Regular.ttf")
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont('Arabic', FONT_PATH))
    ARABIC_FONT = 'Arabic'
else:
    ARABIC_FONT = 'Helvetica'  # Fallback


def arabic_text(text: str) -> str:
    """
    Process Arabic text for PDF display.
    Reshapes characters for proper letter joining, then applies
    bidi algorithm so ReportLab (which renders LTR) displays RTL correctly.
    """
    if not text:
        return ""
    try:
        if text.strip().lower().startswith("<html"):
            text = html.escape(text)

        reshaped_text = reshape(text)
        display_text = get_display(reshaped_text)
        if isinstance(display_text, bytes):
            return display_text.decode('utf-8')
        return display_text
    except Exception as e:
        print(f"Error processing Arabic text: {e}")
        return text


def _normalize_pipe_separated_text(text: str) -> str:
    """Turn pipe-heavy AI lists (a | b | c) into bullet-separated Arabic-friendly text."""
    if not text:
        return ""
    t = text.strip()
    if "|" not in t or t.count("|") < 1:
        return t
    parts = [p.strip().strip("'\"").strip() for p in t.split("|")]
    parts = [p for p in parts if p]
    if len(parts) <= 1:
        return t
    return " • ".join(parts)


def _truncate_for_pdf_cell(text: str, max_chars: int = 380) -> str:
    """Keep matrix/table cells short enough to fit one PDF page frame."""
    if not text:
        return text
    t = text.strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip() + "… (مختصر للتقرير)"


def pdf_cell_text(text: str, normalize_pipes: bool = True) -> str:
    """
    Safe string for ReportLab Paragraph: normalize messy markers, escape XML, then Arabic shaping.
    Unescaped < or & in AI text breaks the mini-HTML parser and can truncate the rest of the cell.
    """
    if text is None:
        return ""
    t = text.strip()
    if not t:
        return arabic_text("-")
    if t == "Not found":
        return arabic_text("-")
    from app.report_feedback_formatter import clean_report_text
    t = clean_report_text(t)
    if normalize_pipes:
        t = _normalize_pipe_separated_text(t)
    # Remove stray leading ASCII quotes before Arabic words (artifact from JSON/list parsing)
    t = re.sub(r"(^|\s)['\"]([\u0600-\u06FF])", r"\1\2", t)
    safe = _xml_escape(t, entities={"'": "&apos;", '"': "&quot;"})
    return arabic_text(safe)


def generate_student_report_pdf(
    student_name: str,
    student_email: str,
    grading_result: Dict,
    output_path: str
) -> str:
    """
    Generate a detailed PDF report for a student with Arabic support

    Args:
        student_name: Student's name
        student_email: Student's email
        grading_result: Complete grading result dictionary
        output_path: Path to save the PDF

    Returns:
        Path to the generated PDF file
    """

    # Create PDF document
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50,
    )

    # Container for the 'Flowable' objects
    elements = []

    # Define styles with Arabic font
    styles = getSampleStyleSheet()

    # Title style - لون أزرق غامق مع خلفية فاتحة
    title_style = ParagraphStyle(
        'ArabicTitle',
        parent=styles['Heading1'],
        fontName=ARABIC_FONT,
        fontSize=22,
        textColor=colors.HexColor('#1e3a8a'),
        spaceAfter=24,
        spaceBefore=12,
        alignment=TA_CENTER,
        borderColor=colors.HexColor('#3b82f6'),
        borderWidth=2,
        borderPadding=10,
        backColor=colors.HexColor('#eff6ff'),
    )

    # Heading style - لون بنفسجي حديث
    heading_style = ParagraphStyle(
        'ArabicHeading',
        parent=styles['Heading2'],
        fontName=ARABIC_FONT,
        fontSize=16,
        textColor=colors.HexColor('#7c3aed'),
        spaceAfter=12,
        spaceBefore=18,
        alignment=TA_RIGHT,
        borderPadding=6,
    )

    # Normal style — RTL word wrap avoids mid-word splits that truncate Arabic in cells
    normal_style = ParagraphStyle(
        'ArabicNormal',
        parent=styles['Normal'],
        fontName=ARABIC_FONT,
        fontSize=12,
        leading=18,
        alignment=TA_RIGHT,
        rightIndent=0,
        leftIndent=0,
        wordWrap='RTL',
        splitLongWords=0,
    )

    # Justified style for long text
    justified_style = ParagraphStyle(
        'ArabicJustified',
        parent=styles['Normal'],
        fontName=ARABIC_FONT,
        fontSize=12,
        leading=18,
        alignment=TA_JUSTIFY,
        rightIndent=0,
        leftIndent=0,
        wordWrap='RTL',
        splitLongWords=0,
    )

    # Bold style for emphasis - لون أزرق حديث
    bold_style = ParagraphStyle(
        'ArabicBold',
        parent=styles['Normal'],
        fontName=ARABIC_FONT,
        fontSize=13,
        leading=20,
        alignment=TA_RIGHT,
        textColor=colors.HexColor('#2563eb'),
    )

    # List item style
    list_style = ParagraphStyle(
        'ArabicList',
        parent=styles['Normal'],
        fontName=ARABIC_FONT,
        fontSize=11,
        leading=16,
        alignment=TA_RIGHT,
        rightIndent=0,
        leftIndent=20,
        wordWrap='RTL',
        splitLongWords=0,
    )

    matrix_cell_style = ParagraphStyle(
        'ArabicMatrixCell',
        parent=normal_style,
        fontSize=9,
        leading=12,
        wordWrap='RTL',
        splitLongWords=1,
    )

    # Add title
    elements.append(Paragraph(arabic_text(" تقرير تصحيح واجب BTEC"), title_style))
    elements.append(Paragraph(arabic_text("BTEC Assignment Grading Report"), ParagraphStyle(
        'SubTitle', parent=styles['Normal'], fontName=ARABIC_FONT, fontSize=12,
        alignment=TA_CENTER, textColor=colors.HexColor('#6b7280'), spaceAfter=8,
    )))
    elements.append(Spacer(1, 0.3 * inch))

    # Student info
    # RTL table: value on left (col 0), label on right (col 1)
    student_info_data = [
        [arabic_text(student_name), ": " + arabic_text("اسم الطالب")],
        [datetime.now().strftime("%Y-%m-%d %H:%M"), ": " + arabic_text("تاريخ التصحيح")],
    ]

    # Add fingerprint if available
    fingerprint = grading_result.get('content_fingerprint', {})
    if fingerprint:
        student_info_data.append([
            fingerprint.get('fingerprint_id', '-'),
            ": " + arabic_text("بصمة الملف")
        ])
        student_info_data.append([
            str(fingerprint.get('word_count', '-')),
            ": " + arabic_text("عدد الكلمات")
        ])

    student_info_table = Table(student_info_data, colWidths=[4 * inch, 2 * inch])
    student_info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), ARABIC_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4b5563')),
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#f3f4f6')),
        ('BACKGROUND', (0, 0), (0, -1), colors.white),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1.5, colors.HexColor('#e5e7eb')),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#eff6ff')),
    ]))

    elements.append(student_info_table)
    elements.append(Spacer(1, 0.4 * inch))

    # Overall summary — Executive Summary per Section 8
    # Fields are at top level of grading_result (not nested under 'summary')
    from app.official_grade import resolve_official_grade

    official = resolve_official_grade(grading_result, reapply_pipeline=True)
    grading_result["grade_display_metrics"] = official.grade_display_metrics
    total_score = grading_result.get('total_score', 0)
    max_score = grading_result.get('max_score', 100)
    percentage = grading_result.get('percentage', 0)
    grade_level = official.grade_label

    # Get AI and plagiarism scores for executive summary
    ai_info = grading_result.get('ai_detection_info', {})
    ai_risk_cls = ai_info.get('risk_classification', {})
    ai_score = ai_info.get('score', grading_result.get('ai_likelihood', 0))
    ai_icon = ai_risk_cls.get('icon', '❓')

    plag_info = grading_result.get("plagiarism_info", {})
    plag_max = plag_info.get("max_similarity", 0)

    elements.append(Paragraph(arabic_text(" الملخص التنفيذي"), heading_style))

    # RTL table: value on left (col 0), label on right (col 1)
    summary_data = [
        [f"{grade_level}", ": " + arabic_text("الدرجة الإجمالية")],
        [f"{percentage:.1f}%", ": " + arabic_text("النسبة المئوية")],
        [f"{total_score} / {max_score}", ": " + arabic_text("الدرجة الكلية")],
        [f"{ai_icon} {ai_score}%", ": " + arabic_text("نسبة الذكاء الاصطناعي")],
        [f"{plag_max:.1f}%", ": " + arabic_text("نسبة الانتحال")],
    ]

    if fingerprint:
        summary_data.append([fingerprint.get('fingerprint_id', '-'), ": " + arabic_text("بصمة الملف")])

    summary_table = Table(summary_data, colWidths=[4 * inch, 2 * inch])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), ARABIC_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.white),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1f2937')),
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#3b82f6')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#eff6ff')),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1.5, colors.HexColor('#60a5fa')),
        ('LEFTPADDING', (0, 0), (-1, -1), 14),
        ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Plagiarism Section
    plag_info = grading_result.get("plagiarism_info")
    if plag_info:
        elements.append(Paragraph(arabic_text("🔗 تحليل الانتحال (Plagiarism Analysis)"), heading_style))

        max_sim = plag_info.get("max_similarity", 0)

        # Use 5-tier classification per Section 4.3
        if max_sim <= 10:
            plag_text = f"✅ مقبول: تشابه طبيعي ({max_sim:.1f}%)"
            plag_color = colors.green
        elif max_sim <= 25:
            plag_text = f"🟡 تشابه ملحوظ - يحتاج مراقبة ({max_sim:.1f}%)"
            plag_color = colors.HexColor('#eab308')
        elif max_sim <= 50:
            plag_text = f"🟠 انتحال مشتبه به - يحتاج تحقيق ({max_sim:.1f}%)"
            plag_color = colors.orange
        elif max_sim <= 75:
            plag_text = f"🔴 انتحال واضح ({max_sim:.1f}%)"
            plag_color = colors.red
        else:
            plag_text = f"⛔ نسخ شبه كامل ({max_sim:.1f}%)"
            plag_color = colors.HexColor('#7f1d1d')

        elements.append(Paragraph(pdf_cell_text(plag_text, normalize_pipes=False), ParagraphStyle(
            'PlagStatus', parent=normal_style, textColor=plag_color, fontSize=12, spaceAfter=10
        )))

        matches = plag_info.get("matches", [])
        if matches:
            elements.append(Paragraph(": " + arabic_text("أعلى حالات التشابه مع طلاب آخرين"), normal_style))

            # RTL table: columns reversed (right to left)
            p_data = [[arabic_text("الحالة"), arabic_text("النسبة"), arabic_text("الطالب المقارن")]]
            for m in matches:
                p_data.append([
                    arabic_text("مشبوه" if m['is_suspicious'] else "عادي"),
                    f"{m['percentage']}%",
                    arabic_text(m["student"])
                ])

            p_table = Table(p_data, colWidths=[2 * inch, 1 * inch, 3 * inch])
            p_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), ARABIC_FONT),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ]))
            elements.append(p_table)
            elements.append(Spacer(1, 0.3 * inch))

    # AI Detection Analysis Section (Section 8 — تحليل الذكاء الاصطناعي)
    ai_detection = grading_result.get('ai_detection_info', {})
    if ai_detection:
        elements.append(Paragraph(arabic_text(" تحليل الذكاء الاصطناعي (AI Content Analysis)"), heading_style))

        ai_score_val = ai_detection.get('score', grading_result.get('ai_likelihood', 0))
        ai_risk_cls_val = ai_detection.get('risk_classification', {})
        ai_icon_val = ai_risk_cls_val.get('icon', '❓')
        ai_label_val = ai_risk_cls_val.get('label_ar', '-')

        # AI score display with color
        if ai_score_val <= 20:
            ai_color = colors.green
        elif ai_score_val <= 40:
            ai_color = colors.HexColor('#eab308')
        elif ai_score_val <= 60:
            ai_color = colors.orange
        elif ai_score_val <= 80:
            ai_color = colors.red
        else:
            ai_color = colors.HexColor('#7f1d1d')

        elements.append(Paragraph(
            arabic_text(f"{ai_icon_val} النسبة: {ai_score_val}% — {ai_label_val}"),
            ParagraphStyle('AIStatus', parent=normal_style, textColor=ai_color, fontSize=12, spaceAfter=10)
        ))

        # Show detected indicators
        indicators = ai_detection.get('indicators_detected', [])
        if indicators:
            elements.append(Paragraph(": " + arabic_text("المؤشرات المكتشفة"), normal_style))
            for ind in indicators[:10]:
                elements.append(Paragraph(pdf_cell_text(f"• {ind}", normalize_pipes=False), list_style))
            elements.append(Spacer(1, 0.15 * inch))

        elements.append(Spacer(1, 0.2 * inch))

    # Current Level Achievement
    achieved_levels = [c.get('criteria_level', '') for c in grading_result.get('criteria_results', []) if c.get('achieved', False)]
    if achieved_levels:
        current_level = achieved_levels[-1]  # Last achieved level
        elements.append(Paragraph(arabic_text(" المعيار الحالي للطالب"), heading_style))
        elements.append(Paragraph(arabic_text(f"أنت حالياً في مستوى: <b>{current_level}</b>"), bold_style))
        elements.append(Spacer(1, 0.3 * inch))

    # Criteria results
    elements.append(Paragraph(arabic_text(" تفاصيل المعايير"), heading_style))
    elements.append(Spacer(1, 0.1 * inch))

    # Sort results by level P1, P2, M1, D1
    def _sort_key(r):
        level = r.get('criteria_level', '')
        # Extract the letter+number part (e.g., "B.P3" -> "P3", "P1" -> "P1")
        short = level.split('.')[-1] if '.' in level else level
        # Sort by type: P < M < D, then by number
        type_order = {'P': 0, 'M': 1, 'D': 2}
        letter = short[0].upper() if short else 'Z'
        num = short[1:] if len(short) > 1 else '0'
        try:
            num_val = int(num)
        except ValueError:
            num_val = 99
        return (type_order.get(letter, 9), num_val)

    # Use actual criteria from the grading result instead of hardcoded levels
    sorted_criteria = sorted(
        grading_result.get('criteria_results', []),
        key=_sort_key
    )

    # Iterate through actual criteria results
    for criteria in sorted_criteria:
        level = criteria.get('criteria_level', '')

        achieved = bool(criteria.get('achieved', False))
        authority = criteria.get('achievement_authority') or ''
        human_review = authority == 'HUMAN_REVIEW_REQUIRED'
        feedback = str(criteria.get('feedback', ''))
        missing_points = criteria.get('missing_points', [])
        if not isinstance(missing_points, list):
            missing_points = []
        next_level = criteria.get('next_level_requirements', '')
        explanation = str(criteria.get('explanation', ''))

        # Criteria box with background color - تصميم محدث
        if human_review:
            bg_color = colors.HexColor('#fef3c7')
            border_color = colors.HexColor('#f59e0b')
            status_icon = "⏸"
            status_text = "مراجعة بشرية مطلوبة (Human Review Required)"
        elif achieved:
            bg_color = colors.HexColor('#d1fae5')
            border_color = colors.HexColor('#10b981')
            status_icon = "✅"
            status_text = "متحقق (Achieved)"
        else:
            bg_color = colors.HexColor('#fee2e2')
            border_color = colors.HexColor('#ef4444')
            status_icon = "❌"
            status_text = "غير متحقق (Not Achieved)"

        # Criteria header with colored box (RTL: status on left, criterion on right)
        criteria_header_data = [[
            arabic_text(f"{status_text}"),
            arabic_text(f"{status_icon} المعيار {level}")
        ]]

        criteria_header_table = Table(criteria_header_data, colWidths=[3 * inch, 3 * inch])
        criteria_header_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), ARABIC_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('BACKGROUND', (0, 0), (-1, -1), bg_color),
            ('TEXTCOLOR', (1, 0), (1, 0), colors.HexColor('#1e3a8a')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 2.5, border_color),
        ]))

        elements.append(criteria_header_table)
        elements.append(Spacer(1, 0.15 * inch))

        # Detailed Explanation
        if explanation:
            elements.append(Paragraph("<b>: </b>" + arabic_text("<b>الشرح المفصل</b>"), bold_style))
            elements.append(Paragraph(pdf_cell_text(explanation), justified_style))
            elements.append(Spacer(1, 0.15 * inch))

        # Feedback
        if feedback:
            from app.report_feedback_formatter import format_criterion_feedback_for_report
            feedback = format_criterion_feedback_for_report(
                feedback,
                runtime_note_ar=criteria.get("runtime_observation_note_ar"),
            )
            elements.append(Paragraph("<b>: </b>" + arabic_text("<b>الملاحظات</b>"), bold_style))
            elements.append(Paragraph(pdf_cell_text(feedback), justified_style))
            elements.append(Spacer(1, 0.15 * inch))

        # Decision Matrix (New Strict BTEC Feedback)
        decision_matrix = criteria.get('decision_matrix', [])
        if not isinstance(decision_matrix, list):
            decision_matrix = []
        if decision_matrix:
            elements.append(Paragraph("<b>: </b>" + arabic_text("<b>متطلبات المعيار</b>"), bold_style))

            # Header style with white text for the blue background
            header_style = ParagraphStyle(
                'MatrixHeader',
                parent=bold_style,
                textColor=colors.white,
                alignment=TA_CENTER
            )

            # Table Header - Reversed for RTL: [Left (Evidence), Middle (Status), Right (Requirement)]
            matrix_header_row = [
                Paragraph(arabic_text("الدليل (Evidence)"), header_style),
                Paragraph(arabic_text("الحالة (Status)"), header_style),
                Paragraph(arabic_text("المتطلب (Requirement)"), header_style),
            ]
            matrix_rows: list = []

            for item in decision_matrix:
                if not isinstance(item, dict):
                    continue
                req = _truncate_for_pdf_cell(str(item.get("requirement", "")))
                met = bool(item.get("met", False))
                evidence = _truncate_for_pdf_cell(str(item.get("evidence", "")))

                status_symbol = "✅" if met else "❌"
                status_str = "متحقق" if met else "غير متحقق"

                ev_text = evidence if evidence and evidence != "Not found" else "-"

                matrix_rows.append([
                    Paragraph(pdf_cell_text(ev_text), matrix_cell_style),
                    Paragraph(arabic_text(f"{status_symbol} {status_str}"), normal_style),
                    Paragraph(pdf_cell_text(req), matrix_cell_style),
                ])

            matrix_table_style = TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), ARABIC_FONT),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fafafa')),
                ('GRID', (0, 0), (-1, -1), 1.2, colors.HexColor('#d1d5db')),
                ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#6366f1')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ])
            matrix_col_widths = [2.8 * inch, 1.2 * inch, 2.5 * inch]
            chunk_size = 6

            for chunk_start in range(0, len(matrix_rows), chunk_size):
                chunk = matrix_rows[chunk_start: chunk_start + chunk_size]
                chunk_table = Table(
                    [matrix_header_row] + chunk,
                    colWidths=matrix_col_widths,
                    repeatRows=1,
                    splitByRow=1,
                )
                chunk_table.setStyle(matrix_table_style)
                elements.append(chunk_table)
                if chunk_start + chunk_size < len(matrix_rows):
                    elements.append(Spacer(1, 0.08 * inch))

            elements.append(Spacer(1, 0.15 * inch))

        # Missing points removed

        # Rule Validation Results (New)
        rule_validation = criteria.get('rule_validation', {})
        if isinstance(rule_validation, dict) and rule_validation:
            matched_keywords = rule_validation.get('matched_keywords', [])
            if not isinstance(matched_keywords, list):
                matched_keywords = []
            matched_patterns = rule_validation.get('matched_patterns', [])
            if not isinstance(matched_patterns, list):
                matched_patterns = []

            if matched_keywords or matched_patterns:
                elements.append(Paragraph("<b>: </b>" + arabic_text("<b>التحقق من الكلمات المفتاحية</b>"), bold_style))
                found_terms = [str(t) for t in matched_keywords + matched_patterns]
                # Show top 5 terms found
                top_terms = [found_terms[j] for j in range(min(5, len(found_terms)))]
                terms_text = ", ".join(top_terms)
                if len(found_terms) > 5:
                    terms_text += "..."

                elements.append(Paragraph(pdf_cell_text(f"تم العثور على مصطلحات: {terms_text}"), list_style))
                elements.append(Spacer(1, 0.15 * inch))

        # Next level requirements
        if next_level and not achieved:
            elements.append(Paragraph("<b>: </b>" + arabic_text("<b>للوصول للمعيار التالي</b>"), bold_style))
            # Handle both list and string formats
            if isinstance(next_level, list):
                for req in next_level:
                    elements.append(Paragraph(pdf_cell_text(f"• {req}"), list_style))
            else:
                elements.append(Paragraph(pdf_cell_text(str(next_level)), justified_style))

        elements.append(Spacer(1, 0.3 * inch))

    # Strengths — Section 8 format
    strengths = grading_result.get('strengths', [])
    if strengths:
        elements.append(Paragraph(arabic_text("🟢 نقاط قوة الطالب"), heading_style))
        for i, strength in enumerate(strengths, 1):
            elements.append(Paragraph(pdf_cell_text(f"{i}. {strength}"), normal_style))
        elements.append(Spacer(1, 0.2 * inch))

    # Improvements — categorized per Section 8 (Critical + Suggested)
    improvements = grading_result.get('improvements', [])
    if improvements:
        elements.append(Paragraph(arabic_text("💡 التحسينات المطلوبة"), heading_style))

        # Split into critical (first half) and suggested (second half)
        mid = max(1, len(improvements) // 2)
        critical = improvements[:mid]
        suggested = improvements[mid:]

        if critical:
            elements.append(Paragraph("<b>: </b>" + arabic_text("<b>تحسينات حرجة (يجب إكمالها)</b>") + " 🔴", bold_style))
            for i, imp in enumerate(critical, 1):
                elements.append(Paragraph(pdf_cell_text(f"{i}. {imp}"), list_style))
            elements.append(Spacer(1, 0.15 * inch))

        if suggested:
            elements.append(Paragraph("<b>: </b>" + arabic_text("<b>تحسينات مقترحة (للحصول على درجة أعلى)</b>") + " 🟡", bold_style))
            for i, imp in enumerate(suggested, 1):
                elements.append(Paragraph(pdf_cell_text(f"{i}. {imp}"), list_style))

        elements.append(Spacer(1, 0.2 * inch))

    # Overall feedback
    overall_feedback = grading_result.get('overall_feedback', '')
    if overall_feedback:
        elements.append(Paragraph(arabic_text("التقييم العام"), heading_style))
        elements.append(Paragraph(pdf_cell_text(overall_feedback), normal_style))

    # Build PDF
    doc.build(elements)

    return output_path


def _criteria_sort_key(level: str) -> tuple:
    short = (level or "").split(".")[-1] if "." in (level or "") else (level or "")
    short = short.split("/")[-1] if "/" in short else short
    letter = short[0].upper() if short else "Z"
    num_part = short[1:] if len(short) > 1 else "0"
    try:
        num_val = int("".join(c for c in num_part if c.isdigit()) or "99")
    except ValueError:
        num_val = 99
    type_order = {"P": 0, "M": 1, "D": 2}
    return (type_order.get(letter, 9), num_val, level or "")


def _criteria_header_label(level: str) -> str:
    if not level:
        return "—"
    if "/" in level:
        return level.split("/", 1)[-1]
    return level.split(".")[-1] if "." in level else level


def _criteria_achieved_mark(achieved: bool) -> str:
    """PDF-safe achievement cell (Arabic 'تم' breaks under RTL font)."""
    return "\u2713" if achieved else "\u2717"


def _short_btec_grade(result: dict) -> str:
    from app.official_grade import resolve_official_grade

    official = resolve_official_grade(result, reapply_pipeline=False)
    return official.grade


def _expected_btec_grade(result: dict) -> str:
    gdm = result.get("grade_display_metrics") or {}
    erg = result.get("expected_runtime_grade") or gdm.get("expected_runtime_grade") or {}
    exp = str(erg.get("expected_btec_grade") or "").strip().upper()
    if exp in ("D", "M", "P", "U"):
        return exp
    return ""


def _collect_batch_criteria_levels(results: List[Dict]) -> List[str]:
    seen: set[str] = set()
    levels: List[str] = []
    for result in results:
        if not result.get("success", False):
            continue
        for cr in result.get("criteria_results") or []:
            lvl = str(cr.get("criteria_level") or "").strip()
            if lvl and lvl not in seen:
                seen.add(lvl)
                levels.append(lvl)
    levels.sort(key=_criteria_sort_key)
    return levels


def format_batch_report_title(raw_title: str) -> str:
    """Batch summary PDF heading: واجب : <assignment name>."""
    name = (raw_title or "").strip()
    if not name:
        return arabic_text("واجب")
    if name.startswith("واجب"):
        return arabic_text(name)
    return arabic_text(f"واجب : {name}")


def generate_batch_summary_report(
    report_title: str,
    results: List[Dict],
    output_path: str
) -> str:
    """
    Generate a summary report for a batch of students
    """
    from reportlab.lib.pagesizes import A4, landscape  # type: ignore
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # type: ignore
    from reportlab.lib.units import inch  # type: ignore
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle  # type: ignore
    from reportlab.lib import colors  # type: ignore
    from reportlab.lib.enums import TA_CENTER  # type: ignore

    # Create PDF document
    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )

    elements = []
    styles = getSampleStyleSheet()

    # Title style - تصميم عصري
    title_style = ParagraphStyle(
        'ArabicTitle',
        parent=styles['Heading1'],
        fontName=ARABIC_FONT,
        fontSize=22,
        textColor=colors.HexColor('#1e3a8a'),
        spaceAfter=20,
        spaceBefore=12,
        alignment=TA_CENTER,
        borderColor=colors.HexColor('#3b82f6'),
        borderWidth=2,
        borderPadding=10,
        backColor=colors.HexColor('#eff6ff'),
    )

    # Add title
    elements.append(Paragraph(
        format_batch_report_title(report_title) if report_title else arabic_text("تقرير ملخص الدفعة"),
        title_style,
    ))
    elements.append(Spacer(1, 0.2 * inch))

    # Statistics
    total_students = len(results)
    successful = sum(1 for r in results if r.get("success", False))
    avg_percentage = sum(r.get("percentage", 0) for r in results if r.get("success", False)) / successful if successful > 0 else 0

    stats_data = [
        [arabic_text("القيمة"), arabic_text("الإحصائية")],
        [str(total_students), arabic_text("إجمالي الطلاب")],
        [str(successful), arabic_text("تم التصحيح بنجاح")],
        [f"{avg_percentage:.1f}%", arabic_text("متوسط الدرجات")],
    ]

    stats_table = Table(stats_data, colWidths=[1.5 * inch, 2 * inch])
    stats_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), ARABIC_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#eff6ff')),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#1f2937')),
        ('GRID', (0, 0), (-1, -1), 1.5, colors.HexColor('#60a5fa')),
        ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#3b82f6')),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))

    elements.append(stats_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Results table header
    elements.append(Paragraph(arabic_text("نتائج الطلاب"), title_style))

    criteria_levels = _collect_batch_criteria_levels(results)
    if not criteria_levels:
        criteria_levels = ["P1", "P2", "M1", "D1"]

    # Results table — dynamic BTEC criteria columns; avoid emoji (not in Arabic PDF font)
    header = [
        arabic_text("المتوقع"),
        arabic_text("المعتمد"),
        arabic_text("النسبة"),
        arabic_text("الدرجة"),
    ]
    header.extend(arabic_text(_criteria_header_label(lvl)) for lvl in criteria_levels)
    header.extend([arabic_text("اسم الطالب"), "#"])
    table_data = [header]
    criteria_achieved_by_row: List[List[bool]] = []

    for i, result in enumerate(results, 1):
        if result.get("success", False):
            criteria_map: dict = {}
            for r in result.get("criteria_results", []):
                raw_level = r.get("criteria_level", "")
                criteria_map[raw_level] = r
                short = raw_level.split(".")[-1] if "." in raw_level else raw_level
                criteria_map[short] = r
                if "/" in raw_level:
                    criteria_map[raw_level.split("/", 1)[-1]] = r

            official = _short_btec_grade(result)
            expected = _expected_btec_grade(result)
            expected_cell = expected if expected and expected != official else "—"

            row = [
                expected_cell,
                official,
                f"{result.get('percentage', 0):.0f}%",
                f"{result.get('total_score', 0)}/{result.get('max_score', 0)}",
            ]
            row_flags: List[bool] = []
            for lvl in criteria_levels:
                cr = criteria_map.get(lvl) or criteria_map.get(_criteria_header_label(lvl), {})
                ok = bool(cr.get("achieved"))
                row_flags.append(ok)
                row.append(_criteria_achieved_mark(ok))
            criteria_achieved_by_row.append(row_flags)
            row.extend([
                arabic_text(result.get("student_name", "-")),
                str(i),
            ])
        else:
            row = [
                "—",
                arabic_text("فشل"),
                "-",
                "-",
            ]
            criteria_achieved_by_row.append([False] * len(criteria_levels))
            row.extend([_criteria_achieved_mark(False)] * len(criteria_levels))
            row.extend([
                arabic_text(result.get("student_name", "-")),
                str(i),
            ])
        table_data.append(row)

    page_width = landscape(A4)[0] - 60  # margins
    fixed_widths = [0.55 * inch, 0.55 * inch, 0.65 * inch, 0.85 * inch]
    name_width = 2.2 * inch
    idx_width = 0.35 * inch
    crit_count = max(len(criteria_levels), 1)
    remaining = page_width - sum(fixed_widths) - name_width - idx_width
    crit_width = max(0.42 * inch, remaining / crit_count)
    col_widths = fixed_widths + [crit_width] * crit_count + [name_width, idx_width]

    results_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    crit_start_col = 4
    table_style_cmds = [
        ('FONTNAME', (0, 0), (-1, -1), ARABIC_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fafafa')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
        ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#6366f1')),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
    ]
    if crit_count > 0:
        crit_end_col = crit_start_col + crit_count - 1
        table_style_cmds.extend([
            ('FONTNAME', (crit_start_col, 1), (crit_end_col, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (crit_start_col, 1), (crit_end_col, -1), 11),
        ])
        for row_i, flags in enumerate(criteria_achieved_by_row, start=1):
            for ci, ok in enumerate(flags):
                col = crit_start_col + ci
                table_style_cmds.append((
                    'TEXTCOLOR',
                    (col, row_i),
                    (col, row_i),
                    colors.HexColor('#15803d') if ok else colors.HexColor('#dc2626'),
                ))
    results_table.setStyle(TableStyle(table_style_cmds))

    elements.append(results_table)

    # Build PDF
    doc.build(elements)

    return output_path


def rebuild_batch_summary_results_from_db(db, batch_id: int) -> tuple[str, List[Dict]]:
    """Build batch summary payload from stored submissions (fresh criteria + grades)."""
    import json

    from app.models import Assignment, BatchGrading, GradingSummary, Submission, SubmissionStatus
    from app.evidence_registry import build_grade_display_metrics

    batch = db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
    if not batch:
        return "", []

    assignment = (
        db.query(Assignment).filter(Assignment.id == batch.assignment_id).first()
    )
    report_title = (
        str(assignment.title).strip()
        if assignment and getattr(assignment, "title", None)
        else (batch.batch_name or f"Batch {batch_id}")
    )
    submissions = db.query(Submission).filter(Submission.batch_id == batch_id).all()
    results: List[Dict] = []

    for submission in submissions:
        if submission.status == SubmissionStatus.FAILED:
            err = None
            if submission.grading_snapshot_json:
                try:
                    err = json.loads(str(submission.grading_snapshot_json)).get("error")
                except Exception:
                    err = None
            results.append(
                {
                    "success": False,
                    "student_name": submission.student_name or "—",
                    "error": err,
                }
            )
            continue

        summary = (
            db.query(GradingSummary)
            .filter(GradingSummary.submission_id == submission.id)
            .first()
        )
        if not summary:
            continue

        snap: dict = {}
        if submission.grading_snapshot_json:
            try:
                snap = json.loads(str(submission.grading_snapshot_json))
            except Exception:
                snap = {}

        gdm = build_grade_display_metrics(snap)
        from app.official_grade import resolve_official_grade

        official = resolve_official_grade(snap, reapply_pipeline=True)
        gdm = official.grade_display_metrics or gdm
        results.append(
            {
                "success": True,
                "student_name": submission.student_name or "—",
                "total_score": summary.total_score,
                "max_score": summary.max_score or 100,
                "percentage": summary.percentage,
                "grade_level": official.grade_label,
                "official_grade": official.to_dict(),
                "criteria_results": snap.get("criteria_results") or [],
                "institutional_resolution": snap.get("institutional_resolution"),
                "expected_runtime_grade": gdm.get("expected_runtime_grade"),
                "grade_display_metrics": gdm,
            }
        )

    return report_title, results


def regenerate_batch_summary_pdf(db, batch_id: int) -> str | None:
    """Regenerate batch summary PDF from DB snapshots (updates existing file)."""
    from pathlib import Path

    report_title, results = rebuild_batch_summary_results_from_db(db, batch_id)
    if not results:
        return None
    out_dir = Path("uploads") / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"batch_summary_{batch_id}.pdf"
    generate_batch_summary_report(report_title, results, str(out_path))
    return str(out_path)
