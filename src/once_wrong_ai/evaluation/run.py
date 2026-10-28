"""AI 審核評分：產生案例 → 跑真的 Gemini → 跟標準答案比對 → 算出各項比率。

    # 先看會產生哪些案例，不呼叫 AI
    python -m once_wrong_ai.evaluation.run --cases 39 --dry-run

    # 實際評分（每筆錯誤一次 Gemini 呼叫）
    python -m once_wrong_ai.evaluation.run --cases 39 --workers 4

    # 合併多次結果（例如不同 seed），不呼叫 AI
    python -m once_wrong_ai.evaluation.run --combine logs/eval/A logs/eval/B logs/eval/C

結果寫在 logs/eval/<時間>/：summary.md（摘要）、summary.json（給 API／前端用）、run.json（這次的設定）、
items.jsonl（每筆錯誤的評分）、cases.jsonl（案例與標準答案）、audit.jsonl（AI 原始回覆）。

每筆錯誤的判定：
- 推得出原值：被弄壞的格子在 AI 可以改的列上，而且送給 AI 的資料裡有線索推回原值
  （例如序號要連續、加保日要等於上一筆的退保日）。
  - 修回原值：AI 的修法通過重驗，而且改的每一格都等於原本的值。
  - 另一種修法：通過重驗，但跟原值不同（規則過了，資料不一定對）。
- 推不出原值：資料裡沒有答案（例如漏填的日期是哪一天）。不給修法、請人確認才是好的反應；
  給了修法就是用猜的，就算規則過了也可能是錯的資料。
- 要動到別列：要改 AI 不能改的列才修得好。同樣是不給修法比較好。
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from once_wrong_ai.ai_review.audit import JsonlAuditLog, _default
from once_wrong_ai.ai_review.llm import LLMClient, LLMError, llm_from_env
from once_wrong_ai.ai_review.models import AIExplanation, ExplanationSource, ReviewItem
from once_wrong_ai.ai_review.reviewer import AIReviewer, related_violations
from once_wrong_ai.evaluation.cases import Case, make_cases
from once_wrong_ai.kb.memory import RuleMemory
from once_wrong_ai.kb.search import Retriever
from once_wrong_ai.kb.store import PASSAGES_FILE
from once_wrong_ai.report import CellRef
from once_wrong_ai.rules import Violation
from once_wrong_ai.rules.life import life_field_rules

_RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL")


class RetryingLLM:
    """評分時遇到限流或暫時錯誤就等一下重試，避免把「沒打到」算成 AI 答錯。"""

    def __init__(self, llm: LLMClient, attempts: int = 5, wait: float = 5.0):
        self.llm = llm
        self.model_name = llm.model_name
        self.attempts = attempts
        self.wait = wait

    def explain(self, system_prompt: str, user_prompt: str) -> AIExplanation:
        for attempt in range(self.attempts):
            try:
                return self.llm.explain(system_prompt, user_prompt)
            except LLMError as e:
                if attempt == self.attempts - 1 or not any(code in str(e) for code in _RETRYABLE):
                    raise
                time.sleep(self.wait * 2**attempt)
        raise AssertionError("unreachable")


class LockedAuditLog:
    def __init__(self, inner: JsonlAuditLog):
        self.inner = inner
        self._lock = threading.Lock()

    def record(self, event: str, **data: Any) -> None:
        with self._lock:
            self.inner.record(event, **data)


_ALWAYS_INFERABLE = {
    "seq_skip", "seq_single",  # 序號依序排列
    "first_terminated", "chain_code", "chain_date",  # 前後筆要接得上
    "both_unchanged",  # 只有一筆的保單，加保別只能是 NEW
    "unchanged_with_date",  # XED 的退保日一定是 00000000
}
_INFERABLE_IF_SHOWN = {"ended_without_date", "bad_entry_date", "bad_exit_date"}
"""日期類：原本的日期出現在送給 AI 的其他格子（例如相鄰那筆）才推得出來。"""


def answer_status(case: Case, violation: Violation, violations: list[Violation] = ()) -> str:
    """這筆錯誤的標準答案，AI 有沒有機會答對：inferable／unknowable／other_rows。

    violations 是整份報表的錯誤：同一列的其他錯誤會一起送給 AI，它們涉及的列也算 AI 看得到。
    """
    editable = set(violation.rows)
    if not all(ref.row in editable for ref in case.changed):
        return "other_rows"
    if case.mutation in _ALWAYS_INFERABLE:
        return "inferable"
    if case.mutation in _INFERABLE_IF_SHOWN:
        shown = [
            value
            for r in {
                *violation.rows,
                *violation.reference_rows,
                *(row for v in related_violations(violation, violations) for row in v.rows),
            }
            for column, value in case.report.row(r).items()
            if CellRef(r, column) not in case.changed
        ]
        if all(original in shown for original in case.changed.values()):
            return "inferable"
    return "unknowable"


@dataclass
class ItemScore:
    case_id: str
    mutation: str
    rule_id: str
    rows: list[int]
    source: str
    answer: str
    """inferable（推得出原值）／unknowable（推不出）／other_rows（要動到別列）。"""
    has_fix: bool
    restored: bool
    other_fix: bool
    abstained: bool
    """沒給任何修法（AI 自己判斷資料不足）。"""
    all_blocked: bool
    """給了修法但全部被規則重驗擋下。"""
    rejected: int
    cited_rule: bool
    """引用的手冊段落裡有這條規則的檢核編號。"""
    blocked_numbers: list[str]
    title: str
    explanation: str
    suggestion: dict[str, str] | None


def score_item(case: Case, item: ReviewItem, violations: list[Violation] = ()) -> ItemScore:
    v = item.violation
    fix = item.suggestion
    restored = bool(fix) and all(case.clean.get(ref) == value for ref, value in fix.changes.items())
    return ItemScore(
        case_id=case.case_id,
        mutation=case.mutation,
        rule_id=v.rule_id,
        rows=v.rows,
        source=item.source.value,
        answer=answer_status(case, v, violations),
        has_fix=fix is not None,
        restored=restored,
        other_fix=fix is not None and not restored,
        abstained=fix is None and not item.rejected,
        all_blocked=fix is None and bool(item.rejected),
        rejected=len(item.rejected),
        cited_rule=any(v.rule_id in p.text for p in item.sources),
        blocked_numbers=item.blocked_numbers,
        title=item.title,
        explanation=item.explanation,
        suggestion=(
            {f"第{ref.row}列 {ref.column}": str(value) for ref, value in fix.changes.items()} if fix else None
        ),
    )


def _rate(n: int, d: int) -> str:
    return f"{n}/{d}（{n / d:.0%}）" if d else "—"


def _what(s: ItemScore) -> str:
    if s.suggestion:
        return f"建議 {s.suggestion}"
    return "全被擋下" if s.all_blocked else "沒給修法"


@dataclass
class _Groups:
    scores: list[ItemScore]

    def __post_init__(self):
        s = self.scores
        self.ai = [x for x in s if x.source == ExplanationSource.AI.value]
        self.llm_errors = [x for x in s if x.source == ExplanationSource.FALLBACK_LLM_ERROR.value]
        self.guarded = [x for x in s if x.source == ExplanationSource.FALLBACK_NUMBER_GUARD.value]
        # 修法相關只看 AI 有回覆的（數字守門攔下的說明也算有回覆，修法仍保留）
        self.answered = [x for x in s if x.source != ExplanationSource.FALLBACK_LLM_ERROR.value]
        self.inferable = [x for x in self.answered if x.answer == "inferable"]
        self.unknowable = [x for x in self.answered if x.answer == "unknowable"]
        self.other_rows = [x for x in self.answered if x.answer == "other_rows"]
        self.should_abstain = self.unknowable + self.other_rows
        self.restored = sum(x.restored for x in self.inferable)
        self.held_back = sum(not x.has_fix for x in self.should_abstain)
        # 處理正確：推得出就修回原值，推不出或要動別列就不給修法
        self.correct = self.restored + self.held_back


def summarize(scores: list[ItemScore], n_cases: int, model: str) -> str:
    g = _Groups(scores)
    ai, guarded, answered = g.ai, g.guarded, g.answered
    inferable, unknowable, other_rows, should_abstain = g.inferable, g.unknowable, g.other_rows, g.should_abstain
    llm_errors = len(g.llm_errors)

    lines = [
        f"# AI 審核評分（{model}）",
        "",
        f"{n_cases} 個案例、{len(scores)} 筆錯誤。資料是程式產生的虛構個人壽險承保資料，每個案例弄壞一處。",
        "",
        "## 總覽",
        "",
        "| 指標 | 結果 |",
        "|---|---|",
        f"| 處理正確（推得出就修回、推不出就不給修法） | {_rate(g.correct, len(answered))} |",
        f"| AI 說明採用率 | {_rate(len(ai), len(scores))} |",
        f"| 數字守門攔下 | {_rate(len(guarded), len(scores))} |",
        f"| 呼叫失敗（重試後仍失敗） | {_rate(llm_errors, len(scores))} |",
        f"| 引用到正確規則的手冊段落 | {_rate(sum(s.cited_rule for s in answered), len(answered))} |",
        f"| 推得出原值時，修回原值 | {_rate(sum(s.restored for s in inferable), len(inferable))} |",
        f"| 推不出原值或要動別列時，不亂給修法 | {_rate(sum(not s.has_fix for s in should_abstain), len(should_abstain))} |",
        "",
        "## 推得出原值",
        "",
        "送給 AI 的資料裡有線索推回原值（序號要連續、前後筆要接得上等）。",
        "",
        "| 結果 | 筆數 |",
        "|---|---|",
        f"| 修回原值 | {_rate(sum(s.restored for s in inferable), len(inferable))} |",
        f"| 另一種修法（規則過了，但跟原值不同） | {_rate(sum(s.other_fix for s in inferable), len(inferable))} |",
        f"| 沒給修法 | {_rate(sum(s.abstained for s in inferable), len(inferable))} |",
        f"| 給了但全被重驗擋下 | {_rate(sum(s.all_blocked for s in inferable), len(inferable))} |",
        "",
        "## 推不出原值，或要動到別列",
        "",
        "資料裡沒有答案（例如漏填的日期是哪一天），或要改 AI 不能改的列。不給修法、請人確認是好的反應；"
        "給了修法就是用猜的，規則過了也可能是錯的資料。",
        "",
        "| 結果 | 推不出原值 | 要動到別列 |",
        "|---|---|---|",
        f"| 沒給修法 | {_rate(sum(s.abstained for s in unknowable), len(unknowable))} | "
        f"{_rate(sum(s.abstained for s in other_rows), len(other_rows))} |",
        f"| 給了通過重驗的修法（用猜的） | {_rate(sum(s.has_fix for s in unknowable), len(unknowable))} | "
        f"{_rate(sum(s.has_fix for s in other_rows), len(other_rows))} |",
        f"| 給了但全被重驗擋下 | {_rate(sum(s.all_blocked for s in unknowable), len(unknowable))} | "
        f"{_rate(sum(s.all_blocked for s in other_rows), len(other_rows))} |",
        "",
        f"重驗總共擋下 {sum(s.rejected for s in scores)} 個錯誤修法（沒給使用者看）。",
        "",
        "## 依規則",
        "",
        "| 規則 | 錯誤數 | 推得出原值 | 修回原值 | 推不出／別列 | 不亂給修法 | 引用正確 | 數字守門攔下 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    by_rule: dict[str, list[ItemScore]] = defaultdict(list)
    for s in answered:
        by_rule[s.rule_id].append(s)
    for rule_id in sorted(by_rule):
        group = by_rule[rule_id]
        inf = [s for s in group if s.answer == "inferable"]
        rest = [s for s in group if s.answer != "inferable"]
        lines.append(
            f"| {rule_id} | {len(group)} | {len(inf)} | {_rate(sum(s.restored for s in inf), len(inf))} | "
            f"{len(rest)} | {_rate(sum(not s.has_fix for s in rest), len(rest))} | "
            f"{_rate(sum(s.cited_rule for s in group), len(group))} | "
            f"{sum(s.source == ExplanationSource.FALLBACK_NUMBER_GUARD.value for s in group)} |"
        )

    misses = [s for s in inferable if not s.restored]
    if misses:
        lines += ["", "## 推得出原值、卻沒修回的", ""]
        lines += [f"- {s.case_id} {s.rule_id} 第 {','.join(map(str, s.rows))} 列（{s.mutation}）：{_what(s)}" for s in misses]
    guesses = [s for s in should_abstain if s.has_fix]
    if guesses:
        lines += ["", "## 推不出原值、卻給了修法的（用猜的）", ""]
        lines += [f"- {s.case_id} {s.rule_id} 第 {','.join(map(str, s.rows))} 列（{s.mutation}）：{_what(s)}" for s in guesses]
    if guarded:
        lines += ["", "## 被數字守門攔下的", ""]
        lines += [f"- {s.case_id} {s.rule_id}：對不上的數字 {', '.join(s.blocked_numbers)}" for s in guarded]
    return "\n".join(lines) + "\n"


def _ratio(n: int, d: int) -> dict:
    return {"count": n, "total": d, "rate": round(n / d, 4) if d else None}


def summary_json(scores: list[ItemScore], n_cases: int, model: str, runs: list[dict]) -> dict:
    """機器可讀的評分結果，給後端 API／前端測試結果頁用。欄位說明見 docs/ai-review-api.md。"""
    g = _Groups(scores)
    by_rule: dict[str, list[ItemScore]] = defaultdict(list)
    for s in g.answered:
        by_rule[s.rule_id].append(s)
    rules = []
    for rule_id in sorted(by_rule):
        r = _Groups(by_rule[rule_id])
        rules.append({
            "ruleId": rule_id,
            "violations": len(r.answered),
            "handledCorrectly": _ratio(r.correct, len(r.answered)),
            "restoredWhenInferable": _ratio(r.restored, len(r.inferable)),
            "heldBackWhenNotInferable": _ratio(r.held_back, len(r.should_abstain)),
            "citedRule": _ratio(sum(x.cited_rule for x in r.answered), len(r.answered)),
            "numberGuardBlocked": len(r.guarded),
        })
    return {
        "schemaVersion": 1,
        "model": model,
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataset": {
            "description": "程式產生的虛構個人壽險承保資料，每個案例弄壞一處，被改掉之前的值是標準答案",
            "product": "個人壽險",
            "rules": "life_field_rules（11 條）",
            "cases": n_cases,
            "violations": len(scores),
        },
        "runs": runs,
        "metrics": {
            "handledCorrectly": _ratio(g.correct, len(g.answered)),
            "restoredWhenInferable": _ratio(g.restored, len(g.inferable)),
            "heldBackWhenNotInferable": _ratio(g.held_back, len(g.should_abstain)),
            "citedRule": _ratio(sum(x.cited_rule for x in g.answered), len(g.answered)),
            "aiExplanationUsed": _ratio(len(g.ai), len(scores)),
            "numberGuardBlocked": _ratio(len(g.guarded), len(scores)),
            "llmErrors": _ratio(len(g.llm_errors), len(scores)),
        },
        "outcomes": {
            "inferable": {
                "restored": g.restored,
                "otherFix": sum(x.other_fix for x in g.inferable),
                "noFix": sum(x.abstained for x in g.inferable),
                "allBlocked": sum(x.all_blocked for x in g.inferable),
            },
            "unknowable": {
                "noFix": sum(x.abstained for x in g.unknowable),
                "guessedFix": sum(x.has_fix for x in g.unknowable),
                "allBlocked": sum(x.all_blocked for x in g.unknowable),
            },
            "otherRows": {
                "noFix": sum(x.abstained for x in g.other_rows),
                "guessedFix": sum(x.has_fix for x in g.other_rows),
                "allBlocked": sum(x.all_blocked for x in g.other_rows),
            },
            "rejectedByRevalidation": sum(x.rejected for x in scores),
        },
        "byRule": rules,
    }


def write_results(out: Path, scores: list[ItemScore], n_cases: int, model: str, runs: list[dict], note: str) -> str:
    summary = summarize(scores, n_cases, model) + f"\n{note}\n"
    (out / "summary.md").write_text(summary, encoding="utf-8")
    payload = summary_json(scores, n_cases, model, runs)
    (out / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def combine(dirs: list[Path], out_root: Path) -> Path:
    """合併多次評分（例如不同 seed）成一份 summary.md／summary.json。"""
    scores: list[ItemScore] = []
    runs: list[dict] = []
    for d in dirs:
        run_scores = [ItemScore(**json.loads(line)) for line in (d / "items.jsonl").open(encoding="utf-8")]
        meta = json.loads((d / "run.json").read_text(encoding="utf-8"))
        g = _Groups(run_scores)
        runs.append({**meta, "dir": d.name, "handledCorrectly": _ratio(g.correct, len(g.answered))})
        scores += run_scores
    out = out_root / f"combined-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    model = "、".join(sorted({r["model"] for r in runs}))
    seeds = "、".join(str(r["seed"]) for r in runs)
    write_results(out, scores, sum(r["cases"] for r in runs), model, runs, f"合併 {len(runs)} 次評分（seed {seeds}）。")
    return out


def _case_record(case: Case) -> dict:
    return {
        "case_id": case.case_id,
        "mutation": case.mutation,
        "description": case.description,
        "answer": [{"row": ref.row, "column": ref.column, "original": value} for ref, value in case.changed.items()],
        "rows": case.report.rows,
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Once Wrong AI 審核評分")
    parser.add_argument("--cases", type=int, default=39, help="案例數，預設 39（13 種弄壞方式各 3 筆）")
    parser.add_argument("--seed", type=int, default=0, help="同一個 seed 每次產生相同的案例")
    parser.add_argument("--policies", type=int, default=8, help="每份報表幾張保單")
    parser.add_argument("--workers", type=int, default=4, help="同時跑幾個案例")
    parser.add_argument("--kb", default="data/kb", help="知識庫資料夾")
    parser.add_argument("--notes", default="config/rule_notes.jsonl", help="團隊規則備忘")
    parser.add_argument("--out", default="logs/eval", help="結果資料夾")
    parser.add_argument("--dry-run", action="store_true", help="只產生案例、跑規則，不呼叫 AI")
    parser.add_argument("--combine", nargs="+", metavar="DIR", help="合併已跑完的評分結果資料夾，不呼叫 AI")
    args = parser.parse_args(argv)

    if args.combine:
        out = combine([Path(d) for d in args.combine], Path(args.out))
        print((out / "summary.md").read_text(encoding="utf-8"))
        print(f"結果：{out}")
        return 0

    rules = life_field_rules()
    cases = make_cases(args.cases, args.seed, args.policies)
    violations = {c.case_id: rules.check(c.report) for c in cases}
    total = sum(map(len, violations.values()))
    print(f"{len(cases)} 個案例、{total} 筆錯誤（每筆錯誤一次 AI 呼叫）")
    print("依規則：", dict(sorted(Counter(v.rule_id for vs in violations.values() for v in vs).items())))
    if args.dry_run:
        for c in cases:
            print(f"  {c.case_id} {c.mutation:20s} {c.description} → "
                  + "、".join(f"{v.rule_id}（第 {','.join(map(str, v.rows))} 列）" for v in violations[c.case_id]))
        return 0

    try:
        llm = RetryingLLM(llm_from_env())
    except LLMError as e:
        print(e, file=sys.stderr)
        return 2
    if not (Path(args.kb) / PASSAGES_FILE).exists():
        print(f"找不到知識庫 {args.kb}，請先建知識庫", file=sys.stderr)
        return 2

    out = Path(args.out) / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    reviewer = AIReviewer(
        llm,
        rules,
        LockedAuditLog(JsonlAuditLog(out / "audit.jsonl")),
        knowledge=Retriever.from_dir(args.kb),
        memory=RuleMemory(args.notes),
    )

    done = 0
    lock = threading.Lock()

    def run(case: Case) -> list[ItemScore]:
        nonlocal done
        before = rules.check(case.report)
        scores = [score_item(case, item, before) for item in reviewer.review(case.report)]
        with lock:
            done += 1
            print(f"  [{done}/{len(cases)}] {case.case_id} {case.mutation}：{len(scores)} 筆", flush=True)
        return scores

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        scores = [s for result in pool.map(run, cases) for s in result]

    with (out / "cases.jsonl").open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(_case_record(case), ensure_ascii=False, default=_default) + "\n")
    with (out / "items.jsonl").open("w", encoding="utf-8") as f:
        for s in scores:
            f.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")
    elapsed = round(time.monotonic() - started)
    meta = {
        "seed": args.seed, "cases": len(cases), "policies": args.policies,
        "violations": len(scores), "model": llm.model_name, "elapsedSeconds": elapsed,
    }
    if usage := getattr(llm.llm, "usage", None):
        meta["usage"] = usage.as_dict()
    (out / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = write_results(out, scores, len(cases), llm.model_name, [meta], f"耗時 {elapsed} 秒，seed={args.seed}。")

    print()
    print(summary)
    if usage := getattr(llm.llm, "usage", None):
        print(f"用量：{usage.summary()}")
    print(f"結果：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
