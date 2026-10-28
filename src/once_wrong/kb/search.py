"""從知識庫找出跟一筆檢核錯誤有關的手冊段落。

不用向量資料庫：檢核編號、欄位名稱、表號都是精確字串，直接比對最準；
剩下的用 BM25（中文取相鄰兩字）補上。

給一筆錯誤找段落的順序：
1. 含有這個檢核編號的檢核規則段落
2. 規則裡提到的代號表（例如「表3．1．1」）
3. 出錯欄位的欄位說明
4. 都找不到時，用規則說明全文搜尋檢核規則
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

from once_wrong.kb.ingest import field_key
from once_wrong.kb.models import Passage, PassageKind

_CJK = r"㐀-鿿"
_CJK_GAP = re.compile(rf"(?<=[{_CJK}])[ \t　]+(?=[{_CJK}])")
_TABLE_REF = re.compile(r"表\s*\d+(?:\s*[．.]\s*\d+)*(?:\s*[．.]\s*[A-Z](?![A-Za-z]))?")


def normalize(text: str) -> str:
    """去掉 PDF 抽字時插在中文字之間的空白（「保 險 金 額」→「保險金額」）。"""
    return _CJK_GAP.sub("", text)


def tokenize(text: str) -> list[str]:
    text = normalize(text)
    tokens = [w.lower() for w in re.findall(r"[A-Za-z0-9_]+", text)]
    for run in re.findall(rf"[{_CJK}]+", text):
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1)) if len(run) > 1 else tokens.append(run)
    return tokens


def table_key(ref: str) -> str:
    return re.sub(r"\s+", "", ref).replace("．", ".")


def code_pattern(code: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])")


class _BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tfs = [Counter(d) for d in docs]
        self.lengths = [len(d) for d in docs]
        self.avg = sum(self.lengths) / max(len(docs), 1)
        df = Counter(t for tf in self.tfs for t in tf)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, i: int, query: Iterable[str]) -> float:
        tf, length = self.tfs[i], self.lengths[i]
        s = 0.0
        for t in set(query):
            f = tf.get(t)
            if f:
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self.avg))
        return s


class Retriever:
    def __init__(self, passages: list[Passage]):
        self.passages = [p for p in passages if p.kind is not PassageKind.TOC]
        self._norm = [normalize(p.text) for p in self.passages]
        self._bm25 = _BM25([tokenize(p.text) for p in self.passages])

    @classmethod
    def from_dir(cls, kb_dir: str) -> Retriever:
        from once_wrong.kb.store import load

        return cls(load(kb_dir))

    def _indices(self, product: str | None, kinds: set[PassageKind] | None = None) -> list[int]:
        return [
            i
            for i, p in enumerate(self.passages)
            if (product is None or p.product == product) and (kinds is None or p.kind in kinds)
        ]

    def find_code(self, code: str, product: str | None = None, limit: int = 2) -> list[Passage]:
        pattern = code_pattern(code)
        hits = [i for i in self._indices(product, {PassageKind.RULE}) if pattern.search(self._norm[i])]
        return [self.passages[i] for i in hits[:limit]]

    def code_context(self, passage: Passage, code: str, before: int = 1, after: int = 2) -> str:
        """規則段落裡，這個檢核編號附近的幾行（用來找它引用的代號表）。"""
        lines = normalize(passage.text).splitlines()
        if passage.page is None:
            # docx 表格一列就是一條規則，不需要看前後列
            before = after = 0
        pattern = code_pattern(code)
        keep: set[int] = set()
        for i, line in enumerate(lines):
            if pattern.search(line):
                keep.update(range(max(0, i - before), min(len(lines), i + after + 1)))
        return "\n".join(lines[i] for i in sorted(keep))

    def find_field(self, name: str, product: str | None = None, limit: int = 2) -> list[Passage]:
        """欄位說明：切段時已標記欄位名稱的段落（說明本文優先，其次是它底下的代號表）。"""
        key = field_key(name)
        hits = [
            self.passages[i]
            for i in self._indices(product, {PassageKind.FIELD, PassageKind.CODE_TABLE, PassageKind.OTHER})
            if self.passages[i].extra.get("field") == key
        ]
        hits.sort(key=lambda p: p.kind is not PassageKind.FIELD)
        return hits[:limit]

    def find_table(self, ref: str, product: str | None = None, limit: int = 1) -> list[Passage]:
        key = table_key(ref)
        hits = []
        for i in self._indices(product):
            caption = self.passages[i].caption
            if caption and table_key(caption).startswith(key):
                rest = table_key(caption)[len(key):]
                # 「表3.1.1」不可以配到「表3.1.12」
                if not rest[:1].isdigit():
                    hits.append(self.passages[i])
        return hits[:limit]

    def search(
        self,
        query: str,
        product: str | None = None,
        kinds: set[PassageKind] | None = None,
        must_contain: Iterable[str] = (),
        limit: int = 3,
    ) -> list[Passage]:
        q = tokenize(query)
        required = [normalize(m) for m in must_contain if m]
        scored = []
        for i in self._indices(product, kinds):
            s = self._bm25.score(i, q)
            # 段落裡真的出現欄位名稱的，排前面
            s += 5 * sum(1 for m in required if m in self._norm[i])
            if s > 0:
                scored.append((s, i))
        scored.sort(reverse=True)
        return [self.passages[i] for _, i in scored[:limit]]

    def for_violation(
        self,
        rule_id: str,
        fields: list[str],
        description: str = "",
        product: str | None = None,
        budget_chars: int = 6000,
    ) -> list[Passage]:
        picked: list[Passage] = []

        rule_passages = self.find_code(rule_id, product)
        picked += rule_passages

        context = "\n".join(self.code_context(p, rule_id) for p in rule_passages)
        refs = {table_key(m) for m in _TABLE_REF.findall(context + "\n" + description)}
        for ref in sorted(refs)[:3]:
            picked += self.find_table(ref, product)

        query = " ".join([*fields, description])
        for name in fields:
            found = self.find_field(name, product)
            picked += found or self.search(
                query, product, {PassageKind.FIELD, PassageKind.CODE_TABLE}, must_contain=[name], limit=1
            )

        if not rule_passages:
            picked += self.search(query, product, {PassageKind.RULE}, must_contain=fields, limit=2)

        result, seen, used = [], set(), 0
        for p in picked:
            if p.id in seen:
                continue
            if used + len(p.text) > budget_chars and result:
                continue
            seen.add(p.id)
            used += len(p.text)
            result.append(p)
        return result
