# جدول مطابقة تسليمات الوزارة — للعرض الإداري

**المنصة:** Institution-Scale Deterministic Evidence-Corroborated Runtime Evaluation  
**الغرض:** توضيح ما يُصحَّح تلقائياً، وما يحتاج مراجعة بشرية، وما يُنصح به للطلاب  
**تاريخ:** 2026-05-27 | **حالة الإطلاق:** Canary Active

---

## 1. الرسالة الإدارية (Executive Summary)

| البند | الوضع |
|-------|--------|
| **Replay integrity** (نفس التسليم → نفس replay hash) | ✅ مضمون مؤسسياً |
| **Runtime observation** (تشغيل + screenshots + telemetry) | ✅ للأنواع المدعومة أدناه |
| **تصحيح أكاديمي 100% تلقائي بدون إنسان** | ❌ **غير مُعدّ — by design** |
| **قرار نهائي قابل للدفاع** | ✅ عبر governance + examiner signoff |
| **هدف canary** | Runtime success **>95%** — وليس 100% |

> **الصياغة الموصى بها للوزارة:**  
> *"تقييم مؤسسي مدعوم بـ replay snapshot وevidence graph، مع signoff بشري إلزامي — وليس تصحيحاً آلياً 100%."*

---

## 2. جدول المطابقة الرئيسي

### أ) محركات الألعاب (Game Development)

| نوع التسليم | المحرك | Runtime | Evidence | Replay | مستوى الدعم | يحتاج examiner؟ | توصية للطلاب |
|-------------|--------|---------|----------|--------|-------------|-----------------|--------------|
| **Unity Windows build (.exe + _Data)** | Unity | ✅ Play session + video + screenshots | ✅ كامل | ✅ | **95% — ممتاز** | مراجعة معايير BTEC | **إلزامي: build + source** |
| **Unity source فقط (Assets/ + ProjectSettings/)** | Unity | ⚠️ Scene validation فقط | ⚠️ جزئي | ✅ | **70% — محدود** | **نعم — إلزامي** | أرفق build دائماً |
| **Godot Windows build (.exe)** | Godot | ✅ EXE smoke + screenshots | ✅ كامل | ✅ | **90% — قوي** | مراجعة معايير | build + source |
| **Godot source (project.godot)** | Godot | ⚠️ Export أو static analysis | ⚠️ جزئي–متوسط | ✅ | **75% — جيد** | **نعم إذا لا build** | build أو export preset |

#### Godot — تفصيل الموثوقية (Sub-tiers)

| الحالة | Tier | الموثوقية | Confidence |
|--------|------|-----------|------------|
| **Exported executable (.exe)** | A/B | High | runtime/export verified |
| **project.godot + scenes/scripts** | C | Medium | static inference |
| **Loose scenes/scripts بدون project** | D | Low | examiner-heavy |

| **GameMaker .exe (Windows build)** | GameMaker | ✅ EXE smoke | ✅ جيد | ✅ | **85% — جيد جداً** | مراجعة معايير | **build إلزامي** |
| **GameMaker HTML5 export** | GameMaker | ✅ Playwright fallback | ✅ جيد | ✅ | **85% — جيد جداً** | مراجعة معايير | HTML5 + source |
| **GameMaker .yyp / .yyz (source فقط)** | GameMaker | ⚠️ Artifact analysis (GML/yyp) | ⚠️ static | ✅ | **75% — مقبول** | **نعم — إلزامي** | build أو HTML5 مع source |
| **Web / HTML5 game (index.html)** | Web | ✅ Headless Playwright | ✅ كامل | ✅ | **90% — ممتاز** | مراجعة معايير | self-contained HTML5 |

### ب) الوثائق والملفات الداعمة

| نوع التسليم | المعالجة | Runtime | Evidence | مستوى الدعم | يحتاج examiner؟ |
|-------------|----------|---------|----------|-------------|-----------------|
| **Word / PDF (تقرير، documentation)** | Extraction + evidence graph | ❌ | ✅ نص + screenshots مدمجة | **80% — documentation** | **نعم** |
| **Screenshots / صور gameplay** | Visual evidence | ❌ | ✅ | **70% — visual hint** | **نعم** |
| **Video (.mp4 gameplay)** | Visual observation | ⚠️ partial | ✅ | **75%** | **نعم** |
| **ZIP mixed (code + doc + build)** | Auto-detect + inventory | حسب المحتوى | ✅ | **85%** إذا build موجود | حسب النوع |

### ج) غير مدعوم / مؤجل

| النوع | الحالة | البديل |
|-------|--------|--------|
| **Unreal Engine** | ❌ مؤجل | Unity / Godot |
| **Mobile APK فقط (بدون source)** | ⚠️ Legacy smoke | Build + documentation |
| **Multiplayer / online games** | ❌ خارج النطاق | Offline build |

---

## 3. Confidence Tier System (A–D)

| Tier | المعنى | متى يُطبَّق | Examiner signoff |
|------|--------|-------------|------------------|
| **A** | Runtime verified | Unity play / EXE smoke / Web headless | موصى — إلزامي institutionally |
| **B** | Export verified | Godot export / HTML5 build | موصى |
| **C** | Static inference | GML/yyp analysis, scene validation | **إلزامي** |
| **D** | Examiner-heavy | missing build, corrupted zip, unknown engine | **إلزامي** |

