"""檢核規則的介面。

官方規則還沒拿到，這裡只定義「規則長什麼樣子」。拿到規則後，每條規則實作
`Rule` 即可，AI 審核那一層不用改。

規則是唯一的裁判：錯不錯由 `Rule.check` 決定，AI 只負責解釋和建議。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable

from once_wrong_ai.report import CellRef, Report

FactValue = int | Decimal | str | None


@dataclass(frozen=True)
class Violation:
    rule_id: str
    message: str
    """給人看的固定說明（AI 失敗或被攔下時，就顯示這段）。"""
    cells: tuple[CellRef, ...]
    """出錯的格子。AI 的修法只能改這些格子所在的列。"""
    facts: dict[str, FactValue] = field(default_factory=dict, compare=False, hash=False)
    """程式算好的數字，例如 expected / actual / diff。AI 只能引用這裡和報表上的數字。"""
    context_rows: tuple[int, ...] = field(default=(), compare=False, hash=False)
    """給 AI 參考的相關列（例如同一保單的其他筆）。AI 看得到但不能改；不算進 key。"""

    @property
    def key(self) -> tuple[str, tuple[CellRef, ...]]:
        """同一條規則、同一批格子，視為同一個錯（擋重複錯也用這個）。"""
        return (self.rule_id, tuple(sorted(self.cells)))

    @property
    def rows(self) -> list[int]:
        return sorted({c.row for c in self.cells})

    @property
    def reference_rows(self) -> list[int]:
        """只供參考、不在出錯格子裡的列。"""
        return sorted(set(self.context_rows) - set(self.rows))


@runtime_checkable
class Rule(Protocol):
    rule_id: str
    description: str

    def check(self, report: Report) -> list[Violation]: ...


class RuleSet:
    def __init__(self, rules: list[Rule]):
        ids = [r.rule_id for r in rules]
        if len(ids) != len(set(ids)):
            raise ValueError(f"規則代碼重複：{ids}")
        self.rules = list(rules)

    def get(self, rule_id: str) -> Rule:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        raise KeyError(rule_id)

    def check(self, report: Report) -> list[Violation]:
        violations: list[Violation] = []
        for rule in self.rules:
            violations.extend(rule.check(report))
        return violations
