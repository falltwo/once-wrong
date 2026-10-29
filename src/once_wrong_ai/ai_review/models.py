"""AI 審核的輸入輸出格式。

`AIExplanation` 是要求 Gemini 回傳的 JSON 結構；`ReviewItem` 是整個審核流程
交給畫面（或下一步「擋重複錯」）的結果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field

from once_wrong_ai.kb.models import Passage
from once_wrong_ai.report import Cell, CellRef
from once_wrong_ai.rules import Violation

# ---- Gemini 回傳的結構（欄位盡量單純，Gemini 的 response_schema 不支援 dict / union）----


class AIChange(BaseModel):
    row: int = Field(description="要修改的列號，從 1 開始")
    column: str = Field(description="要修改的欄位名稱，必須跟報表欄名完全相同")
    new_value: str = Field(description="修改後的值；數字用阿拉伯數字，空白請給空字串")


class AIFixCandidate(BaseModel):
    changes: list[AIChange]
    reason: str = Field(description="一句話說明為什麼這樣改")


class AIExplanation(BaseModel):
    title: str = Field(description="一行標題，說明哪裡錯")
    explanation: str = Field(description="白話說明哪裡錯、為什麼錯，2 到 4 句")
    candidates: list[AIFixCandidate] = Field(description="修法建議，最可能的放第一個")
    citations: list[str] = Field(default_factory=list, description="說明所依據的手冊段落編號，例如 K1、K3")


# ---- 審核流程的結果 ----


class ExplanationSource(str, Enum):  # noqa: UP042 - preserve the public Enum string representation
    AI = "ai"
    FALLBACK_LLM_ERROR = "fallback_llm_error"
    FALLBACK_NUMBER_GUARD = "fallback_number_guard"


@dataclass
class FixSuggestion:
    changes: dict[CellRef, Cell]
    reason: str


@dataclass
class RejectedSuggestion:
    suggestion: FixSuggestion | None
    raw: AIFixCandidate
    why: str


@dataclass
class CandidateReview:
    rank: int
    revalidation: str
    reason: str
    suggestion: FixSuggestion | None
    raw: AIFixCandidate
    blocked_numbers: list[str] = field(default_factory=list)


@dataclass
class ReviewItem:
    violation: Violation
    title: str
    explanation: str
    source: ExplanationSource
    suggestion: FixSuggestion | None
    """已經通過規則重驗的修法；沒有就是 None（AI 不給，或給的都被擋下）。"""
    rejected: list[RejectedSuggestion] = field(default_factory=list)
    """被擋下的修法，不給使用者看，但會寫進稽核紀錄。"""
    blocked_numbers: list[str] = field(default_factory=list)
    """AI 說明裡對不上資料的數字（觸發整段攔下）。"""
    sources: list[Passage] = field(default_factory=list)
    """AI 引用、而且確實有提供給它的手冊段落。"""
    candidates: list[CandidateReview] = field(default_factory=list)
    """依原始排名保存全部候選的重驗結果，包含第二個以後通過的候選。"""
