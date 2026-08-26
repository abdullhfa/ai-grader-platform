"""DeepSeek provider configuration and multimodal request regression tests."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import app.ai_provider as ai_provider
from app.ai_provider import AIProvider


def test_deepseek_initializes_native_openai_compatible_client(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash-vision-exp")

    provider = AIProvider("deepseek")

    assert provider.provider == "deepseek"
    assert provider.model == "deepseek-v4-flash-vision-exp"
    assert str(provider.client.base_url).rstrip("/") == "https://api.deepseek.com"


def test_deepseek_vision_uses_image_url_content_and_disables_thinking():
    provider = AIProvider.__new__(AIProvider)
    provider.provider = "deepseek"
    provider.model = "deepseek-v4-flash-vision-exp"
    provider.client = MagicMock()
    provider.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="وصف الصورة"))]
    )

    result = provider._openai_analyze_images([(b"image", "image/png")], "صف الصورة", 0.0)

    assert result == "وصف الصورة"
    params = provider.client.chat.completions.create.call_args.kwargs
    assert params["model"] == "deepseek-v4-flash-vision-exp"
    assert params["extra_body"] == {"thinking": {"type": "disabled"}}
    content = params["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "صف الصورة"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_deepseek_text_completion_disables_thinking_and_omits_seed():
    provider = AIProvider.__new__(AIProvider)
    provider.provider = "deepseek"
    provider.model = "deepseek-v4-flash-vision-exp"
    provider.client = MagicMock()
    provider.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="K"))]
    )

    result = provider.chat_completion(
        [{"role": "user", "content": "Reply K"}], max_tokens=128, seed=42
    )

    assert result == "K"
    params = provider.client.chat.completions.create.call_args.kwargs
    assert params["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "seed" not in params


def test_deepseek_models_are_used_for_basic_pro_and_vision(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash-vision-exp")
    monkeypatch.delenv("DEEPSEEK_MODEL_FAST", raising=False)
    monkeypatch.delenv("DEEPSEEK_PRO_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL_PRO", raising=False)
    monkeypatch.delenv("DEEPSEEK_VISION_MODEL", raising=False)

    assert ai_provider.resolve_grading_model("fast") == "deepseek-v4-flash-vision-exp"
    assert ai_provider.resolve_grading_model("pro") == "deepseek-v4-flash-vision-exp"
    assert ai_provider.resolve_vision_model("pro") == "deepseek-v4-flash-vision-exp"


def test_reset_provider_clears_cached_vision_provider():
    ai_provider._vision_provider_instance = MagicMock()
    ai_provider.reset_global_provider()
    assert ai_provider._vision_provider_instance is None
