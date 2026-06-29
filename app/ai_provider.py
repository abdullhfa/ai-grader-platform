"""
AI providers: Google Gemini (primary), OpenRouter (cloud fallback), Ollama (local dev).

Production deployment:
    AI_PROVIDER=gemini             ← recommended (cheapest + best for BTEC)
    GEMINI_API_KEY=AIzaSy...       ← from https://aistudio.google.com/app/apikey
    GEMINI_MODEL=gemini-2.5-pro
    DISABLE_OLLAMA_FALLBACK=true   ← MUST be true on cloud hosting

Cloud fallback option (when GEMINI quota hits):
    AI_PROVIDER=openrouter
    OPENROUTER_API_KEY=sk-or-v1-...
    OPENROUTER_MODEL=google/gemini-2.5-pro

Local dev fallback (Ollama):
    AI_PROVIDER=ollama
    OLLAMA_BASE_URL=http://localhost:11434/v1
"""
import base64
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv  # type: ignore

load_dotenv(override=True)

VISION_BATCH_SIZE = 5
OLLAMA_VISION_BATCH_SIZE = 2


def _vision_batch_size(provider: str) -> int:
    if (provider or "").strip().lower() != "ollama":
        return VISION_BATCH_SIZE
    raw = (os.getenv("OLLAMA_VISION_BATCH_SIZE") or str(OLLAMA_VISION_BATCH_SIZE)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = OLLAMA_VISION_BATCH_SIZE
    return max(1, min(n, VISION_BATCH_SIZE))


def ollama_model_supports_vision(model: str) -> bool:
    """Heuristic: local Ollama tags with -vl / llava / gemma4 support image input."""
    m = (model or "").strip().lower()
    if not m:
        return False
    vision_markers = ("-vl", ":vl", "llava", "bakllava", "moondream", "gemma4", "minicpm-v")
    return any(marker in m for marker in vision_markers)


def ensure_ollama_ready_for_grading() -> None:
    """Fail fast with a clear message when AI_PROVIDER=ollama but the daemon is down."""
    if _normalize_provider(os.getenv("AI_PROVIDER", "gemini")) != "ollama":
        return
    import urllib.error
    import urllib.request

    base = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434/v1").strip()
    ping_url = base.replace("/v1", "").rstrip("/") + "/api/tags"
    last_exc: Optional[Exception] = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(ping_url, timeout=8) as resp:
                if resp.status >= 400:
                    raise ConnectionError(f"Ollama HTTP {resp.status}")
            return
        except Exception as exc:
            last_exc = exc
            if attempt < 5:
                if attempt == 0:
                    try:
                        import subprocess

                        subprocess.run(
                            ["ollama", "list"],
                            capture_output=True,
                            timeout=15,
                            check=False,
                        )
                    except Exception:
                        pass
                time.sleep(5)
                continue
    model = (os.getenv("OLLAMA_MODEL") or "deepseek-coder").strip()
    raise ConnectionError(
        "فشل الاتصال بـ Ollama — شغّل تطبيق Ollama من شريط المهام ثم نفّذ: "
        f"ollama run {model}"
    ) from last_exc


def merge_vision_lane_results(
    word_result: Dict[str, Any],
    video_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge independent Vision lanes (DOCX embedded vs video keyframes).
    Each lane keeps its own batch metadata for audit.
    """
    word = word_result or {}
    video = video_result or {}
    if not video.get("vision_attempted"):
        out = dict(word)
        out["vision_lanes"] = [{"lane": "docx_embedded", **{k: word.get(k) for k in (
            "images_submitted", "images_analyzed", "vision_attempted", "vision_completed", "vision_error"
        )}}]
        batches = list(word.get("vision_batches") or [])
        for b in batches:
            if isinstance(b, dict):
                b = dict(b)
                b.setdefault("lane", "docx_embedded")
        out["vision_batches"] = batches
        return out

    word_sub = int(word.get("images_submitted") or 0)
    word_an = int(word.get("images_analyzed") or 0)
    vid_sub = int(video.get("images_submitted") or 0)
    vid_an = int(video.get("images_analyzed") or 0)
    submitted = word_sub + vid_sub
    analyzed = word_an + vid_an
    parts = [str(word.get("text") or "").strip(), str(video.get("text") or "").strip()]
    merged_text = "\n\n".join(p for p in parts if p)
    attempted = bool(word.get("vision_attempted")) or bool(video.get("vision_attempted"))
    completed = bool(merged_text.strip()) and analyzed > 0

    batches: List[Dict[str, Any]] = []
    for b in word.get("vision_batches") or []:
        if isinstance(b, dict):
            row = dict(b)
            row["lane"] = "docx_embedded"
            batches.append(row)
    for b in video.get("vision_batches") or []:
        if isinstance(b, dict):
            row = dict(b)
            row["lane"] = "video_keyframe"
            batches.append(row)

    errors = [str(word.get("vision_error") or ""), str(video.get("vision_error") or "")]
    last_err = next((e for e in errors if e), "")

    return {
        "text": merged_text,
        "images_submitted": submitted,
        "images_analyzed": analyzed if completed else word_an + vid_an,
        "vision_attempted": attempted,
        "vision_completed": completed,
        "vision_error": "" if completed else last_err,
        "vision_batches": batches,
        "vision_lanes": [
            {
                "lane": "docx_embedded",
                "images_submitted": word_sub,
                "images_analyzed": word_an,
                "vision_attempted": bool(word.get("vision_attempted")),
                "vision_completed": bool(word.get("vision_completed")),
                "vision_error": str(word.get("vision_error") or ""),
            },
            {
                "lane": "video_keyframe",
                "images_submitted": vid_sub,
                "images_analyzed": vid_an,
                "vision_attempted": bool(video.get("vision_attempted")),
                "vision_completed": bool(video.get("vision_completed")),
                "vision_error": str(video.get("vision_error") or ""),
            },
        ],
    }


class EmptyVisionResponse(Exception):
    """Vision model returned no usable text (None/blank content)."""

    def __init__(self, code: str = "empty_vision_response") -> None:
        self.code = code
        super().__init__(code)

# Whitelist of providers that the code actually knows how to talk to.
# Anything not in here is mapped to "gemini" (the safest default).
_ALLOWED = frozenset({"gemini", "openrouter", "ollama"})


def _normalize_provider(name: Optional[str]) -> str:
    p = (name or "gemini").strip().lower()
    return p if p in _ALLOWED else "gemini"


def _ollama_fallback_enabled() -> bool:
    """Ollama is a local-dev fallback. Disable explicitly in production."""
    return os.getenv("DISABLE_OLLAMA_FALLBACK", "false").strip().lower() not in ("true", "1", "yes")


def _strict_primary_provider() -> Optional[str]:
    """When AI_PROVIDER is set in .env, use only that provider (no silent Gemini fallback)."""
    raw = (os.getenv("AI_PROVIDER") or "").strip().lower()
    if raw in _ALLOWED:
        return raw
    return None


def _gemini_output_token_floor() -> int:
    """Gemini 2.5 Flash uses internal thinking tokens; tiny max_tokens yields empty content."""
    try:
        return max(32, int(os.getenv("GEMINI_MIN_OUTPUT_TOKENS", "128")))
    except ValueError:
        return 128


def _effective_max_tokens(provider: str, model: Optional[str], max_tokens: Optional[int]) -> Optional[int]:
    if not max_tokens:
        return None
    if provider == "gemini":
        model_l = (model or "").lower()
        if "2.5" in model_l or "flash" in model_l:
            return max(max_tokens, _gemini_output_token_floor())
    return max_tokens


def _gemini_api_key_looks_valid() -> bool:
    """Google AI Studio keys start with AIza; skip gemini if a wrong key is set."""
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    return bool(key) and key.startswith("AIza")


def _looks_like_google_api_error_json(obj: Any) -> bool:
    """True if parsed JSON is a Google-style API error object, not our teacher guide."""
    if not isinstance(obj, dict) or "error" not in obj:
        return False
    err = obj.get("error")
    if isinstance(err, dict):
        return bool(
            err.get("code") or err.get("status") or err.get("message") or err.get("details")
        )
    return isinstance(err, str)


class AIProvider:
    """Gemini (Google), OpenRouter, or Ollama, all via OpenAI-compatible client."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = _normalize_provider(
            provider or os.getenv("AI_PROVIDER", "gemini")
        )
        self._model_override = (model or "").strip() or None
        self.client: Any = None
        self.model: Optional[str] = None
        self._initialize_provider()

    def _initialize_provider(self) -> None:
        if self.provider == "gemini":
            self._init_gemini()
        elif self.provider == "openrouter":
            self._init_openrouter()
        elif self.provider == "ollama":
            self._init_ollama()
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _init_gemini(self) -> None:
        from openai import OpenAI  # type: ignore

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not found in environment. "
                "Get a free key from https://aistudio.google.com/app/apikey"
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        self.model = self._model_override or os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
        print(f"[OK] Initialized Gemini (OpenAI-compat) with model: {self.model}")

    def _init_openrouter(self) -> None:
        """OpenRouter is a unified gateway. Useful for routing to Gemini Pro via a single API key."""
        from openai import OpenAI  # type: ignore

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not found in environment. "
                "Get one from https://openrouter.ai/keys"
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        # Default to Gemini 2.5 Pro via OpenRouter to match the rest of the system's BTEC prompts.
        self.model = self._model_override or os.getenv(
            "OPENROUTER_MODEL", "google/gemini-2.5-pro"
        )
        print(f"[OK] Initialized OpenRouter with model: {self.model}")

    def _init_ollama(self) -> None:
        from openai import OpenAI  # type: ignore

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.client = OpenAI(api_key="ollama", base_url=base_url)
        raw_model = os.getenv("OLLAMA_MODEL", "deepseek-coder").strip()
        # Names like deepseek-v3:671b are OpenRouter slugs, not local Ollama tags.
        if raw_model.startswith("deepseek-v3:") or ":671b" in raw_model:
            print(
                f"⚠️ OLLAMA_MODEL={raw_model!r} is not a local Ollama tag; "
                "using deepseek-coder instead. Run: ollama pull deepseek-coder"
            )
            raw_model = "deepseek-coder"
        self.model = self._model_override or raw_model
        print(f"[OK] Initialized Ollama with model: {self.model} at {base_url}")

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
        seed: Optional[int] = 42,
    ) -> str:
        # Try this provider directly. The global fallback chain is handled at a higher level
        # (get_fallback_provider). We don't auto-cascade to Ollama from inside Gemini's call,
        # because in cloud deployments Ollama isn't there — that just causes confusing errors.
        return self._openai_style_completion(
            messages, temperature, max_tokens, response_format, seed
        )

    def _openai_style_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        response_format: Optional[Dict],
        seed: Optional[int] = None,
    ) -> str:
        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": 1,
        }
        if max_tokens:
            params["max_tokens"] = _effective_max_tokens(self.provider, self.model, max_tokens)  # type: ignore
        # Gemini's OpenAI-compat endpoint doesn't accept these.
        if seed is not None and self.provider not in ["gemini"]:
            params["seed"] = seed  # type: ignore
        if response_format and self.provider not in ["gemini"]:
            params["response_format"] = response_format  # type: ignore

        if self.provider == "ollama":
            last_exc: Optional[Exception] = None
            response = None
            for attempt in range(3):
                try:
                    response = self.client.chat.completions.create(  # type: ignore
                        timeout=600,
                        **params,
                    )
                    break
                except Exception as exc:
                    last_exc = exc
                    err = str(exc).lower()
                    retryable = any(
                        token in err
                        for token in (
                            "500",
                            "connection",
                            "forcibly closed",
                            "timeout",
                            "eof",
                            "reset",
                        )
                    )
                    if attempt < 2 and retryable:
                        print(
                            f"⚠️ [OLLAMA] retry {attempt + 1}/2 after: {exc}"
                        )
                        time.sleep(2 * (attempt + 1))
                        continue
                    raise
            else:
                if last_exc:
                    raise last_exc
            if response is None:
                raise RuntimeError("Ollama returned no response")
        else:
            response = self.client.chat.completions.create(**params)  # type: ignore

        msg = response.choices[0].message
        content = msg.content
        if content is None or not str(content).strip():
            reasoning = getattr(msg, "reasoning", None) or ""
            finish = getattr(response.choices[0], "finish_reason", None)
            if (
                self.provider == "gemini"
                and finish == "length"
                and max_tokens
                and max_tokens < _gemini_output_token_floor() * 2
            ):
                raised = _effective_max_tokens(self.provider, self.model, max(max_tokens * 4, 256))
                if raised and raised != max_tokens:
                    return self._openai_style_completion(
                        messages, temperature, raised, response_format, seed
                    )
            if reasoning and str(reasoning).strip():
                raise ValueError(
                    f"Model {self.model!r} returned reasoning only (no answer text). "
                    "Try OPENROUTER_MODEL=google/gemini-2.5-flash or increase max_tokens."
                )
            raise ValueError(
                f"Empty response from {self.provider} model {self.model!r}"
            )
        return str(content)

    def _vision_prompt(self, context: str = "", evidence_mode: Optional[str] = None) -> str:
        prompt_neutral = """أنت مساعد تقييم BTEC. صِف بدقة ما تراه في كل صورة/لقطة شاشة.

ركّز على:
1. إذا كانت لقطة شاشة لبيئة تطوير (Visual Studio, VS Code, إلخ): اذكر اسم الملف المفتوح، الكود الظاهر، أي أخطاء أو تحذيرات
2. إذا كانت لقطة شاشة لتطبيق يعمل: صِف الواجهة، عناصر التحكم، البيانات المعروضة، نتائج التنفيذ
3. إذا كانت مخطط انسيابي (Flowchart): اذكر الخطوات والتفرعات بالترتيب
4. إذا كانت رسم بياني/جدول: انسخ البيانات الظاهرة
5. إذا كانت لقطة شاشة لنتائج اختبار: اذكر حالات الاختبار ونتائجها (ناجح/فاشل)
6. إذا كانت تصميم واجهة مستخدم (Wireframe/Mockup): صِف العناصر والتخطيط
7. إذا كانت استبانة أو نموذج: انسخ الأسئلة والإجابات

لكل صورة، اكتب:
[صورة X]: وصف تفصيلي لمحتوى الصورة

لا تضف تقييم أو حكم — فقط صِف المحتوى بدقة."""

        prompt_game = """أنت مراجع أدلة بصرية لواجب تطوير لعبة (BTEC). مهمتك: وصف دقيق + إشارات موضوعية لقوة أو ضعف الدليل كـ**لقطة شاشة للتنفيذ** (لا تمنح درجات؛ اذكر الملاحظات فقط).

لكل صورة بالترتيب استخدم القالب التالي (بالعربية):

[صورة N]:
- الوصف: ما يظهر حرفياً (واجهة لعبة، محرر Unity/Godot/GameMaker، كود، جدول اختبار، رسوم عامة، إلخ).
- السياق التقني: هل تبدو من لعبة قيد التشغيل (build) أم من محرر/مشروع أم صورة تسويق/ويب/شعار فقط؟
- عناصر اللعب الظاهرة: حركة/تصادم/نقاط/حيوات/مؤقت/مستويات صعوبة/واجهة/قائمة — اذكر فقط ما يُرى صراحة؛ لا تفترض غير الظاهر.
- أدلة الاختبار/التغذية الراجعة/التحسين: هل تظهر نتائج اختبار، تعليقات مستخدمين، مقاييس قبل/بعد، أو مجرد نص يدّعي ذلك؟
- تناقضات محتملة: إن وُجد نص داخل الصورة (عنوان لعبة، إصدار، اسم مشروع) يذكر تفاصيل تتعارض مع بقية الصور أو مع سياق الواجب — اذكرها بحياد.
- جودة الدليل كـإثبات: هل اللقطة تُثبت تنفيذ المطلوب أم عامة/غامضة/تشبه صورة درس/متجر/بحث جوجل/استوك؟ صنّف بـ: قوي / متوسط / ضعيف كدليل تنفيذي — مع سبب قصير من المرئيات فقط.

لا تستخدم حسن النية: ما لا يظهر في الصورة لا تذكره كحقيقة."""

        prompt = prompt_game if (evidence_mode or "").lower() == "game" else prompt_neutral
        if context:
            prompt += f"\n\nسياق الواجب: {context}"
        return prompt

    def analyze_images(
        self,
        images: List[Tuple[bytes, str]],
        context: str = "",
        temperature: float = 0.0,
        evidence_mode: Optional[str] = None,
    ) -> str:
        if not images:
            return ""
        prompt = self._vision_prompt(context, evidence_mode)
        try:
            return self._openai_analyze_images(images, prompt, temperature)
        except EmptyVisionResponse:
            return ""
        except Exception as e:
            print(f"⚠️ Image analysis failed on {self.provider}: {e}")
            return ""

    def analyze_images_resilient(
        self,
        images: List[Tuple[bytes, str]],
        context: str = "",
        temperature: float = 0.0,
        evidence_mode: Optional[str] = None,
        *,
        batch_size: int = 0,
    ) -> Dict[str, Any]:
        """
        Vision with retry + batch split. Returns audit metadata for visual evidence registry.
        """
        if batch_size <= 0:
            batch_size = _vision_batch_size(self.provider)
        empty: Dict[str, Any] = {
            "text": "",
            "images_submitted": 0,
            "images_analyzed": 0,
            "vision_attempted": False,
            "vision_completed": False,
            "vision_error": "",
            "vision_batches": [],
        }
        if not images:
            return empty

        from app.document_processor import filter_vision_images

        images = filter_vision_images(images)
        if not images:
            return {
                **empty,
                "vision_attempted": True,
                "vision_completed": False,
                "vision_error": "no_vision_supported_images",
            }

        base_prompt = self._vision_prompt(context, evidence_mode)
        submitted = len(images)
        batches_meta: List[Dict[str, Any]] = []

        def _run_once(batch: List[Tuple[bytes, str]], prompt: str) -> Tuple[str, Optional[str]]:
            try:
                text = self._openai_analyze_images(batch, prompt, temperature)
                return text, None
            except EmptyVisionResponse as e:
                return "", getattr(e, "code", "empty_vision_response")
            except Exception as e:
                err = str(e)
                if (
                    len(batch) > 1
                    and "unsupported mime type" in err.lower()
                ):
                    parts: List[str] = []
                    analyzed = 0
                    last_single_err = err
                    for one in batch:
                        t, e2 = _run_once([one], prompt)
                        if t.strip():
                            parts.append(t.strip())
                            analyzed += 1
                        elif e2:
                            last_single_err = e2
                    if parts:
                        return "\n\n".join(parts), None
                    return "", last_single_err
                return "", err

        def _run_with_retry(
            batch: List[Tuple[bytes, str]],
            *,
            batch_index: int,
            total_batches: int,
        ) -> Tuple[str, Optional[str]]:
            prompt = base_prompt
            if total_batches > 1:
                prompt += (
                    f"\n\n(دفعة {batch_index}/{total_batches} — "
                    f"{len(batch)} صورة/لقطة في هذه الدفعة)"
                )
            text, err = _run_once(batch, prompt)
            if text.strip():
                return text, None
            text, err2 = _run_once(batch, prompt)
            if text.strip():
                return text, None
            return "", err2 or err or "empty_vision_response"

        # Full batch first (with one retry).
        full_text, full_err = _run_with_retry(images, batch_index=1, total_batches=1)
        if full_text.strip():
            batches_meta.append(
                {"submitted": submitted, "analyzed": submitted, "error": None}
            )
            return {
                "text": full_text,
                "images_submitted": submitted,
                "images_analyzed": submitted,
                "vision_attempted": True,
                "vision_completed": True,
                "vision_error": "",
                "vision_batches": batches_meta,
            }

        # Split into smaller batches after full-batch failure.
        chunks = [
            images[i : i + batch_size] for i in range(0, len(images), batch_size)
        ]
        if len(chunks) <= 1:
            batches_meta.append(
                {"submitted": submitted, "analyzed": 0, "error": full_err or "empty_vision_response"}
            )
            return {
                "text": "",
                "images_submitted": submitted,
                "images_analyzed": 0,
                "vision_attempted": True,
                "vision_completed": False,
                "vision_error": full_err or "empty_vision_response",
                "vision_batches": batches_meta,
            }

        parts: List[str] = []
        analyzed = 0
        last_err = full_err or "empty_vision_response"
        for idx, chunk in enumerate(chunks, start=1):
            text, err = _run_with_retry(chunk, batch_index=idx, total_batches=len(chunks))
            if text.strip():
                parts.append(text.strip())
                analyzed += len(chunk)
                batches_meta.append({"submitted": len(chunk), "analyzed": len(chunk), "error": None})
            else:
                last_err = err or "empty_vision_response"
                batches_meta.append(
                    {"submitted": len(chunk), "analyzed": 0, "error": last_err}
                )

        merged = "\n\n".join(parts)
        completed = bool(merged.strip())
        return {
            "text": merged,
            "images_submitted": submitted,
            "images_analyzed": analyzed if completed else 0,
            "vision_attempted": True,
            "vision_completed": completed,
            "vision_error": "" if completed else last_err,
            "vision_batches": batches_meta,
        }

    def _openai_analyze_images(
        self,
        images: List[Tuple[bytes, str]],
        prompt: str,
        temperature: float,
    ) -> str:
        content: List[Any] = [{"type": "text", "text": prompt}]
        for image_bytes, mime_type in images:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                }
            )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            temperature=temperature,
            max_tokens=8192,
        )
        msg = response.choices[0].message
        raw = msg.content
        if raw is None or not str(raw).strip():
            reasoning = getattr(msg, "reasoning", None) or ""
            if reasoning and str(reasoning).strip():
                return str(reasoning).strip()
            finish = getattr(response.choices[0], "finish_reason", None)
            code = "empty_vision_response"
            if finish == "length":
                code = "empty_vision_response_max_tokens"
            raise EmptyVisionResponse(code)
        return str(raw).strip()


