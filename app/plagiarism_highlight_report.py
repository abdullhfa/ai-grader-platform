"""
Plagiarism highlight report — HTML export with color-coded matched phrases per source student.
"""
from __future__ import annotations

import difflib
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.plagiarism_boilerplate import filter_boilerplate_phrases

# Distinct highlight colors per compared student (background, border, text)
HIGHLIGHT_PALETTE: List[Tuple[str, str, str]] = [
    ("#fde68a", "#d97706", "#78350f"),
    ("#fecaca", "#dc2626", "#7f1d1d"),
    ("#bfdbfe", "#2563eb", "#1e3a8a"),
    ("#bbf7d0", "#059669", "#064e3b"),
    ("#ddd6fe", "#7c3aed", "#4c1d95"),
    ("#fbcfe8", "#db2777", "#831843"),
    ("#fed7aa", "#ea580c", "#7c2d12"),
    ("#99f6e4", "#0d9488", "#134e4a"),
    ("#fca5a5", "#b91c1c", "#450a0a"),
    ("#c4b5fd", "#6d28d9", "#3b0764"),
]

MIN_MATCH_WORDS = 3
MIN_MATCH_CHARS = 15
MIN_SIMILARITY_FOR_REPORT = 5.0
CHUNK_MIN_SCORE = 12.0


@dataclass
class SourceStyle:
    source_id: int
    source_name: str
    similarity: float
    bg: str
    border: str
    text: str


@dataclass
class PhraseMatch:
    phrase: str
    source_id: int
    source_name: str
    similarity: float
    bg: str
    border: str
    text_color: str


def _palette(idx: int) -> Tuple[str, str, str]:
    return HIGHLIGHT_PALETTE[idx % len(HIGHLIGHT_PALETTE)]


def _tokenize(text: str) -> List[str]:
    return [w for w in re.split(r"\s+", (text or "").strip()) if w]


def _word_set(text: str) -> set[str]:
    return {w.lower() for w in _tokenize(text) if len(w) > 1}


def extract_phrase_matches(
    student_text: str,
    other_text: str,
    *,
    min_words: int = MIN_MATCH_WORDS,
    min_chars: int = MIN_MATCH_CHARS,
) -> List[str]:
    words_a = _tokenize(student_text)
    words_b = _tokenize(other_text)
    if len(words_a) < min_words or len(words_b) < min_words:
        return []

    sm = difflib.SequenceMatcher(
        None,
        [w.lower() for w in words_a],
        [w.lower() for w in words_b],
        autojunk=False,
    )
    phrases: List[str] = []
    seen: set[str] = set()
    for block in sm.get_matching_blocks():
        if block.size < min_words:
            continue
        phrase = " ".join(words_a[block.a : block.a + block.size]).strip()
        if len(phrase) < min_chars:
            continue
        key = phrase.lower()
        if key in seen:
            continue
        seen.add(key)
        phrases.append(phrase)
    phrases.sort(key=len, reverse=True)
    return filter_boilerplate_phrases(phrases)[:25]


def _split_text_chunks(text: str, max_len: int = 420) -> List[Tuple[int, int, str]]:
    """Split into paragraphs/sentences for per-chunk source coloring."""
    if not text:
        return []
    chunks: List[Tuple[int, int, str]] = []
    parts = re.split(r"(\n\s*\n+)", text)
    cursor = 0
    buf = ""
    buf_start = 0
    for part in parts:
        if not part:
            continue
        if len(buf) + len(part) > max_len and buf.strip():
            chunks.append((buf_start, buf_start + len(buf), buf))
            buf = part
            buf_start = cursor
        else:
            if not buf:
                buf_start = cursor
            buf += part
        cursor += len(part)
    if buf.strip():
        chunks.append((buf_start, buf_start + len(buf), buf))
    if len(chunks) <= 1 and len(text) > max_len:
        chunks = []
        for i in range(0, len(text), max_len):
            piece = text[i : i + max_len]
            if piece.strip():
                chunks.append((i, i + len(piece), piece))
    return chunks


