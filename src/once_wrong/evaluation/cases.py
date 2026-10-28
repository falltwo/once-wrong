"""評分用的案例：先產生一份規則全過的模擬報表，再故意弄壞一處。

被改掉之前的值就是標準答案，所以不用人工標註，要幾筆就產生幾筆。
全部是程式產生的虛構資料，沒有真實保戶。
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from once_wrong.report import Cell, CellRef, Report
from once_wrong.rules.life import NO_DATE, NOT_CHANGED

LIFE_COLUMNS = ["公司代號", "保單編號", "保單編號序號", "異動序號", "加保別", "加保日期", "退保別", "退保日期"]

_CHANGES = ("INN", "DNN", "PAU", "ROL")
"""產生資料用的契約變更代號（加保、減額、減額繳清、展期）。"""
_ENDINGS = ("DEA", "ADS", "SRD", "LOP")
"""產生資料用的終止代號。"""
_YEAR_END = date(2025, 12, 31)


def _d(day: date) -> str:
    return day.strftime("%Y%m%d")


def _parse(text: str) -> date:
    return date(int(text[:4]), int(text[4:6]), int(text[6:]))


def clean_life_report(rng: random.Random, policies: int = 8, report_id: str = "eval") -> Report:
    """產生一份個人壽險承保資料，11 條規則都通過。"""
    rows: list[dict[str, Cell]] = []
    for p in range(1, policies + 1):
        n = rng.choice((1, 1, 2, 2, 3, 4))
        day = date(2025, 1, 1) + timedelta(days=rng.randint(0, 150))
        entry, entry_day = "NEW", day
        for k in range(1, n + 1):
            last = k == n
            if last:
                ending = rng.random() < 0.3
                exit_ = rng.choice(_ENDINGS) if ending else NOT_CHANGED
                exit_day = min(entry_day + timedelta(days=rng.randint(10, 120)), _YEAR_END) if ending else None
            else:
                exit_ = rng.choice(_CHANGES)
                exit_day = entry_day + timedelta(days=rng.randint(15, 60))
            rows.append({
                "公司代號": "01",
                "保單編號": f"E{p:05d}",
                "保單編號序號": "00001",
                "異動序號": "00000" if n == 1 else f"{k:05d}",
                "加保別": entry,
                "加保日期": _d(entry_day),
                "退保別": exit_,
                "退保日期": _d(exit_day) if exit_day else NO_DATE,
            })
            # 下一筆接這一筆的退保別、退保日（L1305）
            entry, entry_day = exit_, exit_day
    return Report(
        report_id=report_id,
        version=1,
        columns=list(LIFE_COLUMNS),
        rows=rows,
        numeric_columns=set(),  # 日期、代號都當文字，不加千分位
        meta={"險別": "個人壽險"},
    )


@dataclass
class Case:
    case_id: str
    mutation: str
    description: str
    clean: Report
    report: Report
    """弄壞之後、要送去審核的報表。"""
    changed: dict[CellRef, Cell]
    """被弄壞的格子 → 原本的值（標準答案）。"""


Mutation = Callable[[Report, random.Random], tuple[dict[CellRef, Cell], str] | None]
"""回傳（要改成的值, 說明）；這份報表沒有適合的位置就回傳 None。"""


def _policies(report: Report) -> list[list[int]]:
    groups: dict[str, list[int]] = {}
    for i, row in enumerate(report.rows, start=1):
        groups.setdefault(row["保單編號"], []).append(i)
    return list(groups.values())


def _pick(rng: random.Random, items: list):
    return rng.choice(items) if items else None


def _multi(report: Report) -> list[list[int]]:
    return [rows for rows in _policies(report) if len(rows) >= 2]


def seq_skip(report, rng):
    """多筆保單的某一筆異動序號跳號或重複 → L0302。"""
    rows = _pick(rng, _multi(report))
    if not rows:
        return None
    r = rng.choice(rows[1:])
    old = int(report.row(r)["異動序號"])
    new = old + rng.choice((1, -1))
    return {CellRef(r, "異動序號"): f"{new:05d}"}, f"第 {r} 列異動序號 {old:05d} 改成 {new:05d}"


def seq_single(report, rng):
    """只有一筆的保單，異動序號誤填 00001 → L0302。"""
    rows = _pick(rng, [rows for rows in _policies(report) if len(rows) == 1])
    if not rows:
        return None
    r = rows[0]
    return {CellRef(r, "異動序號"): "00001"}, f"第 {r} 列單筆保單的異動序號改成 00001"


def first_terminated(report, rng):
    """多筆保單的第一筆退保別填成 DEA → L0303、L1305、LU1504。"""
    rows = _pick(rng, _multi(report))
    if not rows:
        return None
    r = rows[0]
    return {CellRef(r, "退保別"): "DEA"}, f"第 {r} 列（首筆）退保別 {report.row(r)['退保別']} 改成 DEA"


def new_not_first(report, rng):
    """把保單的前兩筆整段對調（新契約跑到第 2 筆）→ 要動兩列才修得好。"""
    rows = _pick(rng, _multi(report))
    if not rows:
        return None
    a, b = rows[0], rows[1]
    fields = ("加保別", "加保日期", "退保別", "退保日期")
    changes = {CellRef(a, f): report.row(b)[f] for f in fields}
    changes.update({CellRef(b, f): report.row(a)[f] for f in fields})
    return changes, f"第 {a}、{b} 列的加退保內容對調"


def new_date_missing(report, rng):
    """新契約的加保日期填成 00000000 → L1304。"""
    r = _pick(rng, [i for i, row in enumerate(report.rows, 1) if row["加保別"] == "NEW"])
    if r is None:
        return None
    return {CellRef(r, "加保日期"): NO_DATE}, f"第 {r} 列（NEW）加保日期改成 00000000"


def chain_code(report, rng):
    """契約變更那筆的加保別跟上一筆的退保別對不上 → L1305。"""
    r = _pick(rng, [i for rows in _multi(report) for i in rows[1:]])
    if r is None:
        return None
    old = report.row(r)["加保別"]
    new = rng.choice([c for c in ("INN", "DNN", "PAU", "ROL") if c != old])
    return {CellRef(r, "加保別"): new}, f"第 {r} 列加保別 {old} 改成 {new}"


def chain_date(report, rng):
    """契約變更那筆的加保日期跟上一筆的退保日期差幾天 → L1305。"""
    r = _pick(rng, [i for rows in _multi(report) for i in rows[1:]])
    if r is None:
        return None
    old = report.row(r)["加保日期"]
    new = _d(_parse(old) + timedelta(days=rng.choice((1, 2, 3, -1, -2))))
    return {CellRef(r, "加保日期"): new}, f"第 {r} 列加保日期 {old} 改成 {new}"


def both_unchanged(report, rng):
    """有效中的單筆保單，加保別誤填 XED → L1502、L1304。"""
    r = _pick(rng, [
        rows[0] for rows in _policies(report)
        if len(rows) == 1 and report.row(rows[0])["退保別"] == NOT_CHANGED
    ])
    if r is None:
        return None
    return {CellRef(r, "加保別"): NOT_CHANGED}, f"第 {r} 列加保別 NEW 改成 XED"


def unchanged_with_date(report, rng):
    """退保別是 XED（沒異動）卻填了退保日期 → L1504。"""
    r = _pick(rng, [i for i, row in enumerate(report.rows, 1) if row["退保別"] == NOT_CHANGED])
    if r is None:
        return None
    new = _d(min(_parse(report.row(r)["加保日期"]) + timedelta(days=rng.randint(10, 90)), _YEAR_END))
    return {CellRef(r, "退保日期"): new}, f"第 {r} 列（XED）退保日期改成 {new}"


def ended_without_date(report, rng):
    """終止或變更的那筆漏填退保日期 → L1504（後面還有一筆時也會觸發 L1305）。"""
    r = _pick(rng, [i for i, row in enumerate(report.rows, 1) if row["退保別"] != NOT_CHANGED])
    if r is None:
        return None
    return {CellRef(r, "退保日期"): NO_DATE}, f"第 {r} 列退保日期改成 00000000"


def bad_entry_date(report, rng):
    """加保日期不是合法日期（例如 0931、0229、13 月）→ L1402。"""
    r = rng.randint(1, len(report.rows))
    old = report.row(r)["加保日期"]
    new = old[:4] + rng.choice(("0931", "0229", "1301", "0431", "0631"))
    return {CellRef(r, "加保日期"): new}, f"第 {r} 列加保日期 {old} 改成 {new}"


def bad_exit_date(report, rng):
    """退保日期不是合法日期 → L1602。"""
    r = _pick(rng, [i for i, row in enumerate(report.rows, 1) if row["退保日期"] != NO_DATE])
    if r is None:
        return None
    old = report.row(r)["退保日期"]
    new = old[:4] + rng.choice(("0931", "0229", "1301", "1131"))
    return {CellRef(r, "退保日期"): new}, f"第 {r} 列退保日期 {old} 改成 {new}"


def exit_before_entry(report, rng):
    """最後一筆的退保日期早於加保日期 → L1607。"""
    r = _pick(rng, [
        rows[-1] for rows in _policies(report) if report.row(rows[-1])["退保日期"] != NO_DATE
    ])
    if r is None:
        return None
    old = report.row(r)["退保日期"]
    new = _d(_parse(report.row(r)["加保日期"]) - timedelta(days=rng.randint(5, 40)))
    return {CellRef(r, "退保日期"): new}, f"第 {r} 列退保日期 {old} 改成 {new}（早於加保日）"


MUTATIONS: dict[str, Mutation] = {
    f.__name__: f
    for f in (
        seq_skip, seq_single, first_terminated, new_not_first, new_date_missing, chain_code,
        chain_date, both_unchanged, unchanged_with_date, ended_without_date, bad_entry_date,
        bad_exit_date, exit_before_entry,
    )
}


def make_cases(count: int, seed: int = 0, policies: int = 8) -> list[Case]:
    """依序輪流用每種弄壞方式，產生 count 筆案例；同一個 seed 每次產生的都一樣。"""
    cases: list[Case] = []
    names = list(MUTATIONS)
    attempt = 0
    while len(cases) < count:
        name = names[len(cases) % len(names)]
        rng = random.Random(f"{seed}-{len(cases)}-{attempt}")
        case_id = f"case-{len(cases) + 1:03d}"
        clean = clean_life_report(rng, policies, report_id=case_id)
        result = MUTATIONS[name](clean, rng)
        attempt += 1
        if result is None:  # 這份報表剛好沒有適合的位置，換一份再試
            continue
        changes, description = result
        changed = {ref: clean.get(ref) for ref, value in changes.items() if clean.get(ref) != value}
        if not changed:
            continue
        cases.append(Case(case_id, name, description, clean, clean.with_changes(changes), changed))
        attempt = 0
    return cases