def get_ai_provider(provider: Optional[str] = None) -> AIProvider:
    """Try to initialise a single provider. Used when the caller knows what they want."""
    providers_to_try: List[str] = []
    if provider:
        providers_to_try.append(_normalize_provider(provider))
    else:
        strict = _strict_primary_provider()
        if strict:
            providers_to_try.append(strict)
        else:
            env_p = _normalize_provider(os.getenv("AI_PROVIDER", "gemini"))
            providers_to_try.append(env_p)
            # Auto-discovery only when AI_PROVIDER is unset/invalid.
            cloud_chain = ["gemini", "openrouter"]
            if _ollama_fallback_enabled():
                cloud_chain.append("ollama")
            for p in cloud_chain:
                if p not in providers_to_try:
                    providers_to_try.append(p)

    last_error: Optional[Exception] = None
    for p in providers_to_try:
        if p == "gemini" and not _gemini_api_key_looks_valid():
            print("⚠️  Skipping gemini fallback: GEMINI_API_KEY is missing or not a Google AI key (AIza…)")
            continue
        try:
            return AIProvider(p)
        except Exception as e:
            last_error = e
            print(f"⚠️  Failed to initialize {p}: {e}")
            continue
    raise Exception(
        f"Failed to initialize any AI provider. Last error: {last_error}. "
        f"Hint: set AI_PROVIDER=gemini and GEMINI_API_KEY in your .env."
    )


