"""組 prompt。

只把出錯的那幾列，加上規則指定的相關列（例如同一保單的其他筆），送給 AI，
不送整份報表（資料最小化；正式資料也不可送外部 AI）。
手冊段落和團隊備忘由審核流程先找好，跟著錯誤一起送。
"""

from __future__ import annotations

import json

from once_wrong_ai.kb.memory import RuleNote
from once_wrong_ai.kb.models import Passage
from once_wrong_ai.report import Report, format_cell
from once_wrong_ai.rules import Rule, Violation

SYSTEM_PROMPT = """\
你是保險公司的報表檢核助手，負責向填表的同事說明檢核錯誤，並提出修法建議。

規則：
1. 錯誤已經由檢核規則判定，你不需要也不可以推翻判定。
2. 說明要用白話的繁體中文，讓不熟規則的人也看得懂。
3. 說明要依據提供的「填報手冊段落」和「團隊備忘」；手冊沒寫的不要猜，並把用到的段落編號放進 citations。
   團隊備忘是團隊確認過的解讀，跟手冊段落衝突時以團隊備忘為準。
4. 說明裡出現的數字，只能來自「程式算好的數字」、「出錯的資料列」、「相關資料列」和你引用的段落，不可以自己計算或推估新的數字。
   數字照原樣寫阿拉伯數字（例如 12,480,000），不要換算成「萬」「億」或百分比。
5. 修法建議只能修改「出錯的資料列」裡的格子，欄位名稱必須跟報表完全相同。
   「相關資料列」只供判斷（例如同一保單的其他筆），不可以修改；如果要改相關資料列才修得好，candidates 給空陣列，並在說明裡講清楚。
6. 如果資料不足以判斷怎麼改，candidates 給空陣列，並在說明裡講清楚需要人確認什麼。
   如果有「同一列的其他錯誤」，優先給一次能把這些錯誤一起修好的修法，不要只顧眼前這一條而留下另一條。
7. 最多給 3 個修法建議，最可能的放第一個。
"""


def passage_label(index: int) -> str:
    return f"K{index + 1}"


def build_user_prompt(
    report: Report,
    violation: Violation,
    rule: Rule,
    passages: list[Passage] = (),
    notes: list[RuleNote] = (),
    related: list[Violation] = (),
) -> str:
    """related：同一列上其他規則判定的錯誤，讓 AI 給一次修好的建議。"""
    def row_payload(r: int) -> dict:
        return {"列號": r, **{col: format_cell(report.row(r).get(col)) for col in report.columns}}

    rows = [row_payload(r) for r in violation.rows]
    payload = {
        "報表": {"代號": report.report_id, "版本": report.version, **report.meta},
        "欄位": report.columns,
        "數字欄位": sorted(report.numeric_columns),
        "規則": {"代碼": violation.rule_id, "內容": rule.description},
        "錯誤": violation.message,
        "出錯的格子": [{"列號": c.row, "欄位": c.column} for c in violation.cells],
        "程式算好的數字": {k: format_cell(v) for k, v in violation.facts.items()},
        "出錯的資料列": rows,
    }
    if violation.reference_rows:
        payload["相關資料列"] = [row_payload(r) for r in violation.reference_rows]
    if related:
        payload["同一列的其他錯誤"] = [{"規則": v.rule_id, "錯誤": v.message} for v in related]
    if notes:
        payload["團隊備忘"] = [n.note for n in notes]
    if passages:
        payload["填報手冊段落"] = [
            {"編號": passage_label(i), "來源": p.source, "內容": p.text} for i, p in enumerate(passages)
        ]
    return (
        "以下是一筆檢核錯誤，請說明並提出修法建議。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    )
