"""Verifiable signed PDF audit artifact — not a summary-only report."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from reportlab.lib import colors  # type: ignore
from reportlab.lib.pagesizes import A4  # type: ignore
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
from reportlab.lib.units import inch  # type: ignore
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # type: ignore

from app.governance.institutional_export import export_signed_report_stub
from app.governance.replay_viewer import load_replay_inspection_bundle
from app.governance_ui.presenters.timeline_presenter import present_timeline


def _integrity_label(bundle, report: Dict[str, Any]) -> str:
    flags = (bundle.hallucination_flags or []) + (
        (bundle.ai_reasoning or {}).get("hallucination_flags") or []
    )
    if flags:
        return "suspicious — review required"
    final = (bundle.ai_reasoning or {}).get("final_decision") or {}
    if final.get("requires_manual_review"):
        return "manual_review_required"
    return "clean"


def build_signed_pdf_report(
    submission_key: str,
    session_id: str,
    *,
    signed_evaluation_hash: Optional[str] = None,
) -> bytes:
    """Generate verifiable audit PDF linked to replay hash."""
    bundle = load_replay_inspection_bundle(submission_key, session_id)
    report = export_signed_report_stub(
        submission_key, session_id, signed_evaluation_hash=signed_evaluation_hash
    )
    timeline = present_timeline(bundle)
    final = (bundle.ai_reasoning or {}).get("final_decision") or {}
    grade = (
        (report.get("signoff") or {}).get("final_grade")
        or (bundle.grading_summary or {}).get("grade_level")
        or "—"
    )
    replay_hash = report.get("replay_hash") or bundle.deterministic_hash or "—"
    signed_hash = report.get("signed_evaluation_hash") or "unsigned"
    examiner = ((report.get("signoff") or {}).get("examiner_id")) or "pending_signoff"
    ts = ((report.get("signoff") or {}).get("timestamp")) or datetime.now(timezone.utc).isoformat()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=48, leftMargin=48, topMargin=48, bottomMargin=48)
    styles = getSampleStyleSheet()
    mono = ParagraphStyle("Mono", parent=styles["Normal"], fontName="Courier", fontSize=8, leading=10)
    title = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=16, spaceAfter=12)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, spaceAfter=8)

    story = []
    story.append(Paragraph("Institutional Signed Evaluation Report", title))
    story.append(Paragraph("Verifiable Audit Artifact — replay hash anchored", styles["Normal"]))
    story.append(Spacer(1, 0.2 * inch))

    meta = [
        ["Submission", submission_key],
        ["Session", session_id],
        ["Final Grade", str(grade)],
        ["Generated (UTC)", ts],
    ]
    t = Table(meta, colWidths=[1.6 * inch, 4.4 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("Audit Anchors", h2))
    story.append(Paragraph(f"Replay Hash (SHA-256):<br/>{replay_hash}", mono))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(f"Signed Evaluation Hash:<br/>{signed_hash}", mono))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(f"Examiner Signature ID: {examiner}", styles["Normal"]))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Evidence Summary", h2))
    evidence_count = 0
    if isinstance(bundle.evidence, list):
        for g in bundle.evidence:
            if isinstance(g, dict):
                evidence_count += len(g.get("nodes") or g.get("evidence_nodes") or [])
    story.append(Paragraph(f"Evidence nodes: {evidence_count}", styles["Normal"]))
    story.append(Paragraph(f"Screenshots: {len(bundle.screenshots)}", styles["Normal"]))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Integrity Status", h2))
    story.append(Paragraph(_integrity_label(bundle, report), styles["Normal"]))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Timeline Summary (gameplay)", h2))
    for line in (timeline.get("summary_lines") or [])[:12]:
        story.append(Paragraph(line.replace("<", "&lt;"), mono))
    if timeline.get("contradiction_count"):
        story.append(Paragraph(f"Contradiction markers: {timeline['contradiction_count']}", styles["Normal"]))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Confidence (weighted arbitration)", h2))
    conf = final.get("confidence")
    story.append(Paragraph(f"Graph confidence: {conf if conf is not None else '—'}", styles["Normal"]))
    story.append(Paragraph(f"Decision: {final.get('decision', '—')}", styles["Normal"]))
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph(
        "This document is a verifiable audit artifact. "
        "Verify replay_hash against uploads/replay_snapshots deterministic_hash.json. "
        "Do not treat LLM narrative as authoritative evidence.",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey),
    ))

    doc.build(story)
    return buf.getvalue()
