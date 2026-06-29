@echo off
chcp 65001 > nul
echo ========================================
echo أداة تصحيح واجبات الذكاء الاصطناعي
echo AI Assignment Grader
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python غير مثبت!
    echo ❌ Python is not installed!
    echo.
    echo الرجاء تثبيت Python من:
    echo Please install Python from:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo ✅ Python مثبت
echo.

REM Check if venv exists
if not exist ".venv" (
    echo 📦 إنشاء بيئة افتراضية...
    echo 📦 Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ❌ فشل إنشاء البيئة الافتراضية
        echo ❌ Failed to create virtual environment
        pause
        exit /b 1
    )
    echo ✅ تم إنشاء البيئة الافتراضية
    echo.
)

REM Activate venv
echo 🔄 تفعيل البيئة الافتراضية...
echo 🔄 Activating virtual environment...
call .venv\Scripts\activate.bat

REM Check if requirements are installed
echo 📚 فحص المكتبات المطلوبة...
echo 📚 Checking required libraries...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo 📥 تثبيت المكتبات المطلوبة...
    echo 📥 Installing required libraries...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ❌ فشل تثبيت المكتبات
        echo ❌ Failed to install libraries
        pause
        exit /b 1
    )
    echo ✅ تم تثبيت جميع المكتبات
    echo.
)

REM Check if .env exists
if not exist ".env" (
    echo ⚠️  ملف .env غير موجود!
    echo ⚠️  .env file not found!
    echo.
    echo 📝 إنشاء ملف .env من .env.example...
    echo 📝 Creating .env from .env.example...
    copy .env.example .env
    echo.
    echo ⚠️  الرجاء تعديل ملف .env وإضافة مفاتيح API
    echo ⚠️  Please edit .env file and add your API keys
    echo.
    echo افتح ملف .env وأضف:
    echo Open .env file and add:
    echo - GEMINI_API_KEY (مجاني / Free)
    echo - GROQ_API_KEY (مجاني / Free)
    echo - OPENAI_API_KEY (مدفوع / Paid)
    echo.
    pause
)

REM Start the application
echo.
echo ========================================
echo 🚀 تشغيل التطبيق...
echo 🚀 Starting application...
echo ========================================
echo.
echo التطبيق سيعمل على:
echo Application will run on:
echo http://localhost:5556
echo.
echo اضغط Ctrl+C لإيقاف التطبيق
echo Press Ctrl+C to stop the application
echo.
echo ========================================
echo.

python main.py

pause
