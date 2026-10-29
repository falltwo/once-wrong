"""Bridge immutable API versions to the shared AI review implementation."""

import copy
import hashlib
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
from once_wrong_ai.report import Report

from .filing import FILING_SCHEMA_PROFILE, LIFE_UW, evaluate_filing
from .models import DataRow
from .validation import (
    LIFE_COLUMNS,
    REQUIRED_COLUMNS,
    ApiError,
    report_for_version,
    rules_for_profile,
)

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


class _MetadataOnlyAudit:
    def record(self, event, **data):
        # Persistent review evidence is written by Store. Avoid retaining full
        # prompts and provider output in a shared reviewer's in-memory log.
        return None


def _outbound_report(report, profile):
    columns = list(REQUIRED_COLUMNS if profile == "demo_csv_v1" else LIFE_COLUMNS)
    rows = [{column: row[column] for column in columns} for row in report.rows]
    identity = "id" if profile == "demo_csv_v1" else "保單編號"
    for row in rows:
        raw = str(row[identity]).encode("utf-8")
        row[identity] = "POLICY_" + hashlib.sha256(raw).hexdigest()[:16]
    return Report(
        report_id=report.report_id, version=report.version, columns=columns, rows=rows,
        numeric_columns=set(report.numeric_columns), meta={"險別": "個人壽險"}
        if profile != "demo_csv_v1" else {},
    )


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
                self.llm, rules_for_profile(profile), audit=_MetadataOnlyAudit(),
                knowledge=knowledge, memory=memory,
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
        if version["schemaProfileId"] == FILING_SCHEMA_PROFILE:
            return self._review_filing(version, report_id, issue_id)
        return self._review_single(version, report_id, issue_id)

    def _review_single(self, version: dict, report_id: str, issue_id: str) -> dict:
        reviewer = self.reviewers[version["schemaProfileId"]]
        original = report_for_version(version, report_id)
        report = _outbound_report(original, version["schemaProfileId"])
        before = reviewer.rules.check(report)

        def row_id(row: int) -> str:
            if version["schemaProfileId"] == PROFILES[0]:
                return str(original.rows[row - 1]["id"])
            return str(row)

        violation = find_violation(before, issue_id, row_id)
        if violation is None:
            raise ApiError(404, "ISSUE_NOT_FOUND", "此修訂找不到指定問題。")

        try:
            item = reviewer.review_violation(report, violation, before)
            payload = suggestion_payload(item, self.llm.model_name, row_id).model_dump()
            payload["_candidates"] = []
            for candidate in item.candidates:
                state, reason = candidate.revalidation, candidate.reason
                if candidate.suggestion:
                    invalid = self._invalid_candidate(
                        version, original, candidate.suggestion.changes
                    )
                    if invalid:
                        state, reason = "invalid_target", invalid
                changes = [
                    {"rowId": row_id(change.row) if 1 <= change.row <= len(original.rows)
                     else f"invalid-row:{change.row}", "row": change.row,
                     "column": change.column, "value": change.new_value}
                    for change in candidate.raw.changes
                ]
                payload["_candidates"].append({
                    "rank": candidate.rank, "reason": candidate.raw.reason,
                    "revalidation": state,
                    "rejectionReason": None if state == "passed" else reason,
                    "changes": changes, "blockedNumbers": candidate.blocked_numbers,
                })
            if item.suggestion:
                invalid = self._invalid_candidate(version, original, item.suggestion.changes)
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

    def _review_filing(self, version, report_id, issue_id):
        current = evaluate_filing(
            version["files"], rules=self.reviewers["life_underwriting_v1"].rules
        )
        issue = next((item for item in current["issues"] if item["id"] == issue_id), None)
        if issue is None:
            raise ApiError(404, "ISSUE_NOT_FOUND", "此修訂找不到指定問題。")
        source = next(file for file in version["files"] if file["id"] == issue["fileId"])
        known = {rule.rule_id for rule in self.reviewers["life_underwriting_v1"].rules.rules}
        if source["datasetType"] != LIFE_UW or issue["ruleId"] not in known:
            return {
                "title": issue["title"],
                "explanation": "此跨檔或給付檢查目前提供規則說明；修法須人工核對原始證據。",
                "suggestion": None, "rejectedSuggestions": [], "citations": [],
                "blockedNumbers": [], "model": self.llm.model_name,
                "verification": "unavailable", "source": "fallback_llm_error",
                "_candidates": [],
            }
        single = {
            "schemaProfileId": "life_underwriting_v1", "number": version["number"],
            "columns": list(LIFE_COLUMNS),
            "rows": [{"id": str(row["row"]), "row": row["row"], "values": row["values"]}
                     for row in source["rows"]],
        }
        payload = self._review_single(single, report_id, issue["localIssueId"])
        before_keys = {item["issueKey"] for item in current["issues"]}
        for candidate in payload.get("_candidates", []):
            for change in candidate["changes"]:
                change.update(
                    fileId=source["id"], datasetType=LIFE_UW,
                    rowId=f"{source['id']}:{change['row']}",
                )
            if candidate["revalidation"] != "passed":
                continue
            trial = copy.deepcopy(version["files"])
            target = next(file for file in trial if file["id"] == source["id"])
            for change in candidate["changes"]:
                target["rows"][change["row"] - 1]["values"][change["column"]] = change["value"]
            after_keys = {item["issueKey"] for item in evaluate_filing(
                trial, rules=self.reviewers["life_underwriting_v1"].rules
            )["issues"]}
            if issue["issueKey"] in after_keys or after_keys - before_keys:
                candidate["revalidation"] = "failed"
                candidate["rejectionReason"] = "整組申報重驗後原錯誤仍存在或產生新的跨檔錯誤。"
                payload["rejectedSuggestions"].append(candidate["rejectionReason"])
        accepted = next((candidate for candidate in payload.get("_candidates", [])
                         if candidate["revalidation"] == "passed"), None)
        if accepted and accepted.get("blockedNumbers"):
            payload["source"] = "fallback_number_guard"
            payload["title"] = f"{issue['ruleId']} 未通過"
            payload["explanation"] = issue["title"]
            payload["blockedNumbers"] = list(dict.fromkeys([
                *payload["blockedNumbers"], *accepted["blockedNumbers"]
            ]))
        payload["suggestion"] = (
            {"reason": accepted["reason"] if payload["source"] == "ai" else "",
             "verification": "passed", "changes": accepted["changes"]}
            if accepted else None
        )
        payload["verification"] = "passed" if accepted else "unavailable"
        return payload

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
