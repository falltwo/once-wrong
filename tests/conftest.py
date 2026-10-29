from __future__ import annotations

from pathlib import Path

import pytest

from once_wrong_ai.ai_review.llm import LLMError
from once_wrong_ai.ai_review.models import AIExplanation
from once_wrong_ai.report import Report
from once_wrong_ai.rules.examples import example_rules, life_example_rules

EXAMPLE_CSV = Path(__file__).parents[1] / "examples" / "mock_reserve_2026-09.csv"
LIFE_CSV = EXAMPLE_CSV.parent / "mock_life_policies_2025.csv"


class FakeLLM:
    """依序回傳預先寫好的回覆；放 LLMError 代表那一次呼叫失敗。"""

    model_name = "fake"

    def __init__(self, replies: list[AIExplanation | LLMError]):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def explain(self, system_prompt: str, user_prompt: str) -> AIExplanation:
        self.prompts.append(user_prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, LLMError):
            raise reply
        return reply


@pytest.fixture
def report() -> Report:
    return Report.from_csv(EXAMPLE_CSV, meta={"期間": "2026-09"})


@pytest.fixture
def rules():
    return example_rules()


@pytest.fixture
def life_report() -> Report:
    return Report.from_csv(LIFE_CSV, meta={"險別": "個人壽險"})


@pytest.fixture
def life_rules():
    return life_example_rules()