> **Product positioning:**  
> *"Evidence-based institutional assessment with mandatory human signoff."*

---

## 4. Submission Validity Policy

| الحالة | القرار | التصحيح |
|--------|--------|---------|
| Missing build | partial grading | Tier C + examiner |
| Missing source | reduced evidence | Tier A/B with flag |
| Corrupted ZIP | rejected / manual review | Tier D |
| Unsupported engine | manual review | Tier D |
| Multiple builds | primary build only | continue |
| Missing docs | governance warning | continue with flag |

**Pipeline rule:** NEVER FAIL — دائماً evidence + confidence tier + grading summary.

---

## 5. ماذا يعني كل مستوى دعم؟

| الرمز | المعنى | ماذا يحدث تقنياً |
|-------|--------|------------------|
| **95% — ممتاز** | Runtime كامل + replay + governance | تشغيل اللعبة، screenshots، telemetry، evidence bundle |
| **85–90% — قوي** | Runtime جيد مع fallback محدود | EXE/HTML5 smoke أو export |
| **75% — مقبول** | Static / artifact analysis | تحليل GML/yyp/project بدون تشغيل كامل |
| **70% — محدود** | Detection + validation فقط | scene/source validation — **لا gameplay proof** |

---

## 6. ما تضمنه المنصة vs ما لا تضمنه

### ✅ تضمنه المنصة

- **Deterministic replay snapshot** — canonical truth record
- **Evidence graph** — ربط runtime + documentation + code signals
- **Gameplay observation** — للأنواع القابلة للتشغيل
- **Governance workflow** — investigation → override → signoff → appeals
- **Audit trail** — tamper-verified hashes
- **Engine-agnostic normalization** — نفس envelope لكل المحركات

### ❌ لا تضمنه المنصة

- **100% gameplay correctness** — النظام يصرّح: *"لا تثبت gameplay correctness"*
- **100% automatic BTEC grading** — AI reasoning فقط، ليس مصدر الحقيقة
- **Source-only = full runtime** — بدون build، التحليل static
- **كل صيغ الملفات** — Unreal/multiplayer خارج النطاق

---

## 7. متطلبات التسليم الموصى بها للوزارة

### الحزمة الإلزامية (Minimum Viable Submission)

```
1. Build قابل للتشغيل (.exe أو HTML5)
2. Source code (مشروع المحرك)
3. Documentation (Word/PDF) — design + testing evidence
4. اسم الطالب + assignment ID واضح
```

### حسب المحرك

| المحرك | Build | Source | Documentation |
|--------|-------|--------|---------------|
| Unity | `.exe` + `_Data` | `Assets/` + `ProjectSettings/` | Word/PDF |
| Godot | `.exe` export | `project.godot` + scripts | Word/PDF |
| GameMaker | `.exe` أو HTML5 | `.yyp` أو `.yyz` | Word/PDF |
| Web | `index.html` self-contained | optional | Word/PDF |

---

## 8. سير العمل المؤسسي (Workflow)

```
تسليم الطالب
    ↓
Malware scan + artifact inventory
    ↓
Runtime engine (Unity/Godot/GameMaker/Web)
    ↓
Gameplay observation + evidence graph
    ↓
Replay snapshot (canonical truth — frozen)
    ↓
AI reasoning (استدلال فقط — ليس قرار)
    ↓
Examiner governance review
    ↓
Signoff + audit hash
    ↓
Appeals (snapshot-only — no re-execution)
```

---

## 9. KPIs للعرض على الإدارة (Canary)

| المؤشر | الهدف | المصدر |
|--------|-------|--------|
| Replay hash mismatch | **0** | `/api/ops/dashboard` |
| Runtime success rate | **>95%** | ops metrics |
| Dead letters | **~0** | `uploads/audit/dead_letter.jsonl` |
| Appeal reversal rate | منخفض | governance audit |
| Governance escalations | مستقر | examiner dashboard |

---

## 10. FAQ إداري

**س: هل النظام يصحح 100%؟**  
ج: لا. يوفر **تقييماً مؤسسياً قابلاً للدفاع** مع replay + evidence + signoff بشري.

**س: ماذا لو أرسل الطالب source فقط؟**  
ج: تحليل static + evidence — **examiner review إلزامي** — لا runtime كامل.

**س: أي محرك الأفضل للموثوقية؟**  
ج: Unity build > Web/HTML5 > Godot build > GameMaker build > source-only.

**س: هل appeals تعيد تشغيل اللعبة؟**  
ج: لا — appeals تراجع **replay snapshot مجمد** فقط.

---

## 11. مراجع تقنية

| المورد | المسار |
|--------|--------|
| Engine verification | `python tools/verify_engines.py` |
| Demo samples | `demos/samples/` |
| Canary runbook | `infra/runbooks/CANARY_ROLLOUT.md` |
| Marketplace overview | `infra/docs/marketplace/OVERVIEW.md` |
| Pentest pack | `infra/pentest/` |

---

*هذا المستند للعرض الإداري والتسويق المؤسسي — لا يعدّل العقود المجمدة.*