_global_provider: Optional[AIProvider] = None
_fallback_providers: List[str] = []
_grading_provider_cache: Dict[str, AIProvider] = {}
_vision_provider_instance: Optional[AIProvider] = None


def resolve_vision_model(grading_mode: str | None = None) -> str:
    """Model id for image analysis; may differ from text grading on local Ollama."""
    prov = _normalize_provider(os.getenv("AI_PROVIDER", "gemini"))
    if prov == "ollama":
        dedicated = (os.getenv("OLLAMA_VISION_MODEL") or "").strip()
        if dedicated:
            return dedicated
    return resolve_grading_model(grading_mode)


def get_vision_provider(grading_mode: str | None = None) -> AIProvider:
    """Provider for Vision lanes — uses OLLAMA_VISION_MODEL when set."""
    global _vision_provider_instance

    model = resolve_vision_model(grading_mode)
    if _vision_provider_instance is not None:
        if (_vision_provider_instance.model or "").strip().lower() == model.strip().lower():
            return _vision_provider_instance

    base = get_global_provider()
    if (base.model or "").strip().lower() == model.strip().lower():
        _vision_provider_instance = base
        return base

    _vision_provider_instance = AIProvider(provider=base.provider, model=model)
    print(
        f"[OK] Vision AI: {_vision_provider_instance.provider} / {_vision_provider_instance.model}"
    )
    return _vision_provider_instance


