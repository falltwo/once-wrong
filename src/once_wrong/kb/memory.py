"""規則備忘：手冊沒講清楚、或團隊已經確認過的解讀，記一次就一直用。

例如「L0302：新契約只有一筆時填 00000，不是 00001」。審核時會連同手冊段落一起
給 AI，而且標明是團隊確認過的說法。存成 JSONL，人可以直接編輯、也可以進版控。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path


@dataclass
class RuleNote:
    rule_id: str
    note: str
    product: str | None = None
    """None 表示所有險別都適用"""
    author: str | None = None
    added: str | None = None


class RuleMemory:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.notes: list[RuleNote] = []
        if self.path.exists():
            with self.path.open(encoding="utf-8") as f:
                self.notes = [RuleNote(**json.loads(line)) for line in f if line.strip()]

    def notes_for(self, rule_id: str, product: str | None = None) -> list[RuleNote]:
        return [
            n
            for n in self.notes
            if n.rule_id == rule_id and (n.product is None or product is None or n.product == product)
        ]

    def add(self, rule_id: str, note: str, product: str | None = None, author: str | None = None) -> RuleNote:
        entry = RuleNote(rule_id, note, product, author, date.today().isoformat())
        self.notes.append(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        return entry