def _chunk_overlap_score(chunk: str, other_text: str) -> float:
    a = _word_set(chunk)
    b = _word_set(other_text)
    if not a or not b:
        return 0.0
    return (len(a & b) / len(a)) * 100.0


def _find_phrase_span(text: str, phrase: str) -> Optional[Tuple[int, int]]:
    if not phrase or not text:
        return None
    idx = text.find(phrase)
    if idx >= 0:
        return idx, idx + len(phrase)
    norm_phrase = re.sub(r"\s+", " ", phrase.strip())
    pattern = re.escape(norm_phrase).replace(r"\ ", r"\s+")
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if m:
        return m.start(), m.end()
    return None


def build_chunk_highlighted_html(
    text: str,
    comparisons: Sequence[Dict[str, Any]],
) -> str:
    """Color each paragraph by the classmate it most resembles."""
    styles: List[SourceStyle] = []
    for idx, row in enumerate(comparisons):
        sim = float(row.get("similarity") or 0)
        if sim < MIN_SIMILARITY_FOR_REPORT:
            continue
        bg, border, fg = _palette(idx)
        styles.append(
            SourceStyle(
                source_id=int(row.get("source_id") or 0),
                source_name=str(row.get("source_name") or "?"),
                similarity=sim,
                bg=bg,
                border=border,
                text=fg,
            )
        )
    if not styles:
        return html.escape(text).replace("\n", "<br>\n")

    style_by_id = {s.source_id: s for s in styles}
    comp_rows = [
        r for r in comparisons if float(r.get("similarity") or 0) >= MIN_SIMILARITY_FOR_REPORT
    ]

    parts: List[str] = []
    for _start, _end, chunk in _split_text_chunks(text):
        best_style: Optional[SourceStyle] = None
        best_score = 0.0
        for idx, row in enumerate(comp_rows):
            other_text = str(row.get("other_text") or "")
            score = _chunk_overlap_score(chunk, other_text)
            if score > best_score:
                best_score = score
                sid = int(row.get("source_id") or 0)
                best_style = style_by_id.get(sid) or SourceStyle(
                    sid,
                    str(row.get("source_name") or "?"),
                    float(row.get("similarity") or 0),
                    *_palette(idx),
                )
        chunk_html = html.escape(chunk).replace("\n", "<br>\n")
        if best_style and best_score >= CHUNK_MIN_SCORE:
            title = html.escape(
                f"تطابق {best_score:.0f}% — مقتبس/مشابه لـ: {best_style.source_name}"
            )
            parts.append(
                f'<div class="chunk-mark" style="background:{best_style.bg}; '
                f'border-right:4px solid {best_style.border}; color:{best_style.text};" '
                f'title="{title}" data-source="{html.escape(best_style.source_name)}">'
                f"{chunk_html}</div>"
            )
        else:
            parts.append(f'<div class="chunk-plain">{chunk_html}</div>')
    return "".join(parts)


def collect_phrase_matches_for_submission(
    student_text: str,
    comparisons: Sequence[Dict[str, Any]],
) -> List[PhraseMatch]:
    out: List[PhraseMatch] = []
    for idx, row in enumerate(comparisons):
        sim = float(row.get("similarity") or 0)
        if sim < MIN_SIMILARITY_FOR_REPORT:
            continue
        other_text = str(row.get("other_text") or "")
        if not other_text.strip():
            continue
        bg, border, fg = _palette(idx)
        source_name = str(row.get("source_name") or "?")
        source_id = int(row.get("source_id") or 0)
        for phrase in extract_phrase_matches(student_text, other_text):
            out.append(
                PhraseMatch(
                    phrase=phrase,
                    source_id=source_id,
                    source_name=source_name,
                    similarity=sim,
                    bg=bg,
                    border=border,
                    text_color=fg,
                )
            )
    return out