def resolve_grading_model(grading_mode: str | None) -> str:
    """Model id for BASIC (fast) vs PRO (deep); respects AI_PROVIDER."""
    from app.grading_mode_policy import is_fast_grading_mode

    fast = is_fast_grading_mode(grading_mode)
    prov = _normalize_provider(os.getenv("AI_PROVIDER", "gemini"))
    if prov == "gemini":
        if fast:
            return (
                os.getenv("GEMINI_MODEL_FAST")
                or os.getenv("GEMINI_MODEL")
                or "gemini-2.5-flash"
            ).strip()
        return (
            os.getenv("GEMINI_PRO_MODEL")
            or os.getenv("GEMINI_MODEL_PRO")
            or "gemini-2.5-pro"
        ).strip()
    if prov == "openrouter":
        if fast:
            return (
                os.getenv("OPENROUTER_MODEL_FAST")
                or os.getenv("OPENROUTER_MODEL")
                or "google/gemini-2.5-flash"
            ).strip()
        return (
            os.getenv("OPENROUTER_PRO_MODEL")
            or os.getenv("OPENROUTER_MODEL_PRO")
            or "google/gemini-2.5-pro"
        ).strip()
    return (os.getenv("OLLAMA_MODEL") or "deepseek-coder").strip()


def get_grading_provider(grading_mode: str | None) -> AIProvider:
    """Provider instance for a grading mode (BASIC=flash, PRO=reasoning model)."""
    from app.grading_mode_policy import normalize_grading_mode_choice

    key = normalize_grading_mode_choice(grading_mode)
    cached = _grading_provider_cache.get(key)
    if cached is not None:
        return cached

    base = get_global_provider()
    model = resolve_grading_model(grading_mode)
    if (base.model or "").strip().lower() == model.strip().lower():
        _grading_provider_cache[key] = base
        return base

    dedicated = AIProvider(provider=base.provider, model=model)
    _grading_provider_cache[key] = dedicated
    print(
        f"[OK] Grading AI ({key}): {dedicated.provider} / {dedicated.model}"
    )
    return dedicated


