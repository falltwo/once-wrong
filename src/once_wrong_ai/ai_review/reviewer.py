"""AI 審核流程（簡報六步驟的第 3、4 步）。

對每一筆規則判定的錯誤：
1. 從填報手冊知識庫找出這條規則、相關欄位和代號表的段落，連同團隊備忘一起準備好。
2. 只把出錯的列（加上規則指定的相關列、同一列的其他錯誤）和這些段落送給 AI，請它用白話說明並提出修法。
3. 每個修法先套到副本上重跑規則；沒過、或產生新錯的，直接擋下不給人看。
4. 說明裡的數字對不上資料或引用段落，整段攔下，改用規則的固定說明。
5. 全部寫進稽核紀錄。

AI 失敗時流程不中斷，退回規則的固定說明。
"""

from __future__ import annotations

from once_wrong_ai.ai_review.audit import AuditLog, MemoryAuditLog
from once_wrong_ai.ai_review.guard import allowed_numbers, find_unsupported_numbers
from once_wrong_ai.ai_review.llm import LLMClient, LLMError
from once_wrong_ai.ai_review.models import (
    ExplanationSource,
    FixSuggestion,
    RejectedSuggestion,
    ReviewItem,
)
from once_wrong_ai.ai_review.prompts import SYSTEM_PROMPT, build_user_prompt, passage_label
from once_wrong_ai.ai_review.validation import validate_candidate
from once_wrong_ai.kb.memory import RuleMemory
from once_wrong_ai.kb.models import Passage
from once_wrong_ai.kb.search import Retriever
from once_wrong_ai.report import Report
from once_wrong_ai.rules import RuleSet, Violation

PRODUCT_META_KEY = "險別"


class AIReviewer:
    def __init__(
        self,
        llm: LLMClient,
        rules: RuleSet,
        audit: AuditLog | None = None,
        knowledge: Retriever | None = None,
        memory: RuleMemory | None = None,
        max_candidates: int = 3,
        context_budget_chars: int = 6000,
    ):
        self.llm = llm
        self.rules = rules
        self.audit = audit or MemoryAuditLog()
        self.knowledge = knowledge
        self.memory = memory
        self.max_candidates = max_candidates
        self.context_budget_chars = context_budget_chars

    def review(self, report: Report) -> list[ReviewItem]:
        violations = self.rules.check(report)
        self.audit.record(
            "rule_check",
            report_id=report.report_id,
            version=report.version,
            violations=[{"rule_id": v.rule_id, "cells": list(v.cells), "message": v.message} for v in violations],
        )
        return [self.review_violation(report, v, violations) for v in violations]

    def context_for(self, report: Report, violation: Violation) -> list[Passage]:
        if self.knowledge is None:
            return []
        rule = self.rules.get(violation.rule_id)
        fields = list(dict.fromkeys(c.column for c in violation.cells))
        return self.knowledge.for_violation(
            violation.rule_id,
            fields,
            rule.description,
            product=report.meta.get(PRODUCT_META_KEY),
            budget_chars=self.context_budget_chars,
        )

    def review_violation(self, report: Report, violation: Violation, before: list[Violation]) -> ReviewItem:
        rule = self.rules.get(violation.rule_id)
        passages = self.context_for(report, violation)
        notes = self.memory.notes_for(violation.rule_id, report.meta.get(PRODUCT_META_KEY)) if self.memory else []
        related = related_violations(violation, before)
        user_prompt = build_user_prompt(report, violation, rule, passages, notes, related)
        base = {
            "report_id": report.report_id,
            "version": report.version,
            "rule_id": violation.rule_id,
            "cells": list(violation.cells),
            "model": self.llm.model_name,
            "passages": [p.id for p in passages],
        }

        try:
            ai = self.llm.explain(SYSTEM_PROMPT, user_prompt)
        except LLMError as e:
            self.audit.record("ai_error", **base, error=str(e))
            return self._fallback(violation, ExplanationSource.FALLBACK_LLM_ERROR)

        labels = {passage_label(i): p for i, p in enumerate(passages)}
        cited = [labels[c] for c in dict.fromkeys(ai.citations) if c in labels]

        accepted = None
        rejected: list[RejectedSuggestion] = []
        for candidate in ai.candidates[: self.max_candidates]:
            outcome = validate_candidate(report, violation, candidate, self.rules, before)
            if outcome.passed and accepted is None:
                accepted = outcome.suggestion
            elif not outcome.passed:
                rejected.append(RejectedSuggestion(outcome.suggestion, candidate, outcome.why))

        shown_texts = [ai.title, ai.explanation] + ([accepted.reason] if accepted else [])
        extra = [
            *(accepted.changes.values() if accepted else []),
            *(p.text for p in cited),
            *(n.note for n in notes),
            *(v.message for v in related),
        ]
        unsupported = find_unsupported_numbers(shown_texts, allowed_numbers(report, violation, extra))

        self.audit.record(
            "ai_review",
            **base,
            prompt=user_prompt,
            ai_output=ai,
            cited=[p.id for p in cited],
            accepted=_changes(accepted),
            rejected=[{"raw": r.raw, "why": r.why} for r in rejected],
            unsupported_numbers=unsupported,
        )

        if unsupported:
            item = self._fallback(violation, ExplanationSource.FALLBACK_NUMBER_GUARD)
            # 修法本身已通過規則重驗，可以留著；但 AI 寫的理由一起被攔下
            if accepted:
                item.suggestion = FixSuggestion(changes=accepted.changes, reason="")
            item.rejected = rejected
            item.blocked_numbers = unsupported
            item.sources = cited
            return item

        return ReviewItem(
            violation=violation,
            title=ai.title,
            explanation=ai.explanation,
            source=ExplanationSource.AI,
            suggestion=accepted,
            rejected=rejected,
            sources=cited,
        )

    @staticmethod
    def _fallback(violation: Violation, source: ExplanationSource) -> ReviewItem:
        return ReviewItem(
            violation=violation,
            title=f"{violation.rule_id} 未通過",
            explanation=violation.message,
            source=source,
            suggestion=None,
        )


def related_violations(violation: Violation, violations: list[Violation]) -> list[Violation]:
    """同一列上其他規則判定的錯誤。"""
    return [v for v in violations if v.key != violation.key and set(v.rows) & set(violation.rows)]


def _changes(suggestion: FixSuggestion | None) -> list[dict] | None:
    if suggestion is None:
        return None
    return [{"cell": ref, "new_value": value} for ref, value in suggestion.changes.items()]
