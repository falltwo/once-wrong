"""數字守門：AI 說明裡的每個數字，都必須能在資料或程式算好的數字裡找到。

對不上就整段攔下，改顯示規則的固定說明。寧可說得不漂亮，也不能說錯數字。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from once_wrong_ai.report import Report
from once_wrong_ai.rules import Violation

# 規則代碼、險種代碼這類「英文-數字」的代號不算數字（例如 R-07、ML-05）
_CODE = re.compile(r"[A-Za-z]+-?\d+")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def extract_numbers(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text)
    text = _CODE.sub(" ", text)
    return [m.group().rstrip(",") for m in _NUMBER.finditer(text)]


def _normalize(token: str) -> Decimal | None:
    try:
        return abs(Decimal(token.replace(",", ""))).normalize()
    except InvalidOperation:
        return None


def _collect(values: Iterable[object]) -> set[Decimal]:
    allowed: set[Decimal] = set()
    for value in values:
        if value is None:
            continue
        for token in extract_numbers(str(value)):
            number = _normalize(token)
            if number is not None:
                allowed.add(number)
    return allowed


def allowed_numbers(report: Report, violation: Violation, extra: Iterable[object] = ()) -> set[Decimal]:
    """AI 可以引用的數字：程式算好的數字、出錯列和相關列上的值、列號、報表資訊、通過重驗的建議值。"""
    shown_rows = [*violation.rows, *violation.reference_rows]
    sources: list[object] = [*violation.facts.values(), *shown_rows, report.version, *report.meta.values()]
    for r in shown_rows:
        sources.extend(report.row(r).values())
    sources.extend(extra)
    return _collect(sources)


def find_unsupported_numbers(texts: Iterable[str], allowed: set[Decimal]) -> list[str]:
    unsupported = []
    for text in texts:
        for token in extract_numbers(text):
            number = _normalize(token)
            if number is None or number not in allowed:
                unsupported.append(token)
    return unsupported
