"""Bridge immutable API versions to the shared AI review implementation."""

import logging
import os
from pathlib import Path

from pydantic import ValidationError

from once_wrong_ai.ai_review.api import find_violation, suggestion_payload
from once_wrong_ai.ai_review.llm import DEFAULT_MODEL, LLMClient, LLMError, llm_from_env
from once_wrong_ai.ai_review.models import ExplanationSource, ReviewItem
from once_wrong_ai.ai_review.reviewer import AIReviewer
from once_wrong_ai.kb.memory import RuleMemory
from once_wrong_ai.kb.search import Retriever

from .models import DataRow
from .validation import ApiError, report_for_version, rules_for_profile

LOGGER = logging.getLogger(__name__)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROFILES = ("demo_csv_v1", "life_underwriting_v1")


def _configured_path(value: str | Path | None, env: str, default: str) -> Path:
    path = Path(value if value is not None else os.environ.get(env) or default)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def _model_from_env() -> str:
    provider = (os.environ.get("ONCE_WRONG_PROVIDER") or "").strip().lower()
    if provider == "openrouter" or (not provider and os.environ.get("OPENROUTER_API_KEY")):
        from once_wrong_ai.ai_review.openrouter import DEFAULT_MODEL as OPENROUTER_MODEL

        return os.environ.get("OPENROUTER_MODEL") or OPENROUTER_MODEL
    return os.environ.get("ONCE_WRONG_MODEL") or DEFAULT_MODEL


class _UnavailableLLM:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def explain(self, system_prompt: str, user_prompt: str):
        raise LLMError("AI client is unavailable")


class _ResilientLLM:
    """Normalize SDK/network failures to the reviewer's documented fallback."""

    def __init__(self, client: LLMClient):
        self.client = client
        self.model_name = client.model_name

    def explain(self, system_prompt: str, user_prompt: str):
        try:
            return self.client.explain(system_prompt, user_prompt)
        except LLMError:
            raise
        except Exception as error:
            # Do not expose provider payloads or credentials in API responses/logs.
            raise LLMError(f"AI request failed ({type(error).__name__})") from error


class ReviewService:
    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        kb_dir: str | Path | None = None,
        memory_path: str | Path | None = None,
    ):
        self.configured = True
        if llm is None:
            try:
                llm = llm_from_env()
            except Exception as error:
                LOGGER.warning("AI client unavailable (%s)", type(error).__name__)
                llm = _UnavailableLLM(_model_from_env())
                self.configured = False
        self.llm = _ResilientLLM(llm)

        knowledge_path = _configured_path(kb_dir, "ONCE_WRONG_KB", "data/kb")
        knowledge = None
        if (knowledge_path / "passages.jsonl").is_file():
            try:
                knowledge = Retriever.from_dir(str(knowledge_path))
            except (OSError, ValueError, TypeError, KeyError) as error:
                LOGGER.warning("Knowledge base unavailable (%s)", type(error).__name__)

        notes_path = _configured_path(
            memory_path, "ONCE_WRONG_RULE_MEMORY", "config/rule_notes.jsonl"
        )
        memory = None
        try:
            memory = RuleMemory(notes_path)
        except (OSError, ValueError, TypeError) as error:
            LOGGER.warning("Rule notes unavailable (%s)", type(error).__name__)

        self.knowledge_available = bool(knowledge and knowledge.passages)
        self.reviewers = {
            profile: AIReviewer(
                self.llm, rules_for_profile(profile), knowledge=knowledge, memory=memory
            )
            for profile in PROFILES
        }

    @property
    def health(self) -> dict:
        return {
            "configured": self.configured,
            "model": self.llm.model_name,
            "knowledgeBase": self.knowledge_available,
        }

    def review(self, version: dict, report_id: str, issue_id: str) -> dict:
        reviewer = self.reviewers[version["schemaProfileId"]]
        report = report_for_version(version, report_id)
        before = reviewer.rules.check(report)

        def row_id(row: int) -> str:
            if version["schemaProfileId"] == PROFILES[0]:
                return str(report.rows[row - 1]["id"])
            return str(row)

        violation = find_violation(before, issue_id, row_id)
        if violation is None:
            raise ApiError(404, "ISSUE_NOT_FOUND", "此修訂找不到指定問題。")

        try:
            item = reviewer.review_violation(report, violation, before)
            payload = suggestion_payload(item, self.llm.model_name, row_id).model_dump()
            if item.suggestion:
                invalid = self._invalid_candidate(version, report, item.suggestion.changes)
                if invalid:
                    payload["suggestion"] = None
                    payload["verification"] = "unavailable"
                    payload["rejectedSuggestions"].append(invalid)
            return payload
        except Exception as error:
            # Optional AI/retrieval/formatting failures must never block data repair.
            LOGGER.warning("AI review unavailable (%s)", type(error).__name__)
            item = ReviewItem(
                violation=violation,
                title=f"{violation.rule_id} 未通過",
                explanation=violation.message,
                source=ExplanationSource.FALLBACK_LLM_ERROR,
                suggestion=None,
            )
            return suggestion_payload(item, self.llm.model_name, row_id).model_dump()

    @staticmethod
    def _invalid_candidate(version: dict, report, changes: dict) -> str | None:
        if version["schemaProfileId"] == "life_underwriting_v1":
            if any(not isinstance(value, str) for value in changes.values()):
                return "修法不符合壽險資料格式：所有欄位必須保留文字值。"
            return None
        if any(ref.column == "id" for ref in changes):
            return "修法不可以修改資料列的識別碼。"
        candidate = report.with_changes(changes)
        try:
            for row in candidate.rows:
                DataRow.model_validate(row, strict=True)
        except ValidationError:
            return "修法不符合示範資料格式：金額須為非負安全整數，文字欄位不可為 null。"
        return None
