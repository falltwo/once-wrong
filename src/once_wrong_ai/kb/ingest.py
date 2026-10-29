"""把填報手冊（PDF / docx）切成段落。

切法：
- 依章節標題（壹、貳、… / 一、二、…；docx 用標題樣式）記錄每段所在的章節。
- 遇到新標題、換頁、或累積超過 MAX_CHARS 就切一段。
- docx 的表格逐列轉成「欄 | 欄 | 欄」，每段都帶表頭和表格標題，
  檢核規則表因此大致是一列一條規則。
- 依章節名稱判斷段落種類（檢核規則、代號表、欄位說明、範例）。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from once_wrong_ai.kb.models import Passage, PassageKind

MAX_CHARS = 1500

_TOP_HEADING = re.compile(r"^\s*(壹拾[壹貳參肆伍陸柒捌玖]?|[壹貳參肆伍陸柒捌玖拾])\s*[、．.]\s*(\S.{0,40})$")
_SUB_HEADING = re.compile(r"^\s*([一二三四五六七八九十]{1,3})\s*[、．]\s*(\S.{0,40})$")
_DOT_LEADER = re.compile(r"(\.{6,}|…{3,}|．{6,})")
_TABLE_TITLE = re.compile(r"^\s*表\s*\d+(?:\s*[．.]\s*\d+)*")
# 標題後面黏著的頁碼，例如「伍、統計用資料儲存媒體格式及製作說明 伍-1」
_TRAILING_PAGE_LABEL = re.compile(r"\s+(?:[壹貳參肆伍陸柒捌玖拾]+-)?\d+\s*$")


# 欄位說明的小標，例如「2. 保單編號」「7. 保險金額(原幣金額)」
_FIELD_ITEM = re.compile(r"^\s*\d{1,2}\s*[.．]\s*([^\s\d=＝][^=＝]{0,24})$")


@dataclass
class _Line:
    text: str
    page: int | None = None
    heading: tuple[int, str] | None = None
    """(層級, 標題文字)"""
    caption: bool = False
    field: str | None = None
    """欄位說明的欄位名稱（這行是某個欄位說明的開頭）"""
    table: list[list[str]] | None = None


def field_key(name: str) -> str:
    """欄位名稱比對用：去空白、全形括號轉半形。"""
    name = re.sub(r"\s+", "", name).replace("（", "(").replace("）", ")")
    return name.rstrip("：:。")


def classify(section: list[str], caption: str | None = None, text: str = "") -> PassageKind:
    joined = " ".join(section)
    if len(_DOT_LEADER.findall(text)) >= 3:
        return PassageKind.TOC
    if "檢核" in joined:
        return PassageKind.RULE
    if (caption and _TABLE_TITLE.match(caption)) or re.search(r"代[號碼]表|對照表", caption or ""):
        return PassageKind.CODE_TABLE
    if "範例" in joined:
        return PassageKind.EXAMPLE
    if "欄位" in joined or "資料格式" in joined:
        return PassageKind.FIELD
    return PassageKind.OTHER


# ---- 讀檔 ----


def _pdf_lines(path: Path) -> Iterator[_Line]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    for page_no, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        is_toc_page = len(_DOT_LEADER.findall(text)) >= 3
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            heading = None
            if not is_toc_page and not _DOT_LEADER.search(line):
                if m := _TOP_HEADING.match(line):
                    heading = (1, f"{m.group(1)}、{_TRAILING_PAGE_LABEL.sub('', m.group(2)).strip()}")
                elif m := _SUB_HEADING.match(line):
                    heading = (2, f"{m.group(1)}、{_TRAILING_PAGE_LABEL.sub('', m.group(2)).strip()}")
            if heading is None and _TABLE_TITLE.match(line) and len(line.strip()) <= 50:
                yield _Line(line.strip(), page=page_no, caption=True)
                continue
            field = None
            if heading is None and (m := _FIELD_ITEM.match(line)):
                field = field_key(m.group(1))
            yield _Line(line, page=page_no, heading=heading, field=field)


def _docx_heading_level(style_name: str) -> int | None:
    if "表格標題" in style_name:
        return None
    if m := re.search(r"(?:Heading|標題)\s*(\d)", style_name):
        return int(m.group(1))
    return None


def _docx_lines(path: Path) -> Iterator[_Line]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(str(path))
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, document)
            text = p.text.strip()
            if not text:
                continue
            style = p.style.name if p.style is not None else ""
            level = _docx_heading_level(style)
            if level is not None and level <= 3 and "目錄" not in style:
                yield _Line(text, heading=(level, text))
            elif "表格標題" in style:
                yield _Line(text, caption=True)
            elif "欄位+標號" in style:
                yield _Line(text, field=field_key(text))
            elif not style.lower().startswith("toc"):
                yield _Line(text)
        elif tag == "tbl":
            table = Table(child, document)
            rows = []
            for row in table.rows:
                cells = []
                for cell in row.cells:
                    value = " ".join(cell.text.split())
                    # 合併儲存格會重複出現，同一列只留一次
                    if not cells or cells[-1] != value:
                        cells.append(value)
                if any(cells):
                    rows.append(cells)
            if rows:
                yield _Line("", table=rows)


# ---- 切段 ----


class _Chunker:
    def __init__(self, manual: str, product: str, id_prefix: str):
        self.manual = manual
        self.product = product
        self.id_prefix = id_prefix
        self.section: list[str] = []
        self.caption: str | None = None
        self.buffer: list[str] = []
        self.page: int | None = None
        self.field: str | None = None
        self.passages: list[Passage] = []

    def set_heading(self, level: int, title: str) -> None:
        self.flush()
        self.section = self.section[: level - 1] + [title]
        self.caption = None
        self.field = None

    def start_field(self, name: str) -> bool:
        """遇到欄位說明的小標就另起一段；檢核規則章節裡不切（那裡的編號是條件，不是欄位）。"""
        if any("檢核" in s for s in self.section):
            return False
        self.flush()
        self.caption = None
        self.field = name
        return True

    def set_caption(self, caption: str) -> None:
        self.flush()
        self.caption = caption

    def add_text(self, line: str, page: int | None) -> None:
        if page != self.page:
            self.flush()
            self.page = page
        if self.buffer and sum(len(x) + 1 for x in self.buffer) + len(line) > MAX_CHARS:
            self.flush()
        self.buffer.append(line)

    def add_table(self, rows: list[list[str]]) -> None:
        self.flush()
        header, body = rows[0], rows[1:] or []
        head = " | ".join(header)
        group: list[str] = []
        for row in body or [header]:
            line = " | ".join(row)
            if group and len(head) + sum(len(x) + 1 for x in group) + len(line) > MAX_CHARS:
                self._emit([head, *group], caption=self.caption)
                group = []
            group.append(line)
        self._emit([head, *group] if body else group, caption=self.caption)
        self.caption = None

    def flush(self) -> None:
        if self.buffer:
            self._emit(self.buffer, caption=self.caption)
            self.buffer = []

    def _emit(self, lines: list[str], caption: str | None) -> None:
        text = "\n".join(lines).strip()
        if len(text) < 20:
            return
        if caption:
            text = f"{caption}\n{text}"
        kind = classify(self.section, caption, text)
        self.passages.append(
            Passage(
                id=f"{self.id_prefix}-{len(self.passages) + 1:04d}",
                product=self.product,
                manual=self.manual,
                section=list(self.section),
                kind=kind,
                text=text,
                page=self.page,
                caption=caption,
                extra={"field": self.field} if self.field else {},
            )
        )


def ingest(path: str | Path, *, product: str, manual: str | None = None, id_prefix: str | None = None) -> list[Passage]:
    path = Path(path)
    manual = manual or path.stem
    chunker = _Chunker(manual, product, id_prefix or manual)
    lines = _pdf_lines(path) if path.suffix.lower() == ".pdf" else _docx_lines(path)

    for line in lines:
        if line.heading:
            chunker.set_heading(*line.heading)
            chunker.add_text(line.text, line.page)
        elif line.caption:
            chunker.set_caption(line.text)
        elif line.field:
            chunker.start_field(line.field)
            chunker.add_text(line.text, line.page)
        elif line.table is not None:
            chunker.add_table(line.table)
        else:
            chunker.add_text(line.text, line.page)
    chunker.flush()
    return chunker.passages
