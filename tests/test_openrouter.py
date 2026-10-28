"""OpenRouter client：用假的 HTTP transport，不會連網、不花錢。"""

import json

import httpx
import pytest

from once_wrong.ai_review.llm import LLMError, llm_from_env
from once_wrong.ai_review.openrouter import OpenRouterClient, OpenRouterConfig

REPLY = {
    "title": "異動序號要依序編",
    "explanation": "保單 A00002 共 3 筆，第 3 列應為 00002。",
    "candidates": [{"changes": [{"row": 3, "column": "異動序號", "new_value": "00002"}], "reason": "依序編號"}],
    "citations": ["K1"],
}
USAGE = {"prompt_tokens": 5000, "completion_tokens": 800, "completion_tokens_details": {"reasoning_tokens": 300},
         "cost": 0.00061}


def _client(handler, **config):
    sent = []

    def record(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return handler(request)

    client = OpenRouterClient(OpenRouterConfig(api_key="test-key", **config), transport=httpx.MockTransport(record))
    return client, sent


def _ok(content: str, usage=USAGE):
    return lambda request: httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": usage})


def test_request_asks_for_schema_and_private_providers():
    client, sent = _client(_ok(json.dumps(REPLY)), model="qwen/qwen3.5-flash-02-23", reasoning="low")
    client.explain("系統", "使用者")

    [request] = sent
    assert request.headers["Authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "qwen/qwen3.5-flash-02-23"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["response_format"]["type"] == "json_schema"
    assert body["provider"] == {"require_parameters": True, "data_collection": "deny"}
    assert body["reasoning"] == {"effort": "low"}


def test_schema_is_strict_for_every_object():
    client, _ = _client(_ok(json.dumps(REPLY)))
    schema = client.request_body("s", "u")["response_format"]["json_schema"]["schema"]

    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                yield node
            for value in node.values():
                yield from objects(value)
        elif isinstance(node, list):
            for value in node:
                yield from objects(value)

    found = list(objects(schema))
    assert len(found) >= 3  # AIExplanation、AIFixCandidate、AIChange
    for obj in found:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
    assert '"default"' not in json.dumps(schema)


def test_reply_is_parsed_and_usage_is_counted():
    client, _ = _client(_ok(json.dumps(REPLY, ensure_ascii=False)))
    first = client.explain("s", "u")
    client.explain("s", "u")

    assert first.candidates[0].changes[0].new_value == "00002"
    assert client.usage.calls == 2
    assert client.usage.prompt_tokens == 10_000 and client.usage.reasoning_tokens == 600
    assert client.usage.cost_usd == pytest.approx(0.00122)


def test_json_wrapped_in_code_fence_is_accepted():
    client, _ = _client(_ok("```json\n" + json.dumps(REPLY) + "\n```"))
    assert client.explain("s", "u").title == REPLY["title"]


def test_rate_limit_error_keeps_status_code_for_retry():
    client, _ = _client(lambda r: httpx.Response(429, json={"error": {"code": 429, "message": "Rate limit exceeded"}}))
    with pytest.raises(LLMError, match="429"):
        client.explain("s", "u")


def test_error_inside_200_response_is_raised():
    client, _ = _client(lambda r: httpx.Response(200, json={"error": {"code": 502, "message": "provider down"}}))
    with pytest.raises(LLMError, match="502"):
        client.explain("s", "u")


def test_reply_not_matching_schema_is_an_error():
    client, _ = _client(_ok('{"title": "缺欄位"}'))
    with pytest.raises(LLMError, match="不符格式"):
        client.explain("s", "u")


def test_provider_is_chosen_from_env(monkeypatch):
    for name in ("ONCE_WRONG_PROVIDER", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_REASONING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("once_wrong.ai_review.llm._load_dotenv", lambda: None)

    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
    llm = llm_from_env()
    assert isinstance(llm, OpenRouterClient) and llm.model_name == "deepseek/deepseek-v4-flash"

    monkeypatch.setenv("ONCE_WRONG_PROVIDER", "nope")
    with pytest.raises(LLMError, match="gemini 或 openrouter"):
        llm_from_env()

    monkeypatch.setenv("ONCE_WRONG_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_REASONING", "max")
    with pytest.raises(LLMError, match="low、medium、high"):
        llm_from_env()


def test_temperature_is_only_sent_when_set():
    """推理模型不接受 temperature；預設不送，才不會找不到供應商。"""
    client, _ = _client(_ok(json.dumps(REPLY)))
    assert "temperature" not in client.request_body("s", "u")
    client, _ = _client(_ok(json.dumps(REPLY)), temperature=0.2)
    assert client.request_body("s", "u")["temperature"] == 0.2
