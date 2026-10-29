"""Provider timeout configuration is checked without making network requests."""

import sys
from types import ModuleType, SimpleNamespace

from once_wrong_ai.ai_review.llm import GeminiClient, GeminiConfig
from once_wrong_ai.ai_review.openrouter import OpenRouterConfig


def test_gemini_uses_finite_timeout_and_does_not_retry(monkeypatch):
    google = ModuleType("google")
    genai = ModuleType("google.genai")
    received = {}

    def client(**kwargs):
        received.update(kwargs)
        return object()

    genai.Client = client
    genai.types = SimpleNamespace(HttpOptions=SimpleNamespace, HttpRetryOptions=SimpleNamespace)
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)

    GeminiClient(GeminiConfig(api_key="fake-test-key"))

    assert received["http_options"].timeout == 30_000
    assert received["http_options"].retry_options.attempts == 1


def test_openrouter_defaults_to_finite_timeout():
    assert OpenRouterConfig(api_key="fake-test-key").timeout == 30.0