def _build_source_excerpt_cards(matches: Sequence[PhraseMatch]) -> str:
    """Grouped colored list of shared phrases per source student."""
    by_source: Dict[int, List[PhraseMatch]] = {}
    for m in matches:
        by_source.setdefault(m.source_id, []).append(m)

    if not by_source:
        return '<p class="muted">لم تُكتشف عبارات مشتركة طويلة — راجع التلوين على مستوى الفقرات أعلاه.</p>'

    cards: List[str] = []
    for sid, items in by_source.items():
        m0 = items[0]
        unique_phrases: List[str] = []
        seen: set[str] = set()
        for m in sorted(items, key=lambda x: len(x.phrase), reverse=True):
            key = m.phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_phrases.append(m.phrase)
            if len(unique_phrases) >= 8:
                break
        lis = "".join(
            f'<li><span class="phrase-pill" style="background:{m0.bg}; border:1px solid {m0.border}; '
            f'color:{m0.text_color};">{html.escape(p[:220])}{"…" if len(p) > 220 else ""}</span></li>'
            for p in unique_phrases
        )
        cards.append(
            f'<div class="source-card" style="border-color:{m0.border};">'
            f'<div class="source-head">'
            f'<span class="swatch-lg" style="background:{m0.bg}; border-color:{m0.border};"></span>'
            f"<div><b>{html.escape(m0.source_name)}</b>"
            f'<div class="sub">تشابه إجمالي {m0.similarity:.1f}% · {len(unique_phrases)} عبارة مشتركة</div></div>'
            f"</div>"
            f"<ul>{lis}</ul>"
            f"</div>"
        )
    return "".join(cards)


