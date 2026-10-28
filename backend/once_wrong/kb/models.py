from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class PassageKind(str, Enum):
    RULE = "rule"
    """檢核規則、錯誤代碼表"""
    CODE_TABLE = "code_table"
    """代號表，例如「表3．1．1 公司簡稱與代號表」"""
    FIELD = "field"
    """欄位說明"""
    EXAMPLE = "example"
    """範例說明"""
    TOC = "toc"
    """目錄，不參與檢索"""
    OTHER = "other"


@dataclass
class Passage:
    id: str
    product: str
    manual: str
    section: list[str]
    kind: PassageKind
    text: str
    page: int | None = None
    """PDF 的頁碼（從 1 開始）；docx 沒有頁碼。"""
    caption: str | None = None
    """表格標題（有的話）。"""
    extra: dict = field(default_factory=dict)

    @property
    def source(self) -> str:
        where = f" p.{self.page}" if self.page else ""
        path = " › ".join(self.section)
        return f"{self.manual}{where}" + (f" › {path}" if path else "")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Passage:
        return cls(**{**d, "kind": PassageKind(d["kind"])})
