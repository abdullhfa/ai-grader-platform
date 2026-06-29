# سياسة التسليم الجاهز للتشغيل (Runtime-Ready Submission Policy)

**الإصدار:** v1  
**الحالة:** سارية للـ pilot — BTEC Game Development Unit 8

---

## المبدأ

> **Presence ≠ Authority**  
> وجود الكود أو الصور **لا يعادل** تحقيق معايير التشغيل (C.P5 / C.P6).

---

## يجب تسليم (إلزامي لمعايير Runtime)

| النوع | الصيغ | ملاحظة |
|-------|-------|--------|
| Windows build | `.exe` | مع ملفات `_Data` إن وُجدت (Unity) |
| Godot export | `.exe` + `.pck` | **ليس** مجلد `.gd` فقط |
| Android | `.apk` أو `.aab` | build موقّع أو debug واضح |
| Web | `index.html` + assets | قابل للفتح محلياً |

---

## لا يُعتبر تسليماً كافياً وحده

- مجلدات `.gd` / `.cs` بدون export
- screenshots فقط
- فيديو بدون build
- مجلدات Library / Temp / .godot
- drivers أو ملفات نظام (.exe غير لعبة)

---

## هيكل الأرchive المفضل

```
StudentName/
  ├── Report.docx أو .pdf
  ├── GameBuild.exe          ← مطلوب لـ C.P5/C.P6
  ├── GameBuild.pck          ← Godot
  └── Source/                ← اختياري كدعم
```

أو **ZIP واحد** يحتوي مجلدات منفصلة لكل طالب.

---

## ما يحدث عند التسليم source-only

| النظام | السلوك |
|--------|--------|
| التصحيح الأكاديمي | ✅ يستمر (كود، تقارير، معايير أخرى) |
| Runtime sandbox | ⏭️ يُتخطى — `no_runnable_artifacts` |
| C.P5 / C.P6 | ❌ **لا Achieved** بدون authority chain |

هذا **سلوك صحيح** — وليس خطأ بالنظام.

---

## مراجع تقنية

- تقرير التغطية: `app/calibration/reports/closure/runtime_coverage_dashboard.json`
- Batch #5: 22/25 source-only — متوقع قبل هذه السياسة

---

**اعتماد pilot:** PENDING — المعلّم / الإدارة / الجودة
