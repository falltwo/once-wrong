"""Recorded evaluation scores always retain their model provenance."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from once_wrong.main import create_app


class NoCallsLLM:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def explain(self, system_prompt: str, user_prompt: str):
        raise AssertionError("Reading recorded evaluation must not call a model")


@pytest.mark.parametrize(
    ("runtime_model", "matches"),
    [("deepseek/deepseek-v4-flash", False), ("gemini-3.5-flash", True)],
)
def test_evaluation_distinguishes_recorded_model_from_runtime(
    database_path: Path, runtime_model: str, matches: bool
):
    evaluation = {
        "model": "gemini-3.5-flash",
        "metrics": {"handledCorrectly": {"rate": 0.9311}},
    }
    evaluation_path = database_path.parent / "evaluation.json"
    evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
    application = create_app(
        database_path,
        seed_demo=False,
        llm=NoCallsLLM(runtime_model),
        knowledge_dir=database_path.parent / "missing-kb",
        memory_path=database_path.parent / "missing-notes.jsonl",
        evaluation_path=evaluation_path,
    )

    with TestClient(application) as client:
        response = client.get("/evaluations/latest")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        payload = response.json()
        assert payload["model"] == evaluation["model"]
        assert payload["metrics"] == evaluation["metrics"]
        context = payload["evaluationContext"]
        assert context["evaluatedModel"] == evaluation["model"]
        assert context["runtimeModel"] == client.get("/health").json()["ai"]["model"]
        assert context["runtimeConfigured"] is True
        assert context["modelMatchesRuntime"] is matches
        assert context["displayNotice"]
        if matches:
            assert "不代表目前程式與環境已重新驗證" in context["displayNotice"]
        else:
            assert "此分數不代表目前模型的表現" in context["displayNotice"]


@pytest.mark.parametrize("evaluation", [[], None, {}, {"model": " "}, {"model": 93}])
def test_evaluation_without_identifiable_model_is_rejected(database_path: Path, evaluation):
    evaluation_path = database_path.parent / "evaluation.json"
    evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
    application = create_app(
        database_path,
        seed_demo=False,
        llm=NoCallsLLM("runtime-model"),
        evaluation_path=evaluation_path,
    )
    with TestClient(application) as client:
        response = client.get("/evaluations/latest")
        assert response.status_code == 500
        assert response.json()["code"] == "EVALUATION_INVALID"
