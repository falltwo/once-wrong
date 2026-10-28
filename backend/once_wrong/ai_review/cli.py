"""示範指令：讀一份 CSV 報表，跑示範規則，再請 Gemini 說明每個錯誤。

    # 準備金月報（簡報第 8 頁的示意）
    python -m once_wrong.ai_review.cli examples/mock_reserve_2026-09.csv --period 2026-09

    # 個人壽險承保資料，用真實規則 L0302 / L0303，並從填報手冊知識庫找依據
    python -m once_wrong.ai_review.cli examples/mock_life_policies_2025.csv --rules life --product 個人壽險
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from once_wrong.ai_review.audit import JsonlAuditLog
from once_wrong.ai_review.llm import GeminiClient, GeminiConfig, LLMError
from once_wrong.ai_review.models import ExplanationSource
from once_wrong.ai_review.reviewer import PRODUCT_META_KEY, AIReviewer
from once_wrong.kb.memory import RuleMemory
from once_wrong.kb.search import Retriever
from once_wrong.kb.store import PASSAGES_FILE
from once_wrong.report import Report, format_cell
from once_wrong.rules.examples import example_rules, life_example_rules

RULE_SETS = {"demo": example_rules, "life": life_example_rules}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Once Wrong AI 審核示範")
    parser.add_argument("csv", help="報表 CSV（UTF-8）")
    parser.add_argument("--version", type=int, default=1, help="報表版本，預設 1")
    parser.add_argument("--period", help="報表期間，例如 2026-09")
    parser.add_argument("--product", help="險別，例如 個人壽險；用來篩選手冊段落")
    parser.add_argument("--rules", choices=RULE_SETS, default="demo", help="用哪組示範規則")
    parser.add_argument("--kb", default="data/kb", help="知識庫資料夾（不存在就不查手冊）")
    parser.add_argument("--notes", default="config/rule_notes.jsonl", help="團隊規則備忘")
    parser.add_argument("--audit", default="logs/audit.jsonl", help="稽核紀錄位置")
    args = parser.parse_args(argv)

    meta = {}
    if args.period:
        meta["期間"] = args.period
    if args.product:
        meta[PRODUCT_META_KEY] = args.product
    report = Report.from_csv(args.csv, version=args.version, meta=meta)

    try:
        llm = GeminiClient(GeminiConfig.from_env())
    except LLMError as e:
        print(e, file=sys.stderr)
        return 2

    knowledge = Retriever.from_dir(args.kb) if (Path(args.kb) / PASSAGES_FILE).exists() else None
    if knowledge is None:
        print(f"（找不到知識庫 {args.kb}，這次不查填報手冊）\n")

    reviewer = AIReviewer(
        llm,
        RULE_SETS[args.rules](),
        JsonlAuditLog(args.audit),
        knowledge=knowledge,
        memory=RuleMemory(args.notes),
    )
    items = reviewer.review(report)

    print(f"{report.report_id} 第 {report.version} 版：{len(items)} 項錯誤（模型 {llm.model_name}）\n")
    for item in items:
        rows = ",".join(map(str, item.violation.rows))
        print(f"[{item.violation.rule_id}] 第 {rows} 列｜{item.title}")
        print(f"  {item.explanation}")
        if item.source is not ExplanationSource.AI:
            print(f"  （AI 說明未採用：{item.source.value}"
                  + (f"，對不上的數字：{', '.join(item.blocked_numbers)}" if item.blocked_numbers else "")
                  + "）")
        if item.suggestion:
            changes = "、".join(
                f"第 {ref.row} 列「{ref.column}」改為 {format_cell(v)}" for ref, v in item.suggestion.changes.items()
            )
            print(f"  建議：{changes}（已用規則重驗：通過）")
        if item.rejected:
            print(f"  另有 {len(item.rejected)} 個建議重驗不通過，已擋下")
        for p in item.sources:
            print(f"  依據：{p.source}")
        print()

    print(f"稽核紀錄：{args.audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
