"""稽核紀錄：每一次判定、AI 原始回覆、重驗結果都寫下來。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from once_wrong.report import CellRef


class AuditLog(Protocol):
    def record(self, event: str, **data: Any) -> None: ...


def _default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, CellRef):
        return {"row": value.row, "column": value.column}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "value"):  # Enum
        return value.value
    return str(value)


class JsonlAuditLog:
    """一行一筆 JSON，方便事後查和比對。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, **data: Any) -> None:
        entry = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=_default) + "\n")


class MemoryAuditLog:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(self, event: str, **data: Any) -> None:
        self.entries.append({"event": event, **data})
