"""AI 修法的規則重驗：建議先套到副本上重跑規則，通過了才給人看。"""

from __future__ import annotations

from dataclasses import dataclass

from once_wrong_ai.ai_review.models import AIFixCandidate, FixSuggestion
from once_wrong_ai.report import Cell, CellRef, Report
from once_wrong_ai.rules import RuleSet, Violation


@dataclass
class ValidationOutcome:
    passed: bool
    why: str
    suggestion: FixSuggestion | None = None


def validate_candidate(
    report: Report,
    violation: Violation,
    candidate: AIFixCandidate,
    rules: RuleSet,
    before: list[Violation],
) -> ValidationOutcome:
    allowed_rows = set(violation.rows)
    changes: dict[CellRef, Cell] = {}

    if not candidate.changes:
        return ValidationOutcome(False, "建議沒有任何修改")

    for change in candidate.changes:
        ref = CellRef(change.row, change.column)
        if not report.has_cell(ref):
            return ValidationOutcome(False, f"格子不存在：第 {change.row} 列「{change.column}」")
        if change.row not in allowed_rows:
            return ValidationOutcome(False, f"改到出錯列以外的資料：第 {change.row} 列")
        try:
            value = report.parse_value(change.column, change.new_value)
        except ValueError as e:
            return ValidationOutcome(False, str(e))
        if ref in changes and changes[ref] != value:
            return ValidationOutcome(False, f"同一格給了兩個不同的值：第 {change.row} 列「{change.column}」")
        changes[ref] = value

    if all(report.get(ref) == value for ref, value in changes.items()):
        return ValidationOutcome(False, "建議的值跟原本一樣，沒有實際修改")

    suggestion = FixSuggestion(changes=changes, reason=candidate.reason)
    after = rules.check(report.with_changes(changes))
    after_keys = {v.key for v in after}

    if violation.key in after_keys:
        return ValidationOutcome(False, "重驗後同一條規則仍未通過", suggestion)

    before_keys = {v.key for v in before}
    new_errors = [v for v in after if v.key not in before_keys]
    if new_errors:
        listed = "、".join(f"{v.rule_id}（第 {','.join(map(str, v.rows))} 列）" for v in new_errors)
        return ValidationOutcome(False, f"修改後產生新的錯誤：{listed}", suggestion)

    return ValidationOutcome(True, "規則重驗通過", suggestion)
