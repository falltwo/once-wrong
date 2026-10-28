"""報表的資料結構。

列號一律從 1 開始（跟畫面上的「第 3 列」一致），欄位用欄名指定。
"""

from __future__ import annotations

import copy
import csv
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

Cell = int | Decimal | str | None

_LEADING_ZERO = re.compile(r"^-?0\d")


@dataclass(frozen=True, order=True)
class CellRef:
    row: int
    column: str


@dataclass
class Report:
    report_id: str
    version: int
    columns: list[str]
    rows: list[dict[str, Cell]]
    numeric_columns: set[str] = field(default_factory=set)
    meta: dict[str, Any] = field(default_factory=dict)
    # 跨月勾稽用：上一期的報表（沒有就是 None）
    previous: Report | None = None

    def get(self, ref: CellRef) -> Cell:
        return self.rows[ref.row - 1].get(ref.column)

    def row(self, row: int) -> dict[str, Cell]:
        return self.rows[row - 1]

    def has_cell(self, ref: CellRef) -> bool:
        return 1 <= ref.row <= len(self.rows) and ref.column in self.columns

    def with_changes(self, changes: dict[CellRef, Cell]) -> Report:
        """回傳套用修改後的副本，原報表不動。"""
        rows = copy.deepcopy(self.rows)
        for ref, value in changes.items():
            rows[ref.row - 1][ref.column] = value
        return Report(
            report_id=self.report_id,
            version=self.version,
            columns=list(self.columns),
            rows=rows,
            numeric_columns=set(self.numeric_columns),
            meta=dict(self.meta),
            previous=self.previous,
        )

    def parse_value(self, column: str, text: str | None) -> Cell:
        """把文字轉成該欄位的型別；數字欄位解析失敗會丟 ValueError。"""
        if text is None or text.strip() == "":
            return None
        text = text.strip()
        if column in self.numeric_columns:
            number = parse_number(text)
            if number is None:
                raise ValueError(f"欄位 {column} 需要數字，收到 {text!r}")
            return number
        return text

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        report_id: str | None = None,
        version: int = 1,
        meta: dict[str, Any] | None = None,
    ) -> Report:
        """讀 CSV。整欄（忽略空白格）都能解析成數字的，視為數字欄位。

        有前置 0 的欄位（例如公司代號「01」、異動序號「00001」）是代碼，保留成文字。
        """
        path = Path(path)
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            columns = list(reader.fieldnames or [])
            raw_rows = [dict(r) for r in reader]

        def values(col: str) -> list[str]:
            return [v for r in raw_rows if (v := (r.get(col) or "").strip())]

        numeric = {
            col
            for col in columns
            if values(col)
            and all(parse_number(v) is not None and not _LEADING_ZERO.match(v) for v in values(col))
        }
        report = cls(
            report_id=report_id or path.stem,
            version=version,
            columns=columns,
            rows=[],
            numeric_columns=numeric,
            meta=meta or {},
        )
        report.rows = [
            {col: report.parse_value(col, r.get(col)) for col in columns} for r in raw_rows
        ]
        return report


def parse_number(text: str) -> int | Decimal | None:
    """解析「12,480,000」「-3.5」這類數字；不是數字回傳 None。"""
    cleaned = text.strip().replace(",", "").replace("，", "")
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return int(value) if value == value.to_integral_value() and "." not in cleaned else value


def format_cell(value: Cell) -> str:
    if value is None:
        return "（空白）"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, Decimal):
        return f"{value:,}"
    return str(value)
