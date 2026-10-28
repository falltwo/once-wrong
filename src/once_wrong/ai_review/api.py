"""把檢核錯誤和 AI 審核結果轉成 API 回應格式。

`SuggestionResponse` 對齊前端 `frontend/src/types/index.ts` 的 `Suggestion`
（codex/frontend-prototype 分支），後端的 suggestion 端點可以直接當 response_model。
`IssueResponse` 是給任意欄位報表（例如個人壽險承保資料）的錯誤格式；前端目前的 `Issue`
只支援 demo 的 4 個欄位，要接壽險規則需要一起擴充。提案說明見 docs/ai-review-api.md。

列號從 1 開始，跟畫面上的「第 3 列」一致。`row_id` 決定 API 裡每一列的識別碼：
demo 報表用資料自己的 id 欄，壽險資料沒有唯一的 id 欄，預設用列號。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from once_wrong.ai_review.models import ExplanationSource, ReviewItem
from once_wrong.report import Cell
from once_wrong.rules import Violation

RowId = Callable[[int], str]
JsonValue = str | int | None

_MAX_SAFE_INTEGER = 2**53 - 1
"""超過這個值的整數，JavaScript 的 number 會失真，改用文字傳。"""


def row_number_id(row: int) -> str:
    return str(row)


def json_value(value: Cell) -> JsonValue:
    """報表的值轉成 JSON：整數用 number，小數和超大整數用文字以免失真。"""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value if abs(value) <= _MAX_SAFE_INTEGER else str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


# ---- 錯誤列表 ----


class IssueCell(BaseModel):
    row: int
    rowId: str
    column: str
    value: JsonValue


class IssueResponse(BaseModel):
    id: str
    """`{第一列的 rowId}:{ruleId}`，跟後端 demo 的格式一致；同一份報表內不重複。"""
    ruleId: str
    title: str
    """規則的固定說明（AI 失敗時也顯示這段）。"""
    rows: list[int]
    rowIds: list[str]
    cells: list[IssueCell]
    """出錯的格子；AI 的修法只能改這些格子所在的列。"""
    facts: dict[str, JsonValue]
    """程式算好的數字，例如應填的值、筆數。"""
    contextRowIds: list[str]
    """規則附上的參考列（例如同一保單的其他筆），畫面可以一起列出來。"""
    repeated: bool


def issue_ids(violations: Iterable[Violation], row_id: RowId = row_number_id) -> list[str]:
    """每筆錯誤的 id：`{第一列的 rowId}:{ruleId}`；同一份報表內不重複。"""
    ids: list[str] = []
    used: set[str] = set()
    for v in violations:
        base = f"{row_id(v.rows[0])}:{v.rule_id}"
        issue_id, n = base, 2
        while issue_id in used:  # 同一條規則從同一列開始報兩次時才會發生
            issue_id, n = f"{base}#{n}", n + 1
        used.add(issue_id)
        ids.append(issue_id)
    return ids


def find_violation(
    violations: list[Violation], issue_id: str, row_id: RowId = row_number_id
) -> Violation | None:
    """依 API 的 issueId 找回規則判定的那一筆錯誤；找不到回傳 None（端點回 404）。"""
    return next((v for v, i in zip(violations, issue_ids(violations, row_id)) if i == issue_id), None)


def issue_payloads(
    report_rows: list[dict[str, Cell]],
    violations: Iterable[Violation],
    row_id: RowId = row_number_id,
    repeated: Callable[[Violation], bool] = lambda v: False,
) -> list[IssueResponse]:
    """把規則判定的錯誤轉成 API 格式。`repeated` 由第 5 步「擋重複錯」決定。"""
    violations = list(violations)
    issues: list[IssueResponse] = []
    for v, issue_id in zip(violations, issue_ids(violations, row_id)):
        issues.append(
            IssueResponse(
                id=issue_id,
                ruleId=v.rule_id,
                title=v.message,
                rows=v.rows,
                rowIds=[row_id(r) for r in v.rows],
                cells=[
                    IssueCell(
                        row=c.row,
                        rowId=row_id(c.row),
                        column=c.column,
                        value=json_value(report_rows[c.row - 1].get(c.column)),
                    )
                    for c in v.cells
                ],
                facts={k: json_value(value) for k, value in v.facts.items()},
                contextRowIds=[row_id(r) for r in v.reference_rows],
                repeated=repeated(v),
            )
        )
    return issues


# ---- AI 說明與修法（對齊前端 Suggestion）----


class SuggestionChange(BaseModel):
    rowId: str
    row: int
    column: str
    value: JsonValue


class VerifiedSuggestion(BaseModel):
    reason: str
    verification: Literal["passed"] = "passed"
    changes: list[SuggestionChange]


class Citation(BaseModel):
    id: str
    source: str
    """手冊名稱。"""
    section: list[str]
    page: int | None = None


class SuggestionResponse(BaseModel):
    title: str
    explanation: str
    suggestion: VerifiedSuggestion | None
    """通過規則重驗的修法；沒有就是 null，畫面改提示「請核對來源資料後自行修改」。"""
    rejectedSuggestions: list[str]
    """被規則重驗擋下的修法，只放擋下的理由，不放修改內容。"""
    citations: list[Citation]
    blockedNumbers: list[str]
    model: str
    verification: Literal["passed", "unavailable"]
    source: Literal["ai", "fallback_llm_error", "fallback_number_guard"]


def suggestion_payload(item: ReviewItem, model: str, row_id: RowId = row_number_id) -> SuggestionResponse:
    fix = item.suggestion
    verified = (
        VerifiedSuggestion(
            reason=fix.reason,
            changes=[
                SuggestionChange(rowId=row_id(ref.row), row=ref.row, column=ref.column, value=json_value(value))
                for ref, value in sorted(fix.changes.items())
            ],
        )
        if fix
        else None
    )
    return SuggestionResponse(
        title=item.title,
        explanation=item.explanation,
        suggestion=verified,
        rejectedSuggestions=[r.why for r in item.rejected],
        citations=[Citation(id=p.id, source=p.manual, section=p.section, page=p.page) for p in item.sources],
        blockedNumbers=item.blocked_numbers,
        model=model,
        verification="passed" if verified else "unavailable",
        source=ExplanationSource(item.source).value,
    )
