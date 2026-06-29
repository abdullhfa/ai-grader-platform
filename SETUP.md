# دليل النشر — BTEC IT Auto-Grader

## ⚠️ قبل النشر — قراءة إجبارية

النسخة السابقة من المشروع كانت تحتوي على مفاتيح API مسرَّبة داخل ملف `.env` المُرفق في الـ zip:
- `GROQ_API_KEY` (gsk_2hL...)
- `OPENROUTER_API_KEY` (sk-or-v1-604e...)
- `PPLX_API_KEY` (pplx-Ohys...)
- `GOOGLE_CLIENT_SECRET` (GOCSPX-a-Fv...)

**اعتبر هذه المفاتيح مكشوفة وأبطلها فوراً** عبر لوحات التحكم في:
- https://console.groq.com
- https://openrouter.ai/keys
- https://perplexity.ai
- https://console.cloud.google.com (لمفاتيح OAuth)

ثم أنشئ مفاتيح جديدة وضعها فقط في ملف `.env` الجديد (الذي **لن يُرفع** بفضل `.gitignore` المرفق).

---

## الخطوة 1: متطلبات النظام

| المتطلب | الإصدار الموصى به |
|---|---|
| Python | 3.11 أو 3.12 (تجنّب 3.14 — beta) |
| نظام التشغيل | Linux Ubuntu 22.04+ / Windows 10+ |
| الذاكرة (RAM) | 2 جيجابايت كحد أدنى |
| مساحة التخزين | 5 جيجابايت |
| اتصال إنترنت | للوصول إلى Gemini API |

## الخطوة 2: الحصول على مفتاح Gemini API

1. ادخل على https://aistudio.google.com/app/apikey
2. اضغط على "Create API Key"
3. اختر مشروع Google Cloud أو أنشئ واحداً جديداً
4. انسخ المفتاح (يبدأ بـ `AIzaSy...`)
5. **خطة Gemini API المجانية تكفي للتجريب** — للإنتاج بحجم كبير، فعّل الفوترة

## الخطوة 3: تجهيز ملف `.env`

```bash
cp .env.example .env
nano .env   # أو vim أو أي محرر
```

عدّل القيم التالية كحد أدنى:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy_ضع_مفتاحك_الحقيقي_هنا
GEMINI_MODEL=gemini-2.5-pro
DISABLE_OLLAMA_FALLBACK=true
SECRET_KEY=ضع_سلسلة_عشوائية_طويلة_هنا
```

لتوليد `SECRET_KEY` آمن:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

## الخطوة 4: تثبيت الحزم

```bash
python3 -m venv .venv
source .venv/bin/activate          # Linux/Mac
# .venv\Scripts\activate.bat       # Windows
pip install -r requirements.txt
```

## الخطوة 5: التحقق من القوالب

تأكد أن الملفين موجودان في `uploads/templates/`:

```bash
ls "uploads/templates/"
# يجب أن تظهر:
#   Evidance - IT.docx
#   نموذج ربط أدلة المتعلم بأهداف التعلّم.docx
```

إذا كان أحدهما مفقوداً يمكنك إعادة توليد قالب LA الافتراضي:
```bash
python3 scripts/build_la_template.py
```

## الخطوة 6: التشغيل والاختبار

```bash
python3 main.py
```

سيظهر التطبيق على: http://localhost:5556

**اختبار جاهزية النشر — `curl http://localhost:5556/health`**

يجب أن يُرجع:
```json
{
  "status": "ok",
  "checks": {
    "ai_provider": {"ok": true, "provider_in_use": "gemini", "model": "gemini-2.5-pro"},
    "templates": {"ok": true, ...},
    "database": {"ok": true}
  }
}
```

إن كان أي شيء `"ok": false`، النظام **ليس** جاهزاً للنشر بعد. أصلِح الخطأ المُحدَّد في الـ response ثم أعد الاختبار.

---

## التغطية الفعلية لأنواع الملفات

### ✅ تُقرأ بالكامل وتُحلَّل
- Word (.docx)
- PDF
- Excel (.xlsx)
- **PowerPoint (.pptx) — جديد في هذه النسخة!**
- Python, C#, JavaScript, Java, HTML, CSS، أي كود نصي (50+ امتداداً)
- Godot (.gd), GameMaker (.gml), Unity scripts (.cs)
- Scratch (.sb3)
- الصور المضمَّنة داخل Word/PDF/PowerPoint (عبر Gemini Vision)
- Jupyter Notebooks (.ipynb)