def generate_plagiarism_highlight_html(
    *,
    student_name: str,
    submission_id: int,
    batch_name: str,
    student_text: str,
    comparisons: Sequence[Dict[str, Any]],
    max_similarity: float = 0.0,
    suspicious_count: int = 0,
    batch_id: Optional[int] = None,
) -> str:
    matches = collect_phrase_matches_for_submission(student_text, comparisons)
    body_html = build_chunk_highlighted_html(student_text, comparisons)
    excerpt_cards = _build_source_excerpt_cards(matches)

    legend_rows = []
    seen_sources: set[int] = set()
    for idx, row in enumerate(comparisons):
        sim = float(row.get("similarity") or 0)
        if sim < MIN_SIMILARITY_FOR_REPORT:
            continue
        sid = int(row.get("source_id") or 0)
        if sid in seen_sources:
            continue
        seen_sources.add(sid)
        bg, border, _fg = _palette(idx)
        name = html.escape(str(row.get("source_name") or "?"))
        legend_rows.append(
            f'<div class="legend-item">'
            f'<span class="swatch" style="background:{bg}; border-color:{border};"></span>'
            f"<span>{name}</span>"
            f'<span class="pct">{sim:.1f}%</span>'
            f"</div>"
        )

    legend_html = (
        "".join(legend_rows)
        if legend_rows
        else '<p class="muted">لا توجد مقارنات فوق عتبة العرض.</p>'
    )
    source_count = len({m.source_id for m in matches}) or len(seen_sources)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    back_href = f"/batch-results/{batch_id}" if batch_id else f"/results/{submission_id}"

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>تقرير التشابه — {html.escape(student_name)}</title>
<style>
  body {{
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
    background: #0f172a; color: #e2e8f0; margin: 0; padding: 24px; line-height: 1.85;
  }}
  .wrap {{ max-width: 980px; margin: 0 auto; }}
  .back-link {{
    display: inline-flex; align-items: center; gap: 8px;
    color: #38bdf8; text-decoration: none; font-weight: 700;
    font-size: 0.95rem; margin-bottom: 16px;
  }}
  .back-link:hover {{ color: #7dd3fc; }}
  h1 {{ font-size: 1.45rem; margin: 0 0 8px; color: #fff; }}
  h2 {{ margin: 0 0 12px; font-size: 1.05rem; color: #fff; }}
  .meta {{ color: #94a3b8; font-size: 0.92rem; margin-bottom: 20px; }}
  .card {{
    background: #1e293b; border: 1px solid #334155; border-radius: 14px;
    padding: 18px 20px; margin-bottom: 18px;
  }}
  .stats {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }}
  .stat {{
    background: #0f172a; border: 1px solid #334155; border-radius: 10px;
    padding: 10px 14px; min-width: 140px;
  }}
  .stat b {{ display: block; color: #fff; font-size: 1.1rem; }}
  .stat span {{ color: #94a3b8; font-size: 0.82rem; }}
  .legend {{ display: grid; gap: 8px; }}
  .legend-item {{
    display: flex; align-items: center; gap: 10px;
    background: #0f172a; border-radius: 8px; padding: 8px 12px;
  }}
  .swatch, .swatch-lg {{
    border-radius: 6px; border: 2px solid; flex-shrink: 0;
  }}
  .swatch {{ width: 22px; height: 22px; }}
  .swatch-lg {{ width: 28px; height: 28px; }}
  .pct {{ margin-right: auto; color: #fbbf24; font-weight: 700; }}
  .muted {{ color: #94a3b8; }}
  .text-box {{
    background: #fff; color: #111827; border-radius: 12px;
    padding: 12px 14px; font-size: 0.98rem;
  }}
  .chunk-mark {{
    padding: 10px 12px; margin-bottom: 8px; border-radius: 8px;
    cursor: help;
  }}
  .chunk-plain {{ padding: 6px 4px; margin-bottom: 4px; color: #374151; }}
  .source-card {{
    background: #0f172a; border: 1px solid; border-radius: 12px;
    padding: 14px 16px; margin-bottom: 12px;
  }}
  .source-head {{ display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }}
  .source-head b {{ color: #fff; display: block; }}
  .source-head .sub {{ color: #94a3b8; font-size: 0.82rem; }}
  .source-card ul {{ margin: 0; padding-right: 18px; }}
  .source-card li {{ margin-bottom: 8px; }}
  .phrase-pill {{
    display: inline-block; padding: 4px 8px; border-radius: 6px;
    line-height: 1.6; font-size: 0.92rem;
  }}
  .hint {{ color: #94a3b8; font-size: 0.88rem; margin-top: 10px; }}
</style>
</head>
<body>
<div class="wrap">
  <a href="{back_href}" class="back-link">→ العودة للنتائج</a>
  <h1>تقرير التشابه والاقتباس — {html.escape(student_name)}</h1>

  <div class="card">
    <div class="stats">
      <div class="stat"><b>{max_similarity:.1f}%</b><span>أعلى تشابه مع زميل</span></div>
      <div class="stat"><b>{source_count}</b><span>زميل بلون مختلف</span></div>
      <div class="stat"><b>{suspicious_count}</b><span>مقارنات مشبوهة (≥26%)</span></div>
    </div>
    <p class="hint">كل زميل له لون ثابت في الدليل — الفقرات الملوّنة في النص، والعبارات في البطاقات أدناه.</p>
  </div>

  <div class="card">
    <h2>دليل الألوان — من أي ملف/طالب الاقتباس؟</h2>
    <div class="legend">{legend_html}</div>
  </div>

  <div class="card">
    <div class="text-box">{body_html}</div>
  </div>

  <div class="card">
    <h2>العبارات المشتركة — بطاقة لكل زميل (لون مختلف)</h2>
    {excerpt_cards}
  </div>
</div>
</body>
</html>"""


def build_comparisons_from_db(db: Any, submission: Any) -> List[Dict[str, Any]]:
    from app.models import PlagiarismCheck, Submission

    checks = (
        db.query(PlagiarismCheck)
        .filter(PlagiarismCheck.submission_id == submission.id)
        .order_by(PlagiarismCheck.similarity_percentage.desc())
        .limit(10)
        .all()
    )
    rows: List[Dict[str, Any]] = []
    for chk in checks:
        other = (
            db.query(Submission)
            .filter(Submission.id == chk.compared_submission_id)
            .first()
        )
        if not other or not other.submission_text:
            continue
        rows.append(
            {
                "source_id": other.id,
                "source_name": other.student_name,
                "similarity": float(chk.similarity_percentage or 0),
                "other_text": other.submission_text,
                "details": json.loads(chk.details_json) if chk.details_json else {},
            }
        )
    return rows
