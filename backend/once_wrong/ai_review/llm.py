"""呼叫 Gemini。

金鑰與模型都從環境變數讀（可放在專案根目錄的 .env，見 .env.example）：

- GOOGLE_API_KEY：Google Cloud / AI Studio 的 API 金鑰
- GOOGLE_GENAI_USE_VERTEXAI：設為 true 時走 Vertex AI（用 API 金鑰的 express mode）
- ONCE_WRONG_MODEL：模型名稱，預設 gemini-3.5-flash
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from once_wrong.ai_review.models import AIExplanation

DEFAULT_MODEL = "gemini-3.5-flash"


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    model_name: str

    def explain(self, system_prompt: str, user_prompt: str) -> AIExplanation: ...


@dataclass
class GeminiConfig:
    api_key: str
    model: str = DEFAULT_MODEL
    use_vertexai: bool = False
    temperature: float = 0.2

    @classmethod
    def from_env(cls) -> GeminiConfig:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMError("找不到 GOOGLE_API_KEY，請在 .env 或環境變數設定")
        return cls(
            api_key=api_key,
            model=os.environ.get("ONCE_WRONG_MODEL", DEFAULT_MODEL),
            use_vertexai=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes"),
        )


class GeminiClient:
    def __init__(self, config: GeminiConfig):
        from google import genai

        self.config = config
        self.model_name = config.model
        self._client = genai.Client(api_key=config.api_key, vertexai=config.use_vertexai)

    def explain(self, system_prompt: str, user_prompt: str) -> AIExplanation:
        from google.genai import errors, types

        try:
            response = self._client.models.generate_content(
                model=self.config.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=self.config.temperature,
                    response_mime_type="application/json",
                    response_schema=AIExplanation,
                ),
            )
        except errors.APIError as e:
            raise LLMError(f"Gemini 呼叫失敗：{e}") from e

        if isinstance(response.parsed, AIExplanation):
            return response.parsed
        try:
            return AIExplanation.model_validate_json(response.text or "")
        except ValueError as e:
            raise LLMError(f"Gemini 回傳格式不符：{response.text!r}") from e
