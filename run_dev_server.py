"""Dev server launcher — applies env overrides after .env load."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(override=True)

os.environ.setdefault("PORT", "5557")
os.environ.setdefault("PRO_FAST_PATH", "0")
os.environ.setdefault("BATCH_GRADING_WORKERS", "1")

import main  # noqa: E402 — triggers main.load_dotenv; re-apply dev overrides below

from app.ai_provider import reset_global_provider  # noqa: E402

reset_global_provider()

os.environ["WHATSAPP_AUTO_START"] = "false"

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        main.app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5557")),
        reload=os.getenv("DEBUG", "False").lower() == "true",
        timeout_keep_alive=int(os.getenv("UVICORN_TIMEOUT_KEEP_ALIVE", "300")),
    )