### ⚠️ تُسجَّل كـ "ملف موجود" فقط — بدون قراءة محتوى
هذه أنواع ثنائية مغلقة المصدر لا يمكن قراءتها بدون أدوات خاصة:

- **Packet Tracer (.pkt, .pka)** — صيغة Cisco مشفّرة
- **Unity scenes (.unity, .prefab)** — YAML ثنائي
- **Unreal (.uasset, .umap)** — ثنائي
- **الفيديو (.mp4, .avi, .mov)** — يُستخرج Metadata فقط
- **الصوت (.mp3, .wav)** — Metadata فقط

**التوصية:** اطلب من الطلاب أن يُوثِّقوا عملهم في هذه الأدوات داخل وثيقة Word مع لقطات شاشة. النظام سيقيِّم الـ Word والصور المضمَّنة فيه.

---

## مشاكل شائعة وحلولها

### ❌ "GEMINI_API_KEY not found in environment"
**السبب:** ملف `.env` فارغ أو لم يُقرأ.
**الحل:** تأكد أن `.env` موجود في نفس مجلد `main.py`، وأن `GEMINI_API_KEY=AIzaSy...` بدون أقواس أو علامات اقتباس.

### ❌ "Connection refused" عند استخدام Gemini
**السبب:** الـ firewall يحجب `generativelanguage.googleapis.com`.
**الحل:** افتح المنفذ 443 outbound لهذا الـ domain، أو استخدم proxy.

### ❌ "Failed to initialize any AI provider"
**السبب:** لا يوجد مفتاح API صالح في `.env`.
**الحل:** ضع مفتاح Gemini أو OpenRouter صحيح. لا تعتمد على Ollama في الإنتاج.

### ❌ تقارير Evidence تُرجع 400
**السبب:** قوالب Word مفقودة.
**الحل:**
```bash
python3 scripts/build_la_template.py
cp "app/templates/Evidance - IT.docx" "uploads/templates/"
```

### ⚠️ التصحيح بطيء جداً
**السبب:** Gemini Pro نموذج كبير. للسرعة استخدم:
```env
GEMINI_MODEL=gemini-2.5-flash
```

---

## النشر على خدمة استضافة

### Linux Server (Ubuntu)
```bash
# 1. ركّب Python و pip
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip

# 2. انسخ المشروع
git clone <your-repo> /opt/ai-grader
cd /opt/ai-grader

# 3. أعد ملف .env (لا تنسخه من نسخة محلية مكشوفة!)
nano .env

# 4. ركّب الـ dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 5. ركّب systemd service
sudo nano /etc/systemd/system/ai-grader.service
```

محتوى الـ service:
```ini
[Unit]
Description=BTEC IT Auto-Grader
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/ai-grader
EnvironmentFile=/opt/ai-grader/.env
ExecStart=/opt/ai-grader/.venv/bin/python3 main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-grader
sudo systemctl start ai-grader
sudo systemctl status ai-grader

# تحقق من /health
curl http://localhost:5556/health
```

### Nginx Reverse Proxy
```nginx
server {
    listen 443 ssl;
    server_name grader.example.com;

    ssl_certificate /etc/letsencrypt/live/grader.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/grader.example.com/privkey.pem;

    client_max_body_size 100M;   # لرفع ملفات الطلاب

    location / {
        proxy_pass http://127.0.0.1:5556;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;  # التصحيح قد يستغرق وقتاً
    }

    location /health {
        proxy_pass http://127.0.0.1:5556/health;
        access_log off;
    }
}
```

### Cron للنسخ الاحتياطي
```cron
# نسخة احتياطية يومية من قاعدة البيانات
0 2 * * * /usr/bin/sqlite3 /opt/ai-grader/ai_grader.db ".backup '/backup/ai_grader_$(date +\%F).db'"
```

---

## التحقق النهائي قبل الإعلان

```bash
# 1. /health يُرجع 200 ok
curl -s http://your-domain.com/health | jq .

# 2. التصحيح يعمل لطالب تجريبي (ارفع ملف Word واختبر)

# 3. تقارير Evidence تُولَّد بدون أخطاء

# 4. لا توجد مفاتيح API في الـ logs
grep -i "AIzaSy\|sk-or-v1\|gsk_" /var/log/ai-grader.log
# يجب أن يُرجع نتيجة فارغة
```

---

*أُنشئ هذا الملف في 15 أيار/مايو 2026.*
