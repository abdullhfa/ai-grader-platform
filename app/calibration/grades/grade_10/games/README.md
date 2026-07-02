# Grade 10 — Games (MOE Unit 9 / Pearson Unit 8)

**الحالة:** `draft` — معايرة نشطة، غير مُجمَّدة بعد

## المراجع الرسمية

| المصدر | الملف |
|--------|--------|
| كتاب الوحدة (Pearson عربي) | مرجع داخلي المعلم |
| واجب بيرسون | `wjb-lmhmh` |
| برمجيات الوزارة | IT-Software 08-03-2025 (Level 2, Unit 9) |

## المحركات المعتمدة (وزارة التربية)

Godot · Unity · Unreal · Scratch · GameMaker

سياسة المنصة عند محرك غير معتمد: **تحذير المعلم** (`warn_teacher`) — لا يمنع التصحيح تلقائياً.

## مهام الواجب الرسمي

| المهمة | المعايير |
|--------|----------|
| 1 — التصميم | B.P3, B.P4, B.M2, B.D2 |
| 2 — النموذج الأولي والعرض | C.P5, C.P6, C.M3, C.D3 |

`C.P7` موجود في الوحدة الكاملة لكن **خارج** واجب `wjb-lmhmh`.

## قرارات المعايرة (موثَّقة)

### submission 48 — «العاب» (Batch 53)

- **الدرجة الرسمية:** U (43%) — متسقة مع Pearson
- **محرك MOE:** Scratch (متوافق)
- **محقق تصميمياً:** B.P3, B.P4؛ B.M2 achieved لكن غير awardable
- **Runtime Gate:** C.P5, C.P6, C.M3, C.D3 محجوبة — لا فيديو/playtest/تشغيل موثّق
- **الملفات:** `.sb3`, `docx`, `pptx` — كافية للتصميم، غير كافية للتشغيل
- **Phase 2A-fix:** أعمدة Evidence Map «موجود/ناقص» تعمل عبر `evidence_found_ar`

### Ahmad Bakr — Godot (معايرة 2026-06-29) ✅ UI مُتحقق

- **المنصة:** submission **50** (batch 55) — رفع zip عبر `batch-grade/3`
- **الدرجة الرسمية:** U — متسقة مع Gate والعاب
- **محرك MOE:** Godot (متوافق)
- **UI:** B.P3/B.P4 محققة؛ C.P5/C.P6/C.M3/C.D3 محجوبة رغم تغطية 75%/50%/67%
- **L4:** تشغيل آلي + لقطات منصة — **لا تثبت gameplay**؛ Gate يمنع المنح
- **Word/PDF:** تقرير يشرح U؛ أُضيفت فقرة «ملاحظة معايير التشغيل» في Word

### GAME B&C — Unity + GameMaker + Godot (معايرة 2026-06-29)

- **المصدر:** `uploads/تجربة/GAME B&C` — **غير مرفوع بعد** على السيرفر/DB (مجلد مركّب لعدة طلاب)
- **الدرجة الرسمية:** U — متسقة مع Gate
- **محركات مكتشفة:** Unity (build عالي الثقة) + GameMaker (28 `.yyp`) + Godot (`project.godot`)
- **كلها ضمن قائمة الوزارة** — لا تحذير `non_compliant`
- **Gate:** نفس الحجب على معايير التشغيل؛ فيديوهات متعددة لكن غير مُحلَّلة (`detected_not_analyzed`)

### تقرير المعايرة

`reports/calibration_2026-06-29.json` — تشغيل:

```bash
python scripts/run_unit9_calibration.py --include-baseline-48 --sample "Ahmad Bakr" --sample "GAME B"
```

## قاعدة ذهبية (لا تُخالَف)

> وجود `.sb3` / `.exe` / مستندات **لا يعادل** تحقيق C.P5/C.P6/C.M3/C.D3.  
> القرار النهائي للتشغيل = **Runtime Gate** وليس Gemini.

## قائمة التجميد (Freeze Checklist)

| # | الشرط | الحالة |
|---|--------|--------|
| 1 | `evidence_found_ar` / `evidence_missing_ar` في Evidence Map | ✅ |
| 2 | Gate يحجب P5/P6/M3/D3 بدون runtime | ✅ |
| 3 | Governance تراكمي (M/D لا تُمنح بدون Pass) | ✅ |
| 4 | Gemini لا يمنح معايير التشغيل وحده | ✅ |
| 5 | المحركات الخمسة قابلة للكشف | ⚠️ 4/5 (Scratch, Godot, Unity, GameMaker — Unreal بانتظار عينة) |
| 6 | ≥ 3 طلبة حقيقية مُعايرة | ✅ (3/3 — تقرير 2026-06-29) |
| 7 | README موثّق | ✅ |

**للتجميد:** أكمل صفوف 5–6 ثم ضع في `spec.json`:

```json
"status": "frozen",
"frozen_at": "YYYY-MM-DD",
"calibration": { "status": "frozen" }
```

ولا تُضف `programming/` إلى `INDEX.json` قبل ذلك.

## الملفات

- `spec.json` — SSOT للمعايير والأدلة والـ Gate (بيانات فقط)
- المحرك المشترك — `app/runtime_evidence_gate.py`, `app/evidence_map.py`, …