def get_global_provider() -> AIProvider:
    global _global_provider, _fallback_providers
    if _global_provider is None:
        _global_provider = get_ai_provider()
        strict = _strict_primary_provider()
        if strict:
            # Honour AI_PROVIDER=ollama|gemini|openrouter — do not fall back to Gemini silently.
            _fallback_providers = []
        else:
            chain = ["gemini", "openrouter"]
            if _ollama_fallback_enabled():
                chain.append("ollama")
            _fallback_providers = [
                p for p in chain
                if p != _global_provider.provider
                and not (p == "gemini" and not _gemini_api_key_looks_valid())
            ]
    return _global_provider


def get_fallback_provider() -> Optional[AIProvider]:
    """Try the next provider in the chain. Returns None if all fail."""
    global _global_provider, _fallback_providers
    old_name = _global_provider.provider if _global_provider else "unknown"
    while _fallback_providers:
        p = _fallback_providers.pop(0)
        if p == "gemini" and not _gemini_api_key_looks_valid():
            continue
        try:
            fallback = AIProvider(p)
            print(f"🔄 [FALLBACK] Switched from {old_name} to {p}")
            _global_provider = fallback
            return fallback
        except Exception as e:
            print(f"⚠️ [FALLBACK] {p} also failed: {e}")
            continue
    return None


def reset_global_provider() -> None:
    global _global_provider, _fallback_providers, _grading_provider_cache
    _global_provider = None
    _fallback_providers = []
    _grading_provider_cache = {}


def check_provider_health() -> Dict[str, Any]:
    """Run a tiny smoke-test call to confirm the configured provider actually works.
    Used by the /health endpoint and at startup to fail fast instead of silently."""
    info: Dict[str, Any] = {
        "provider_requested": os.getenv("AI_PROVIDER", "gemini"),
        "ollama_fallback_enabled": _ollama_fallback_enabled(),
        "ok": False,
        "provider_in_use": None,
        "model": None,
        "error": None,
    }
    try:
        prov = get_ai_provider()
        info["provider_in_use"] = prov.provider
        info["model"] = prov.model
        # Tiny smoke test — 1 short reply
        reply = prov.chat_completion(
            messages=[{"role": "user", "content": "Respond with the single character: K"}],
            temperature=0.0,
            max_tokens=128,
        )
        info["ok"] = bool(reply and len(reply.strip()) > 0)
        info["smoke_test_reply"] = (reply or "").strip()[:50]
    except Exception as e:
        info["error"] = str(e)
    return info
