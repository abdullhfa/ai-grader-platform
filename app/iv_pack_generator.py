"""
Internal Verification (IV) / External Verification (EV) pack — PRO only.

Produces human-readable HTML (+ optional PDF) from pearson_btec_pro snapshot:
Decision, Evidence, Justification, Audit Trail per criterion.
"""
from __future__ import annotations

import html
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

IV_PACK_VERSION = "iv_pack_v1"
_DEFAULT_DIR = Path(os.getenv("IV_PACK_OUTPUT_DIR", "uploads/reports/iv_packs"))


def _safe_slug(name: str) -> str:
    s = re.sub(r"[^\w\u0600-\u06FF\-]+", "_", (name or "student").strip())
    return s[:80] or "student"


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def render_iv_pack_html(
    grading_result: Dict[str, Any],
    *,
    student_name: str = "",
    assignment_title: str = "",
) -> str:
    pkg = grading_result.get("pearson_btec_pro") or {}
    trail = pkg.get("audit_trail") or []
    unit = pkg.get("unit_award_validation") or {}
    authenticity = pkg.get("authenticity") or {}
    gameplay = pkg.get("gameplay_validation") or {}
    locators = pkg.get("evidence_locators_by_criterion") or {}

    rows_html: List[str] = []
    for entry in trail:
        if not isinstance(entry, dict):
            continue
        level = _esc(entry.get("criteria_level"))
        achieved = "نعم" if entry.get("achieved") else "لا"
        awardable = "نعم" if entry.get("awardable") else "لا"
        loc_list = locators.get(_short_from_level(str(entry.get("criteria_level") or ""))) or []
        if not loc_list:
            lv_full = str(entry.get("criteria_level") or "")
            loc_list = locators.get(lv_full) or []
        loc_html = ""
        if loc_list:
            items = []
            for loc in loc_list[:8]:
                if not isinstance(loc, dict):
                    continue
                items.append(
                    "<li>"
                    f"<strong>{_esc(loc.get('artifact_file') or '—')}</strong>"
                    f" — {_esc(loc.get('evidence_section') or '')}"
                    f" — صفحة/موضع: {_esc(loc.get('page_or_position') or '—')}"
                    f" — دليل: {_esc(loc.get('proof') or '')[:200]}"
                    "</li>"
                )
            loc_html = f"<ul>{''.join(items)}</ul>"
        else:
            loc_html = "<p class='muted'>لا يوجد موضّع دليل مفصّل — مراجعة IV مطلوبة.</p>"

        rows_html.append(
            f"""
            <section class="criterion">
              <h3>{level} — تحقق: {achieved} | قابل للمنح: {awardable}</h3>
              <p><strong>القرار:</strong> {_esc(entry.get('accept_reason_ar') or entry.get('reject_reason_ar'))}</p>
              <p><strong>السلطة:</strong> {_esc(entry.get('achievement_authority'))}</p>
              <p><strong>الدرجة المرجّحة للأدلة:</strong> {_esc(entry.get('evidence_weighted_score'))}%</p>
              <h4>مواضع الأدلة (Evidence Locator)</h4>
              {loc_html}
              <h4>التبرير (مقتطف)</h4>
              <p class="feedback">{_esc(entry.get('feedback_excerpt'))}</p>
            </section>
            """
        )

    gp_checks = gameplay.get("checks") or {}
    gp_rows = ""
    for key, chk in gp_checks.items():
        if isinstance(chk, dict):
            gp_rows += (
                f"<tr><td>{_esc(key)}</td>"
                f"<td>{'نعم' if chk.get('observed') else 'لا'}</td>"
                f"<td>{_esc(chk.get('source'))}</td>"
                f"<td>{_esc(chk.get('note_ar'))}</td></tr>"
            )

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8"/>
  <title>حزمة IV/EV — {_esc(student_name)}</title>
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, sans-serif; margin: 24px; background: #f8fafc; color: #1e293b; }}
    h1 {{ color: #0f766e; }}
    h2 {{ border-bottom: 2px solid #0d9488; padding-bottom: 6px; }}
    .criterion {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 12px 0; }}
    .feedback {{ white-space: pre-wrap; font-size: 0.95rem; }}
    .muted {{ color: #64748b; }}
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px; text-align: right; }}
    th {{ background: #ecfeff; }}
    .warn {{ background: #fff7ed; border-right: 4px solid #f97316; padding: 12px; }}
  </style>
</head>
<body>
  <h1>حزمة المراجعة الداخلية / الخارجية (Pearson BTEC — PRO)</h1>
  <p><strong>الطالب:</strong> {_esc(student_name)}</p>
  <p><strong>المهمة:</strong> {_esc(assignment_title)}</p>
  <p><strong>التقدير المؤسسي:</strong> {_esc(grading_result.get('grade_level'))}</p>
  <p><strong>نسبة المعايير:</strong> {_esc(grading_result.get('criteria_score_pct') or grading_result.get('percentage'))}%</p>

  <h2>التحقق على مستوى الوحدة (Unit Award)</h2>
  <table>
    <tr><th>البند</th><th>القيمة</th></tr>
    <tr><td>الفرقة القابلة للمنح</td><td>{_esc(unit.get('unit_awardable_band'))}</td></tr>
    <tr><td>Merit على مستوى الوحدة</td><td>{'نعم' if unit.get('merit_unit_awardable') else 'لا'}</td></tr>
    <tr><td>Distinction على مستوى الوحدة</td><td>{'نعم' if unit.get('distinction_unit_awardable') else 'لا'}</td></tr>
    <tr><td>سبب الحجب (عربي)</td><td>{_esc(unit.get('unit_block_reason_ar'))}</td></tr>
  </table>

  <h2>الأصالة (تحذير فقط — لا إلغاء تلقائي)</h2>
  <div class="warn">
    <p><strong>تحذير الأصالة:</strong> {_esc(authenticity.get('authenticity_warning_ar'))}</p>
    <p>احتمال AI: {_esc(authenticity.get('ai_likelihood_pct'))}% — 
       إجراء: {_esc(authenticity.get('recommended_action_ar'))}</p>
    <p>إلغاء تلقائي بسبب AI: {'ممنوع في PRO' if authenticity.get('automatic_fail_prohibited') else '—'}</p>
  </div>

  <h2>التحقق من أسلوب اللعب (Gameplay)</h2>
  <p class="muted">{_esc(gameplay.get('summary_ar'))}</p>
  <table>
    <tr><th>الفحص</th><th>مُلاحظ</th><th>المصدر</th><th>ملاحظة</th></tr>
    {gp_rows or "<tr><td colspan='4'>لا توجد أدلة تشغيل كافية</td></tr>"}
  </table>

  <h2>سجل القرارات — معيار بمعيار</h2>
  {''.join(rows_html) or '<p>لا توجد معايير.</p>'}

  <p class="muted">Generated {IV_PACK_VERSION} — {time.strftime('%Y-%m-%d %H:%M')}</p>
</body>
</html>"""


def _short_from_level(level: str) -> str:
    lv = (level or "").strip().upper()
    return lv.split(".")[-1] if "." in lv else lv


def generate_iv_pack_files(
    grading_result: Dict[str, Any],
    *,
    student_name: str = "",
    assignment_title: str = "",
    submission_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Write HTML IV pack; attempt PDF when ReportLab + font available."""
    _DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    slug = _safe_slug(student_name)
    sid = submission_id or grading_result.get("submission_id") or 0
    stamp = int(time.time())
    base = f"iv_pack_{sid}_{slug}_{stamp}"
    html_path = _DEFAULT_DIR / f"{base}.html"
    html_body = render_iv_pack_html(
        grading_result,
        student_name=student_name,
        assignment_title=assignment_title,
    )
    html_path.write_text(html_body, encoding="utf-8")

    pdf_path: Optional[Path] = None
    pdf_error: Optional[str] = None
    try:
        pdf_path = _DEFAULT_DIR / f"{base}.pdf"
        _write_iv_pack_pdf(grading_result, pdf_path, student_name=student_name)
    except Exception as exc:
        pdf_path = None
        pdf_error = str(exc)

    rel_html = str(html_path).replace("\\", "/")
    out: Dict[str, Any] = {
        "version": IV_PACK_VERSION,
        "html_path": rel_html,
        "html_url": f"/{rel_html}" if not rel_html.startswith("/") else rel_html,
        "generated_at": stamp,
    }
    if pdf_path and pdf_path.is_file():
        rel_pdf = str(pdf_path).replace("\\", "/")
        out["pdf_path"] = rel_pdf
        out["pdf_url"] = f"/{rel_pdf}" if not rel_pdf.startswith("/") else rel_pdf
    if pdf_error:
        out["pdf_error"] = pdf_error
    return out


def _write_iv_pack_pdf(
    grading_result: Dict[str, Any],
    path: Path,
    *,
    student_name: str,
) -> None:
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer  # type: ignore
    from reportlab.lib.styles import getSampleStyleSheet  # type: ignore

    from app.report_generator import ARABIC_FONT, arabic_text

    styles = getSampleStyleSheet()
    story: List[Any] = []
    title = arabic_text(f"حزمة IV — {student_name}")
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 12))
    pkg = grading_result.get("pearson_btec_pro") or {}
    unit = pkg.get("unit_award_validation") or {}
    story.append(
        Paragraph(
            arabic_text(
                f"التقدير: {grading_result.get('grade_level')} — "
                f"فرقة الوحدة: {unit.get('unit_awardable_band')}"
            ),
            styles["Normal"],
        )
    )
    for entry in pkg.get("audit_trail") or []:
        if not isinstance(entry, dict):
            continue
        line = (
            f"{entry.get('criteria_level')}: "
            f"{'متحقق' if entry.get('achieved') else 'غير متحقق'} — "
            f"{(entry.get('accept_reason_ar') or entry.get('reject_reason_ar') or '')[:120]}"
        )
        story.append(Paragraph(arabic_text(line), styles["Normal"]))
        story.append(Spacer(1, 6))
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    doc.build(story)


def attach_iv_pack_to_grading_result(
    grading_result: Dict[str, Any],
    *,
    student_name: str = "",
    assignment_title: str = "",
    submission_id: Optional[int] = None,
) -> Dict[str, Any]:
    """PRO: attach IV pack file paths into pearson_btec_pro.iv_pack."""
    files = generate_iv_pack_files(
        grading_result,
        student_name=student_name or grading_result.get("student_name") or "",
        assignment_title=assignment_title,
        submission_id=submission_id,
    )
    pkg = grading_result.setdefault("pearson_btec_pro", {})
    pkg["iv_pack"] = files
    return files
