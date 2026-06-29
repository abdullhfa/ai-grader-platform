

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from app.whatsapp_config import get_whatsapp_sender_phone_e164  # type: ignore

whatsapp_process: Optional[subprocess.Popen] = None

we_started_the_service = False

log_reader_thread: Optional[threading.Thread] = None


WHATSAPP_SERVICE_FOLDER = Path(__file__).resolve().parent.parent / "whatsapp_service"


WHATSAPP_SERVICE_URL = os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3001")

def is_auto_start_enabled() -> bool:

    value = os.getenv("WHATSAPP_AUTO_START", "true").strip().lower()
    return value in ("1", "true", "yes", "on")


def is_whatsapp_service_running(timeout_seconds: float = 2.0) -> bool:
  
    try:
        import httpx

        response = httpx.get(
            f"{WHATSAPP_SERVICE_URL}/health",
            timeout=timeout_seconds,
        )
        return response.status_code == 200
    except Exception:
        return False


def print_node_output(process: subprocess.Popen) -> None:
    """يقرأ مخرجات Node سطراً بسطر ويطبعها في الطرفية مع بادئة [WA]."""
    if process.stdout is None:
        return

    for raw_line in process.stdout:
        try:
            line_text = raw_line.decode("utf-8", errors="replace").rstrip()
        except Exception:
            line_text = str(raw_line)

        if line_text:
            print(f"[WA] {line_text}")


def install_npm_dependencies_if_needed() -> None:
    """يثبت حزم npm إذا لم يكن مجلد node_modules موجوداً."""
    node_modules_folder = WHATSAPP_SERVICE_FOLDER / "node_modules"

    if node_modules_folder.is_dir():
        return

    npm_command = shutil.which("npm")
    if not npm_command:
        print("[WA] npm غير موجود — لا يمكن تثبيت الحزم")
        return

    print("[WA] جاري تثبيت حزم npm...")
    subprocess.run(
        [npm_command, "install"],
        cwd=str(WHATSAPP_SERVICE_FOLDER),
        check=False,
    )


def build_process_environment() -> dict:
    """
    يجهّز متغيرات البيئة لعملية Node.

    يمرّر رقم الهاتف المتوقع حتى تتطابق جلسة QR مع الرقم الم configured.
    """
    environment = os.environ.copy()
    environment.setdefault("WA_PORT", "3001")
    environment["EXPECTED_PHONE"] = get_whatsapp_sender_phone_e164()
    return environment


# ─────────────────────────────────────────────────────────────
# دوال عامة — تُستدعى من main.py
# ─────────────────────────────────────────────────────────────

def start_whatsapp_service() -> bool:
    """
    يشغّل خدمة واتساب إن لم تكن تعمل.

    الخطوات:
    1. التحقق من التشغيل التلقائي
    2. التحقق إن كانت الخدمة شغالة مسبقاً
    3. التحقق من وجود server.js و Node.js
    4. تثبيت npm إن لزم
    5. تشغيل Node وانتظار /health حتى 30 ثانية

    يعيد True إذا أصبحت الخدمة متاحة.
    """
    global whatsapp_process, we_started_the_service, log_reader_thread

    if not is_auto_start_enabled():
        print("[WA] التشغيل التلقائي معطّل (WHATSAPP_AUTO_START=false)")
        return is_whatsapp_service_running()

    if is_whatsapp_service_running():
        print("[WA] الخدمة تعمل مسبقاً")
        return True

    server_file = WHATSAPP_SERVICE_FOLDER / "server.js"
    if not server_file.is_file():
        print(f"[WA] لم يُعثر على server.js في: {WHATSAPP_SERVICE_FOLDER}")
        return False

    node_command = shutil.which("node")
    if not node_command:
        print("[WA] Node.js غير مثبت — ثبّت Node.js لتفعيل الواتساب")
        return False

    install_npm_dependencies_if_needed()

    environment = build_process_environment()
    service_port = environment.get("WA_PORT", "3001")

    process_options = {
        "cwd": str(WHATSAPP_SERVICE_FOLDER),
        "env": environment,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
    }

    # على Windows: تشغيل بدون نافذة سوداء
    if sys.platform == "win32":
        process_options["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    try:
        whatsapp_process = subprocess.Popen(
            [node_command, "server.js"],
            **process_options,
        )
        we_started_the_service = True

        log_reader_thread = threading.Thread(
            target=print_node_output,
            args=(whatsapp_process,),
            daemon=True,
        )
        log_reader_thread.start()

        print(f"[WA] جاري تشغيل الخدمة على المنفذ {service_port}...")
    except Exception as error:
        print(f"[WA] فشل تشغيل الخدمة: {error}")
        return False

    # انتظار حتى 30 ثانية حتى تستجيب الخدمة
    maximum_wait_seconds = 30
    for second in range(maximum_wait_seconds):
        if is_whatsapp_service_running(timeout_seconds=1.5):
            print("[WA] الخدمة جاهزة")
            return True
        time.sleep(1)

    print("[WA] الخدمة بدأت لكن لم تستجب بعد — قد يظهر QR قريباً")
    return False


def stop_whatsapp_service() -> None:
    """
    يوقف خدمة Node فقط إذا كنا نحن من شغّلناها.

    لا يلمس عملية Node التي بدأها المستخدم يدوياً في طرفية منفصلة.
    """
    global whatsapp_process, we_started_the_service

    if not we_started_the_service or whatsapp_process is None:
        return

    try:
        whatsapp_process.terminate()
        whatsapp_process.wait(timeout=8)
    except Exception:
        try:
            whatsapp_process.kill()
        except Exception:
            pass
    finally:
        whatsapp_process = None
        we_started_the_service = False
        print("[WA] تم إيقاف الخدمة")


def restart_whatsapp_service() -> bool:
    """
    يعيد تشغيل الخدمة لالتقاط رقم الهاتف الجديد (EXPECTED_PHONE).

    يُستدعى بعد حفظ رقم جديد من لوحة المدير.
    """
    stop_whatsapp_service()
    time.sleep(1)
    return start_whatsapp_service()
