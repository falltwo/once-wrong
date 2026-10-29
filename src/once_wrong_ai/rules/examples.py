"""示範規則：官方規則寄來之前，讓 AI 審核流程能跑起來。

這些不是主辦方的規則。正式版本要換掉，或標示為「自訂延伸規則」。
欄位名稱對應簡報第 8 頁的示意畫面（險種、上月期末、本月期初）。
"""

from __future__ import annotations

from dataclasses import dataclass

from once_wrong_ai.report import CellRef, Report
from once_wrong_ai.rules import RuleSet, Violation
from once_wrong_ai.rules.life import FirstTransactionNotTerminated, TransactionSequence


@dataclass
class RequiredField:
    rule_id: str
    column: str

    @property
    def description(self) -> str:
        return f"「{self.column}」不可空白"

    def check(self, report: Report) -> list[Violation]:
        return [
            Violation(
                rule_id=self.rule_id,
                message=f"第 {i} 列的「{self.column}」是空白，必須填寫。",
                cells=(CellRef(i, self.column),),
            )
            for i, row in enumerate(report.rows, start=1)
            if row.get(self.column) in (None, "")
        ]


@dataclass
class OpeningEqualsClosing:
    """本月期初必須等於上月期末。"""

    rule_id: str
    closing_column: str
    opening_column: str

    @property
    def description(self) -> str:
        return f"「{self.opening_column}」必須等於「{self.closing_column}」"

    def check(self, report: Report) -> list[Violation]:
        violations = []
        for i, row in enumerate(report.rows, start=1):
            closing = row.get(self.closing_column)
            opening = row.get(self.opening_column)
            if closing is None or opening is None or isinstance(closing, str) or isinstance(opening, str):
                continue
            if closing != opening:
                violations.append(
                    Violation(
                        rule_id=self.rule_id,
                        message=(
                            f"第 {i} 列的「{self.opening_column}」與「{self.closing_column}」不一致。"
                        ),
                        cells=(CellRef(i, self.closing_column), CellRef(i, self.opening_column)),
                        facts={
                            "上月期末": closing,
                            "本月期初": opening,
                            "差額": closing - opening,
                        },
                    )
                )
        return violations


def life_example_rules() -> RuleSet:
    """個人壽險的兩條真實規則（手冊裡的 L0302、L0303），示範知識庫檢索。"""
    return RuleSet([TransactionSequence(), FirstTransactionNotTerminated()])


def example_rules() -> RuleSet:
    return RuleSet(
        [
            RequiredField(rule_id="R-01", column="險種"),
            OpeningEqualsClosing(rule_id="R-07", closing_column="上月期末", opening_column="本月期初"),
        ]
    )
