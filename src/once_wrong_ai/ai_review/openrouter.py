"""透過 OpenRouter 呼叫各家模型（OpenAI 相容的 chat completions API）。

環境變數（可放在專案根目錄的 .env，見 .env.example）：

- OPENROUTER_API_KEY：OpenRouter 的 API 金鑰
- OPENROUTER_MODEL：模型 id，預設 deepseek/deepseek-v4-flash；可用的模型見 https://openrouter.ai/models
- OPENROUTER_REASONING：思考強度 low／medium／high，不設就用模型預設。思考 token 按輸出計費
- OPENROUTER_TEMPERATURE：不設就不送。推理模型（例如 openai/gpt-6-luna）不接受 temperature，
  送了會因為「只用支援全部參數的供應商」而找不到任何供應商（404）
- OPENROUTER_MAX_TOKENS：可選的正整數輸出上限；不設就沿用供應商預設

要求模型照 `AIExplanation` 的 JSON schema 回覆，並只路由到支援這個參數、而且不保留資料的供應商。
每次呼叫的 token 數和費用（美元）累計在 `usage`，評分和示範指令會印出來。
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field

import httpx

from once_wrong_ai.ai_review.llm import LLMError
from once_wrong_ai.ai_review.models import AIExplanation

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _strict_schema(schema: dict) -> dict:
    """structured outputs 的嚴格模式要求：每個物件都列出全部欄位為必填、不准多欄位、不放預設值。"""
    if isinstance(schema, dict):
        schema = {k: _strict_schema(v) for k, v in schema.items() if k != "default"}
        if schema.get("type") == "object" and "properties" in schema:
            schema["required"] = list(schema["properties"])
            schema["additionalProperties"] = False
        return schema
    if isinstance(schema, list):
        return [_strict_schema(v) for v in schema]
    return schema


RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "AIExplanation", "strict": True, "schema": _strict_schema(AIExplanation.model_json_schema())},
}


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add(self, usage: dict) -> None:
        details = usage.get("completion_tokens_details") or {}
        with self._lock:
            self.calls += 1
            self.prompt_tokens += usage.get("prompt_tokens") or 0
            self.completion_tokens += usage.get("completion_tokens") or 0
            self.reasoning_tokens += details.get("reasoning_tokens") or 0
            self.cost_usd += float(usage.get("cost") or 0)

    def summary(self) -> str:
        return (
            f"{self.calls} 次呼叫，輸入 {self.prompt_tokens:,} token、輸出 {self.completion_tokens:,} token"
            f"（其中思考 {self.reasoning_tokens:,}），費用 US${self.cost_usd:.4f}"
        )

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "promptTokens": self.prompt_tokens,
            "completionTokens": self.completion_tokens,
            "reasoningTokens": self.reasoning_tokens,
            "costUsd": round(self.cost_usd, 6),
        }


@dataclass
class OpenRouterConfig:
    api_key: str
    model: str = DEFAULT_MODEL
    temperature: float | None = None
    reasoning: str | None = None
    timeout: float = 30.0
    max_tokens: int | None = None

    @classmethod
    def from_env(cls) -> OpenRouterConfig:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise LLMError("找不到 OPENROUTER_API_KEY，請在 .env 或環境變數設定")
        reasoning = os.environ.get("OPENROUTER_REASONING") or None
        if reasoning not in (None, "low", "medium", "high"):
            raise LLMError(f"OPENROUTER_REASONING 只能是 low、medium、high，收到 {reasoning!r}")
        temperature = os.environ.get("OPENROUTER_TEMPERATURE") or None
        try:
            temperature = float(temperature) if temperature is not None else None
        except ValueError as e:
            raise LLMError(f"OPENROUTER_TEMPERATURE 要是數字，收到 {temperature!r}") from e
        max_tokens_text = os.environ.get("OPENROUTER_MAX_TOKENS") or None
        max_tokens = None
        if max_tokens_text is not None:
            try:
                if re.fullmatch(r"[0-9]+", max_tokens_text) is None:
                    raise ValueError("not an ASCII integer")
                max_tokens = int(max_tokens_text)
                if max_tokens <= 0:
                    raise ValueError("not positive")
            except ValueError as e:
                raise LLMError("OPENROUTER_MAX_TOKENS 必須是正整數") from e
        return cls(
            api_key=api_key,
            model=os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL,
            reasoning=reasoning,
            temperature=temperature,
            max_tokens=max_tokens,
        )


class OpenRouterClient:
    def __init__(self, config: OpenRouterConfig, transport: httpx.BaseTransport | None = None):
        self.config = config
        self.model_name = config.model
        self.usage = Usage()
        self._http = httpx.Client(
            timeout=config.timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "X-Title": "Once Wrong",
            },
        )

    def request_body(self, system_prompt: str, user_prompt: str) -> dict:
        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": RESPONSE_FORMAT,
            # 只用支援 JSON schema、而且不保留或拿資料訓練的供應商
            "provider": {"require_parameters": True, "data_collection": "deny"},
            "usage": {"include": True},
        }
        if self.config.temperature is not None:
            body["temperature"] = self.config.temperature
        if self.config.reasoning:
            body["reasoning"] = {"effort": self.config.reasoning}
        if self.config.max_tokens is not None:
            body["max_tokens"] = self.config.max_tokens
        return body

    def explain(self, system_prompt: str, user_prompt: str) -> AIExplanation:
        try:
            response = self._http.post(API_URL, json=self.request_body(system_prompt, user_prompt))
        except httpx.HTTPError as e:
            raise LLMError(f"OpenRouter 連線失敗：{e}") from e

        try:
            data = response.json()
        except ValueError:
            data = {}
        error = data.get("error") if isinstance(data, dict) else None
        if response.status_code >= 400 or error:
            # 訊息帶 HTTP 狀態碼，評分程式靠它判斷 429、503 要不要重試
            code = (error or {}).get("code", response.status_code) if isinstance(error, dict) else response.status_code
            message = (error or {}).get("message", response.text[:300]) if isinstance(error, dict) else response.text[:300]
            raise LLMError(f"OpenRouter 呼叫失敗：{code} {message}")

        if isinstance(data.get("usage"), dict):
            self.usage.add(data["usage"])
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"OpenRouter 回傳格式不符：{json.dumps(data, ensure_ascii=False)[:300]}") from e
        try:
            return AIExplanation.model_validate_json(_FENCE.sub("", content.strip()))
        except ValueError as e:
            raise LLMError(f"模型回傳的 JSON 不符格式：{content[:300]!r}") from e
