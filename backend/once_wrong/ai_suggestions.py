"""Adapt the AI review package to the demo API's stored R-01/R-07 reports."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from once_wrong.ai_review.audit import JsonlAuditLog
from once_wrong.ai_review.llm import GeminiClient, GeminiConfig, LLMError
from once_wrong.ai_review.reviewer import AIReviewer
from once_wrong.kb.memory import RuleMemory
from once_wrong.kb.search import Retriever
from once_wrong.kb.store import PASSAGES_FILE
from once_wrong.report import Cell, Report
from once_wrong.rules import RuleSet, Violation
from once_wrong.rules.examples import OpeningEqualsClosing, RequiredField

from .models import Suggestion
from .storage import Store
from .validation import ApiError


class _UnavailableLLM:
    """Keep report review available when a model key is not configured."""

    model_name = "unavailable"

    def __init__(self, reason: str):
        self.reason = reason

    def explain(self, system_prompt: str, user_prompt: str):
        raise LLMError(self.reason)


def _reviewer(root: Path) -> AIReviewer:
    try:
        llm = GeminiClient(GeminiConfig.from_env())
    except (LLMError, ImportError) as error:
        llm = _UnavailableLLM(str(error))

    kb_path = Path(os.environ.get("ONCE_WRONG_KB_PATH", root / "data" / "kb"))
    knowledge = None
    if (kb_path / PASSAGES_FILE).is_file():
        try:
            knowledge = Retriever.from_dir(str(kb_path))
        except (OSError, ValueError):
            # A missing or unreadable manual index should not break deterministic checks.
            knowledge = None

    notes_path = Path(os.environ.get("ONCE_WRONG_RULE_NOTES", root / "config" / "rule_notes.jsonl"))
    audit_path = Path(os.environ.get("ONCE_WRONG_AUDIT_PATH", root / "logs" / "audit.jsonl"))
    return AIReviewer(
        llm,
        _demo_rules(),
        audit=JsonlAuditLog(audit_path),
        knowledge=knowledge,
        memory=RuleMemory(notes_path),
    )


def _demo_rules() -> RuleSet:
    """Use the API CSV's English column names with the shared review pipeline."""
    return RuleSet(
        [
            RequiredField(rule_id="R-01", column="product"),
            OpeningEqualsClosing(
                rule_id="R-07", closing_column="previous", opening_column="opening"
            ),
        ]
    )


def _cell_value(value: Cell) -> str | int | None:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _to_api_suggestion(item, report: Report, model: str) -> Suggestion:
    verified = None
    if item.suggestion is not None:
        changes = []
        for ref, value in item.suggestion.changes.items():
            row = report.row(ref.row)
            changes.append(
                {
                    "rowId": str(row.get("id", ref.row)),
                    "row": ref.row,
                    "column": ref.column,
                    "value": _cell_value(value),
                }
            )
        verified = {
            "reason": item.suggestion.reason,
            "changes": changes,
            "verification": "passed",
        }

    return Suggestion(
        title=item.title,
        explanation=item.explanation,
        source=item.source.value,
        verification="passed" if verified else "unavailable",
        suggestion=verified,
        rejectedSuggestions=[rejected.why for rejected in item.rejected],
        citations=[
            {
                "id": passage.id,
                "source": passage.source,
                "section": passage.section,
                "page": passage.page,
            }
            for passage in item.sources
        ],
        blockedNumbers=item.blocked_numbers,
        model=model,
    )


def get_ai_suggestion(store: Store, version_id: str, issue_id: str) -> dict:
    version = store.get_version(version_id)
    issue = next((entry for entry in version["issues"] if entry["id"] == issue_id), None)
    if issue is None:
        raise ApiError(404, "ISSUE_NOT_FOUND", "此修訂找不到指定問題。")

    rows = [
        {
            "id": row["id"],
            "product": row["product"],
            "previous": row["previous"],
            "opening": row["opening"],
        }
        for row in version["rows"]
    ]
    report = Report(
        report_id=version.get("reportId", version_id),
        version=version["number"],
        columns=["id", "product", "previous", "opening"],
        rows=rows,
        numeric_columns={"previous", "opening"},
        meta={"期間": version.get("period", "")},
    )
    rules = _demo_rules()
    violations = rules.check(report)
    row_number = next(
        (index for index, row in enumerate(rows, start=1) if row["id"] == issue["rowId"]),
        None,
    )
    violation: Violation | None = next(
        (
            candidate
            for candidate in violations
            if candidate.rule_id == issue["ruleId"] and row_number in candidate.rows
        ),
        None,
    )
    if violation is None:
        raise ApiError(409, "ISSUE_NOT_REVIEWABLE", "此問題與目前示範規則不一致，無法產生 AI 說明。")

    root = Path(__file__).resolve().parents[2]
    reviewer = _reviewer(root)
    result = reviewer.review_violation(report, violation, violations)
    # Keep the model identifier truthful even if the reviewer fell back before a call.
    return _to_api_suggestion(
        result, report, getattr(reviewer.llm, "model_name", "unknown")
    ).model_dump(mode="json")
