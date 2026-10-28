"""知識庫的存放：切好的段落存成 JSONL，之後每次審核直接讀，不必重新解析手冊。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from once_wrong_ai.kb.ingest import ingest
from once_wrong_ai.kb.models import Passage

PASSAGES_FILE = "passages.jsonl"


@dataclass
class ManualEntry:
    path: str
    product: str
    """險別，例如「個人壽險」。審核時用報表的險別篩選段落。"""
    name: str | None = None
    id_prefix: str | None = None


def load_manifest(path: str | Path) -> list[ManualEntry]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ManualEntry(**entry) for entry in data["manuals"]]


def build(manifest: list[ManualEntry], root: str | Path = ".") -> list[Passage]:
    root = Path(root)
    passages: list[Passage] = []
    for entry in manifest:
        passages.extend(
            ingest(root / entry.path, product=entry.product, manual=entry.name, id_prefix=entry.id_prefix)
        )
    ids = [p.id for p in passages]
    if len(ids) != len(set(ids)):
        raise ValueError("段落編號重複，請在 manifest 給每本手冊不同的 id_prefix")
    return passages


def save(passages: list[Passage], out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / PASSAGES_FILE
    with out.open("w", encoding="utf-8") as f:
        for p in passages:
            f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")
    return out


def load(kb_dir: str | Path) -> list[Passage]:
    path = Path(kb_dir) / PASSAGES_FILE
    with path.open(encoding="utf-8") as f:
        return [Passage.from_dict(json.loads(line)) for line in f if line.strip()]
