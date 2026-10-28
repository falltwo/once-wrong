"""示範規則：官方規則寄來之前，讓 AI 審核流程能跑起來。

這些不是主辦方的規則。正式版本要換掉，或標示為「自訂延伸規則」。
欄位名稱對應簡報第 8 頁的示意畫面（險種、上月期末、本月期初）。
"""

from __future__ import annotations

from dataclasses import dataclass

from once_wrong.report import CellRef, Report
from once_wrong.rules import RuleSet, Violation


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


@dataclass
class TransactionSequence:
    """個人壽險 L0302：同一保單只有一筆時異動序號=00000；兩筆以上時從 00001 依序編。

    依據：個人壽險填報說明手冊範例與檢核規則 2025，參、欄位檢核「03. 異動序號」。
    """

    rule_id: str = "L0302"
    description: str = (
        "保單只有一筆時，異動序號=00000；保單有兩筆以上異動時，第一筆異動序號=00001，"
        "其他依序排列，即 00001、00002、00003"
    )

    def check(self, report: Report) -> list[Violation]:
        groups: dict[tuple, list[int]] = {}
        for i, row in enumerate(report.rows, start=1):
            groups.setdefault((row.get("保單編號"), row.get("保單編號序號")), []).append(i)

        violations = []
        for (policy, sub), rows in groups.items():
            expected = ["00000"] if len(rows) == 1 else [f"{n:05d}" for n in range(1, len(rows) + 1)]
            actual = [str(report.row(r).get("異動序號") or "") for r in rows]
            if actual != expected:
                violations.append(
                    Violation(
                        rule_id=self.rule_id,
                        message=(
                            f"保單 {policy}（序號 {sub}）共 {len(rows)} 筆，異動序號應為 "
                            f"{'、'.join(expected)}，目前是 {'、'.join(actual)}。"
                        ),
                        cells=tuple(CellRef(r, "異動序號") for r in rows),
                        facts={
                            "保單編號": policy,
                            "保單編號序號": sub,
                            "筆數": len(rows),
                            "應填異動序號": "、".join(expected),
                            "目前異動序號": "、".join(actual),
                        },
                    )
                )
        return violations


_L0303_FORBIDDEN = ("DEA", "ADS", "TDI", "ATS", "MAD", "SRD", "RES", "LOP", "TMD", "DDA", "ABD")


@dataclass
class FirstTransactionNotTerminated:
    """個人壽險 L0303：異動序號=00001 時，退保別不可為 DEA、ADS 等終止類代號。"""

    rule_id: str = "L0303"
    description: str = "異動序號=“00001”時，退保別不可為 " + "、".join(f"“{c}”" for c in _L0303_FORBIDDEN)

    def check(self, report: Report) -> list[Violation]:
        return [
            Violation(
                rule_id=self.rule_id,
                message=f"第 {i} 列是這張保單的第一筆異動（00001），退保別不可以填 {row.get('退保別')}。",
                cells=(CellRef(i, "異動序號"), CellRef(i, "退保別")),
                facts={"退保別": row.get("退保別")},
            )
            for i, row in enumerate(report.rows, start=1)
            if row.get("異動序號") == "00001" and row.get("退保別") in _L0303_FORBIDDEN
        ]


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
