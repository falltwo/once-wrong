"""個人壽險承保資料的檢核規則，照填報手冊實作。

依據：個人壽險填報說明手冊範例與檢核規則 2025，「參、欄位檢核」與「肆、檢核程式項目及代碼表」。
只實作用這 8 個欄位就能檢的規則：公司代號、保單編號、保單編號序號、異動序號、加保別、加保日期、
退保別、退保日期。正式版本由組員的規則引擎取代，這裡是讓 AI 審核和評分能先跑起來。

日期欄位是 8 碼西元年月日的文字，「00000000」代表沒有日期。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime

from once_wrong_ai.report import CellRef, Report
from once_wrong_ai.rules import RuleSet, Violation

NO_DATE = "00000000"
NOT_CHANGED = "XED"
"""加保別或退保別為 XED：這一段沒有異動。"""

TERMINATIONS = ("DEA", "ADS", "TDI", "ATS", "MAD", "SRD", "RES", "LOP", "TMD", "DDA", "ABD")
"""終止類退保別（身故、失能、滿期、解約等），保單到此結束。"""

CHAINED_CHANGES = ("INN", "DNN", "HCC", "TPD", "PAU", "ROL", "INV")
"""契約變更類加保別：要接上一筆的退保別和退保日（L1305）。"""


def _policy_key(row: dict) -> tuple:
    """多筆檢核的單位：同一家公司內的保單編號＋保單編號序號。"""
    return (row.get("公司代號"), row.get("保單編號"), row.get("保單編號序號"))


def _policy_groups(report: Report) -> dict[tuple, list[int]]:
    """保單號碼 → 這張保單在檔案中的列號（依檔案先後）。"""
    groups: dict[tuple, list[int]] = {}
    for i, row in enumerate(report.rows, start=1):
        groups.setdefault(_policy_key(row), []).append(i)
    return groups


def _is_date(text: object) -> bool:
    """西元年月日，月 1~12、日依大小月及閏年。"""
    if not isinstance(text, str) or len(text) != 8 or not text.isdigit():
        return False
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError:
        return False
    return True


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
        violations = []
        for (_, policy, sub), rows in _policy_groups(report).items():
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


@dataclass
class FirstTransactionNotTerminated:
    """個人壽險 L0303：異動序號=00001 時，退保別不可為 DEA、ADS 等終止類代號。"""

    rule_id: str = "L0303"
    description: str = "異動序號=“00001”時，退保別不可為 " + "、".join(f"“{c}”" for c in TERMINATIONS)

    def check(self, report: Report) -> list[Violation]:
        groups = _policy_groups(report)
        return [
            Violation(
                rule_id=self.rule_id,
                message=f"第 {i} 列是這張保單的第一筆異動（00001），退保別不可以填 {row.get('退保別')}。",
                cells=(CellRef(i, "異動序號"), CellRef(i, "退保別")),
                facts={"退保別": row.get("退保別")},
                # 判斷首筆該怎麼改，要看同一保單的其他筆
                context_rows=tuple(groups[_policy_key(row)]),
            )
            for i, row in enumerate(report.rows, start=1)
            if row.get("異動序號") == "00001" and row.get("退保別") in TERMINATIONS
        ]


@dataclass
class NewContractIsFirst:
    """L1303：加保別=NEW 或 NCT 時，異動序號=00000 或 00001（一定是保單的第 1 筆）。"""

    rule_id: str = "L1303"
    description: str = "加保別=“NEW”或“NCT”時，異動序號=“00000”或“00001”；一定是保單的第 1 筆"

    def check(self, report: Report) -> list[Violation]:
        groups = _policy_groups(report)
        return [
            Violation(
                rule_id=self.rule_id,
                message=(
                    f"第 {i} 列的加保別是 {row.get('加保別')}（新契約），應該是保單的第 1 筆，"
                    f"異動序號要是 00000 或 00001，目前是 {row.get('異動序號')}。"
                ),
                cells=(CellRef(i, "異動序號"), CellRef(i, "加保別")),
                facts={"加保別": row.get("加保別"), "異動序號": row.get("異動序號")},
                context_rows=tuple(groups[_policy_key(row)]),
            )
            for i, row in enumerate(report.rows, start=1)
            if row.get("加保別") in ("NEW", "NCT") and row.get("異動序號") not in ("00000", "00001")
        ]


@dataclass
class EntryDateMatchesEntryType:
    """L1304：加保別≠XED 時加保日期≠00000000；加保別=XED 時加保日期=00000000。"""

    rule_id: str = "L1304"
    description: str = (
        "加保別=“NEW”時，加保日期≠“00000000”；加保別≠“XED”時，加保日期≠“00000000”；"
        "加保別=“XED”時，加保日期=“00000000”"
    )

    def check(self, report: Report) -> list[Violation]:
        violations = []
        for i, row in enumerate(report.rows, start=1):
            entry, date = row.get("加保別"), row.get("加保日期")
            if entry != NOT_CHANGED and date == NO_DATE:
                message = f"第 {i} 列的加保別是 {entry}，有異動就要填加保日期，不可以是 00000000。"
            elif entry == NOT_CHANGED and date != NO_DATE:
                message = f"第 {i} 列的加保別是 XED（沒有異動），加保日期應為 00000000，目前是 {date}。"
            else:
                continue
            violations.append(
                Violation(
                    rule_id=self.rule_id,
                    message=message,
                    cells=(CellRef(i, "加保別"), CellRef(i, "加保日期")),
                    facts={"加保別": entry, "加保日期": date},
                )
            )
        return violations


@dataclass
class EntryContinuesPreviousExit:
    """L1305：加保別為 INN、DNN 等契約變更時，加保別=上一筆退保別，加保日=上一筆退保日。"""

    rule_id: str = "L1305"
    description: str = (
        "加保別= " + "、".join(f"“{c}”" for c in CHAINED_CHANGES) + " 時，"
        "加保別=上一筆退保別，且加保日期=上一筆退保日期"
    )

    def check(self, report: Report) -> list[Violation]:
        violations = []
        for rows in _policy_groups(report).values():
            for prev, cur in zip(rows, rows[1:]):
                p, c = report.row(prev), report.row(cur)
                if c.get("加保別") not in CHAINED_CHANGES:
                    continue
                if c.get("加保別") == p.get("退保別") and c.get("加保日期") == p.get("退保日期"):
                    continue
                violations.append(
                    Violation(
                        rule_id=self.rule_id,
                        message=(
                            f"第 {cur} 列的加保別 {c.get('加保別')}、加保日期 {c.get('加保日期')}，"
                            f"要跟上一筆（第 {prev} 列）的退保別 {p.get('退保別')}、"
                            f"退保日期 {p.get('退保日期')} 相同。"
                        ),
                        # 可能錯在這一筆，也可能錯在上一筆，兩邊都可以改
                        cells=(
                            CellRef(prev, "退保別"),
                            CellRef(prev, "退保日期"),
                            CellRef(cur, "加保別"),
                            CellRef(cur, "加保日期"),
                        ),
                        facts={
                            "上一筆退保別": p.get("退保別"),
                            "上一筆退保日期": p.get("退保日期"),
                            "本筆加保別": c.get("加保別"),
                            "本筆加保日期": c.get("加保日期"),
                        },
                        context_rows=tuple(rows),
                    )
                )
        return violations


@dataclass
class NotBothUnchanged:
    """L1502：加保別、退保別不能同時為 XED。"""

    rule_id: str = "L1502"
    description: str = "加保別、退保別不能同時為“XED”"

    def check(self, report: Report) -> list[Violation]:
        return [
            Violation(
                rule_id=self.rule_id,
                message=f"第 {i} 列的加保別和退保別都是 XED，一筆資料不能兩頭都沒有異動。",
                cells=(CellRef(i, "加保別"), CellRef(i, "退保別")),
                facts={"加保別": row.get("加保別"), "退保別": row.get("退保別")},
            )
            for i, row in enumerate(report.rows, start=1)
            if row.get("加保別") == NOT_CHANGED and row.get("退保別") == NOT_CHANGED
        ]


@dataclass
class ExitDateMatchesExitType:
    """L1504：退保別≠XED 時退保日期≠00000000；退保別=XED 時退保日期=00000000。"""

    rule_id: str = "L1504"
    description: str = "退保別≠“XED”時，退保日期≠“00000000”；退保別=“XED”時，退保日期=“00000000”"

    def check(self, report: Report) -> list[Violation]:
        violations = []
        for i, row in enumerate(report.rows, start=1):
            exit_, date = row.get("退保別"), row.get("退保日期")
            if exit_ != NOT_CHANGED and date == NO_DATE:
                message = f"第 {i} 列的退保別是 {exit_}，有異動就要填退保日期，不可以是 00000000。"
            elif exit_ == NOT_CHANGED and date != NO_DATE:
                message = f"第 {i} 列的退保別是 XED（沒有異動），退保日期應為 00000000，目前是 {date}。"
            else:
                continue
            violations.append(
                Violation(
                    rule_id=self.rule_id,
                    message=message,
                    cells=(CellRef(i, "退保別"), CellRef(i, "退保日期")),
                    facts={"退保別": exit_, "退保日期": date},
                )
            )
        return violations


@dataclass
class ValidDate:
    """L1402（加保日期）、L1602（退保日期）：不是 00000000 時，要是合法的西元年月日。"""

    rule_id: str
    column: str

    @property
    def description(self) -> str:
        return f"{self.column}≠“00000000”時，西元年、月為 1~12 月、日為 1~31 日（按大小月及閏年）"

    def check(self, report: Report) -> list[Violation]:
        return [
            Violation(
                rule_id=self.rule_id,
                message=f"第 {i} 列的{self.column} {row.get(self.column)} 不是合法的日期。",
                cells=(CellRef(i, self.column),),
                facts={self.column: row.get(self.column), **_date_parts(row.get(self.column))},
            )
            for i, row in enumerate(report.rows, start=1)
            if row.get(self.column) != NO_DATE and not _is_date(row.get(self.column))
        ]


def _date_parts(text: object) -> dict[str, int]:
    """把 8 碼日期拆成年、月、日，月份合法時附上當月天數，讓 AI 說明時有數字可引用。"""
    if not isinstance(text, str) or len(text) != 8 or not text.isdigit():
        return {}
    year, month, day = int(text[:4]), int(text[4:6]), int(text[6:])
    parts = {"年": year, "月": month, "日": day}
    if 1 <= month <= 12:
        parts["該月天數"] = calendar.monthrange(year, month)[1]
    return parts


@dataclass
class ExitNotBeforeEntry:
    """L1607：退保日期≠00000000 時，退保日期≥加保日期。"""

    rule_id: str = "L1607"
    description: str = "退保日期≠“00000000”時，退保日期≥加保日期"

    def check(self, report: Report) -> list[Violation]:
        violations = []
        for i, row in enumerate(report.rows, start=1):
            entry, exit_ = row.get("加保日期"), row.get("退保日期")
            # 日期本身不合法的，交給 L1402／L1602
            if not (_is_date(entry) and _is_date(exit_)) or exit_ >= entry:
                continue
            violations.append(
                Violation(
                    rule_id=self.rule_id,
                    message=f"第 {i} 列的退保日期 {exit_} 早於加保日期 {entry}。",
                    cells=(CellRef(i, "加保日期"), CellRef(i, "退保日期")),
                    facts={"加保日期": entry, "退保日期": exit_},
                )
            )
        return violations


@dataclass
class TerminationIsLast:
    """LU1504：退保別為 XED 或終止類代號時，是這張保單的最後一筆異動。"""

    rule_id: str = "LU1504"
    description: str = (
        "退保別= “XED”、" + "、".join(f"“{c}”" for c in TERMINATIONS) + " 時，為此保單之最後 1 筆異動"
    )

    def check(self, report: Report) -> list[Violation]:
        violations = []
        for rows in _policy_groups(report).values():
            for n, r in enumerate(rows[:-1], start=1):
                exit_ = report.row(r).get("退保別")
                if exit_ != NOT_CHANGED and exit_ not in TERMINATIONS:
                    continue
                violations.append(
                    Violation(
                        rule_id=self.rule_id,
                        message=(
                            f"第 {r} 列的退保別是 {exit_}，應該是這張保單的最後一筆，"
                            f"但這張保單共 {len(rows)} 筆，這是第 {n} 筆。"
                        ),
                        cells=(CellRef(r, "退保別"),),
                        facts={"退保別": exit_, "保單筆數": len(rows), "本筆是第幾筆": n},
                        context_rows=tuple(rows),
                    )
                )
        return violations


def life_field_rules() -> RuleSet:
    """個人壽險承保資料：上面 8 個欄位能檢的手冊規則，共 11 條。"""
    return RuleSet(
        [
            TransactionSequence(),
            FirstTransactionNotTerminated(),
            NewContractIsFirst(),
            EntryDateMatchesEntryType(),
            EntryContinuesPreviousExit(),
            NotBothUnchanged(),
            ExitDateMatchesExitType(),
            ValidDate(rule_id="L1402", column="加保日期"),
            ValidDate(rule_id="L1602", column="退保日期"),
            ExitNotBeforeEntry(),
            TerminationIsLast(),
        ]
    )
