"""LLM Service Provider Layer.

Defines an abstract BaseLLMService interface and provides a production-ready
adapter for Google Gemini using the official unified google-genai SDK.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base exception for LLM provider errors."""

    pass


class RateLimitExceededError(LLMError):
    """Raised when the free-tier rate limit or daily quota is exceeded (HTTP 429)."""

    pass


class BaseLLMService(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        system_instruction: str,
    ) -> Dict[str, Any]:
        """Generate a structured response for a multi-turn conversation.

        Args:
            messages: List of turns [{"role": "user"|"model", "content": "..."}]
            system_instruction: The core prompt guiding persona and rules.

        Returns:
            Parsed dictionary matching ChatResponse fields.
        """
        pass


class GeminiLLMService(BaseLLMService):
    """Google Gemini adapter using the official google-genai SDK.

    Primary Model: gemini-2.0-flash (fast, multimodal, Arabic dialect-aware)
    Free Tier Limits: 15 RPM, 1,000,000 TPM, 1,500 RPD.
    """

    def __init__(self, api_key: str, model_name: str = "gemini-flash-lite-latest"):
        self.api_key = api_key
        self.model_name = model_name
        self._client = None

        if self.api_key and self.api_key != "your_gemini_api_key_here":
            try:
                from google import genai

                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Google GenAI client: {e}")

    @property
    def is_configured(self) -> bool:
        """Check if a valid API key is present."""
        return bool(self._client is not None and self.api_key and self.api_key != "your_gemini_api_key_here")

    def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        system_instruction: str,
    ) -> Dict[str, Any]:
        """Generate response from Gemini with JSON output format."""
        if not self.is_configured:
            # Helpful fallback when the user hasn't entered their API key yet
            return {
                "reply": "مرحباً بك في خدمة صَنعة! لم يتم ضبط مفتاح Gemini API Key في ملف .env بعد. يرجى إضافة المفتاح لبدء المحادثة.",
                "suggested_actions": ["إضافة GEMINI_API_KEY في ملف .env", "إعادة تشغيل الخادم"],
                "safety_warning": None,
                "escalate_to_technician": False,
                "hazard_level": "SAFE",
            }

        try:
            from google.genai import types
            from google.genai.errors import APIError

            # Format conversation contents for google-genai SDK
            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["content"])],
                    )
                )

            # Generate content with JSON schema expectation
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3,  # Low temperature for technical grounding
                response_mime_type="application/json",
            )

            response = self._client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

            # Parse JSON output from model
            raw_text = response.text or "{}"
            try:
                parsed = json.loads(raw_text)
                return {
                    "reply": parsed.get("reply", raw_text),
                    "suggested_actions": parsed.get("suggested_actions", []),
                    "safety_warning": parsed.get("safety_warning"),
                    "escalate_to_technician": bool(parsed.get("escalate_to_technician", False)),
                    "hazard_level": parsed.get("hazard_level", "SAFE"),
                }
            except json.JSONDecodeError:
                return {
                    "reply": raw_text,
                    "suggested_actions": [],
                    "safety_warning": None,
                    "escalate_to_technician": False,
                    "hazard_level": "SAFE",
                }

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Gemini API invocation error: {err_msg}")

            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                raise RateLimitExceededError(
                    "تم تجاوز الحد المجاني للطلبات مؤقتاً (15 طلب/دقيقة). يرجى الانتظار بضع ثوانٍ والمحاولة ثانية."
                )
            raise LLMError(f"خطأ في الاتصال بنموذج الذكاء الاصطناعي: {err_msg}")


def get_llm_service(settings: Optional[Settings] = None) -> BaseLLMService:
    """Factory to create LLM service based on application configuration."""
    cfg = settings or get_settings()

    if cfg.LLM_PROVIDER.lower() == "gemini":
        return GeminiLLMService(
            api_key=cfg.GEMINI_API_KEY,
            model_name=cfg.GEMINI_MODEL,
        )

    # Future providers (e.g. OpenAI, Groq) can be plugged in here
    raise ValueError(f"Unsupported LLM provider: {cfg.LLM_PROVIDER}")
