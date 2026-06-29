

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict




WHATSAPP_SETTINGS_FILE = Path("uploads/config/whatsapp_settings.json")
DEFAULT_PHONE_FROM_ENV = os.getenv("WHATSAPP_DEFAULT_PHONE", "0786060100").strip()
FALLBACK_PHONE = "0786060100"



def normalize_whatsapp_phone(phone: str) -> str:
  
    digits_only = re.sub(r"\D", "", phone or "")

    if digits_only.startswith("00"):
        digits_only = digits_only[2:]


    if digits_only.startswith("0") and len(digits_only) == 10:
        return "962" + digits_only[1:]

    if digits_only.startswith("7") and len(digits_only) == 9:
        return "962" + digits_only

    return digits_only


def format_phone_display(phone: str) -> str:
   
    international_digits = normalize_whatsapp_phone(phone)

    if international_digits.startswith("962") and len(international_digits) == 12:
        local_number = "0" + international_digits[3:]
        return local_number

    return (phone or "").strip()


def build_default_settings() -> Dict[str, Any]:
  
    default_display = DEFAULT_PHONE_FROM_ENV or FALLBACK_PHONE
    default_international = normalize_whatsapp_phone(default_display)

    return {
        "sender_phone": format_phone_display(default_display),
        "sender_phone_e164": default_international,
    }


def ensure_whatsapp_settings_file() -> Dict[str, Any]:
  
    if WHATSAPP_SETTINGS_FILE.is_file():
        return load_settings_from_file()

    default_settings = build_default_settings()
    save_settings_to_file(default_settings)
    print(
        f" تم إنشاء ملف الإعدادات الافتراضي: {WHATSAPP_SETTINGS_FILE} "
        f"(رقم: {default_settings['sender_phone']})"
    )
    return default_settings


def load_settings_from_file() -> Dict[str, Any]:
    if not WHATSAPP_SETTINGS_FILE.is_file():
        return ensure_whatsapp_settings_file()

    try:
        raw_text = WHATSAPP_SETTINGS_FILE.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        if isinstance(data, dict):
            return data
        return build_default_settings()
    except Exception:
       
        default_settings = build_default_settings()
        save_settings_to_file(default_settings)
        return default_settings

def save_settings_to_file(data: Dict[str, Any]) -> None:

    WHATSAPP_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WHATSAPP_SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_whatsapp_sender_phone() -> str:
   
    saved_data = load_settings_from_file()
    phone_from_admin = str(saved_data.get("sender_phone", "")).strip()

    if phone_from_admin:
        return phone_from_admin

    if DEFAULT_PHONE_FROM_ENV:
        return DEFAULT_PHONE_FROM_ENV

    return FALLBACK_PHONE


def get_whatsapp_sender_phone_e164() -> str:
   
    return normalize_whatsapp_phone(get_whatsapp_sender_phone())


def set_whatsapp_sender_phone(phone: str) -> str:
   
    cleaned_phone = (phone or "").strip()

    if not cleaned_phone:
        raise ValueError("رقم الواتساب مطلوب")

    international_phone = normalize_whatsapp_phone(cleaned_phone)

    if len(international_phone) < 9:
        raise ValueError("رقم الواتساب غير صالح")

    display_phone = format_phone_display(cleaned_phone)

    settings_data = load_settings_from_file()
    settings_data["sender_phone"] = display_phone
    settings_data["sender_phone_e164"] = international_phone
    save_settings_to_file(settings_data)

    return display_phone


def get_whatsapp_settings() -> Dict[str, Any]:
    
    display_phone = get_whatsapp_sender_phone()
    international_phone = get_whatsapp_sender_phone_e164()

    return {
        "sender_phone": display_phone,
        "sender_phone_e164": international_phone,
        "env_default_phone": DEFAULT_PHONE_FROM_ENV or FALLBACK_PHONE,
        "settings_path": str(WHATSAPP_SETTINGS_FILE),
    }
