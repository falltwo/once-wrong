"""HTTP contracts shared by the backend and the AI review package.

LLMs are deterministic fakes: these tests never send uploaded data to a provider.
"""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from once_wrong.main import create_app
from once_wrong_ai.ai_review.llm import LLMError
from once_wrong_ai.ai_review.models import AIChange, AIExplanation, AIFixCandidate

REPORT_URL = "/reports/reserve-202609"
DEMO_CSV = b"id,product,previous,opening\nA,P,100,90\n"
VALID_DEMO_CSV = b"id,product,previous,opening\nA,P,100,100\n"
LIFE_COLUMNS = [
    "公司代號",
    "保單編號",
    "保單編號序號",
    "異動序號",
    "加保別",
    "加保日期",
    "退保別",
    "退保日期",
]
VALID_LIFE_CSV = (
    ",".join(LIFE_COLUMNS) + "\n01,A00001,0001,00000,NEW,20250115,XED,00000000\n"
).encode()
SUGGESTION_FIELDS = {
    "title",
    "explanation",
    "suggestion",
    "rejectedSuggestions",
    "citations",
    "blockedNumbers",
    "model",
    "verification",
    "source",
}


class FakeLLM:
    model_name = "fake-contract-model"

    def __init__(self, *replies: AIExplanation | Exception):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def explain(self, system_prompt: str, user_prompt: str) -> AIExplanation:
        self.prompts.append(user_prompt)
        if not self.replies:
            raise AssertionError("Unexpected LLM call")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def reply(*changes: tuple[int, str, str]) -> AIExplanation:
    candidates = []
    if changes:
        candidates.append(
            AIFixCandidate(
                reason="依據同列資料修正",
                changes=[
                    AIChange(row=row, column=column, new_value=value)
                    for row, column, value in changes
                ],
            )
        )
    return AIExplanation(
        title="請核對資料", explanation="欄位不符合檢核規則。", candidates=candidates
    )


def app(database_path: Path, llm: FakeLLM, **kwargs):
    return create_app(
        database_path,
        llm=llm,
        knowledge_dir=database_path.parent / "missing-kb",
        memory_path=database_path.parent / "missing-notes.jsonl",
        **kwargs,
    )


def upload(client: TestClient, content: bytes = DEMO_CSV) -> dict:
    response = client.post(
        f"{REPORT_URL}/versions", files={"file": ("contract.csv", content, "text/csv")}
    )
    assert response.status_code == 201, response.text
    return response.json()


def suggestion_url(version: dict, issue_id: str | None = None) -> str:
    issue_id = issue_id or version["issues"][0]["id"]
    return f"/versions/{version['id']}/issues/{quote(issue_id, safe='')}/suggestion"


def test_suggestion_returns_complete_verified_contract_lazily_and_persists_cache(
    database_path: Path,
):
    llm = FakeLLM(reply((1, "opening", "100")))
    with TestClient(app(database_path, llm, seed_demo=True)) as client:
        version = upload(client)
        before = client.get(REPORT_URL).json()
        assert llm.prompts == []
        first = client.get(suggestion_url(version))
        assert first.status_code == 200, first.text
        payload = first.json()
        assert set(payload) == SUGGESTION_FIELDS
        assert payload["source"] == "ai"
        assert payload["verification"] == "passed"
        assert payload["model"] == llm.model_name
        assert payload["suggestion"] == {
            "reason": "依據同列資料修正",
            "verification": "passed",
            "changes": [{"rowId": "A", "row": 1, "column": "opening", "value": 100}],
        }
        assert payload["rejectedSuggestions"] == []
        assert payload["citations"] == []
        assert payload["blockedNumbers"] == []
        assert client.get(suggestion_url(version)).json() == payload
        assert len(llm.prompts) == 1
        assert client.get(REPORT_URL).json() == before

    restarted_llm = FakeLLM()
    with TestClient(app(database_path, restarted_llm, seed_demo=False)) as restarted:
        assert restarted.get(suggestion_url(version)).json() == payload
        assert restarted_llm.prompts == []


@pytest.mark.parametrize("error", [LLMError("provider failed"), TimeoutError("timed out")])
def test_llm_failure_returns_full_fallback_and_can_retry(database_path: Path, error: Exception):
    llm = FakeLLM(error, reply())
    with TestClient(app(database_path, llm, seed_demo=True)) as client:
        version = upload(client)
        first = client.get(suggestion_url(version))
        assert first.status_code == 200, first.text
        payload = first.json()
        assert set(payload) == SUGGESTION_FIELDS
        assert payload["source"] == "fallback_llm_error"
        assert payload["verification"] == "unavailable"
        assert payload["suggestion"] is None
        assert payload["title"].strip() and payload["explanation"].strip()
        assert (
            payload["rejectedSuggestions"]
            == payload["citations"]
            == payload["blockedNumbers"]
            == []
        )
        retry = client.get(suggestion_url(version))
        assert retry.status_code == 200, retry.text
        assert retry.json()["source"] == "ai"
        assert retry.json()["verification"] == "unavailable"
        assert len(llm.prompts) == 2


def test_invalid_candidate_is_hidden_and_original_version_stays_unchanged(database_path: Path):
    llm = FakeLLM(reply((1, "opening", "95")))
    with TestClient(app(database_path, llm, seed_demo=True)) as client:
        version = upload(client)
        response = client.get(suggestion_url(version))
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["suggestion"] is None
        assert payload["verification"] == "unavailable"
        assert len(payload["rejectedSuggestions"]) == 1
        assert client.get(REPORT_URL).json()["versions"][-1] == version


@pytest.mark.parametrize(
    "changes",
    [
        ((1, "previous", "-1"), (1, "opening", "-1")),
        ((1, "previous", ""), (1, "opening", "")),
        ((1, "previous", "9007199254740992"), (1, "opening", "9007199254740992")),
        ((1, "id", ""), (1, "opening", "100")),
    ],
    ids=["negative-money", "null-money", "unsafe-money", "empty-id"],
)
def test_demo_candidates_must_obey_csv_schema_even_if_rules_pass(database_path: Path, changes):
    llm = FakeLLM(reply(*changes))
    with TestClient(app(database_path, llm, seed_demo=True)) as client:
        version = upload(client)
        response = client.get(suggestion_url(version))
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["suggestion"] is None
        assert payload["verification"] == "unavailable"
        assert payload["rejectedSuggestions"]


def test_life_candidate_cannot_replace_text_with_null(database_path: Path):
    invalid_sequence = VALID_LIFE_CSV.replace(b",00000,NEW,", b",00001,NEW,")
    llm = FakeLLM(reply((1, "異動序號", "00000"), (1, "公司代號", "")))
    with TestClient(app(database_path, llm, seed_demo=True)) as client:
        version = upload(client, invalid_sequence)
        response = client.get(suggestion_url(version, "1:L0302"))
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["suggestion"] is None
        assert payload["verification"] == "unavailable"
        assert payload["rejectedSuggestions"]


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/versions/missing/issues/A%3AR-07/suggestion", "VERSION_NOT_FOUND"),
        ("/versions/v2/issues/missing/suggestion", "ISSUE_NOT_FOUND"),
    ],
)
def test_unknown_suggestion_resources_do_not_call_llm(database_path: Path, path: str, code: str):
    llm = FakeLLM()
    with TestClient(app(database_path, llm, seed_demo=True)) as client:
        response = client.get(path)
        assert response.status_code == 404, response.text
        assert response.json()["code"] == code
        assert llm.prompts == []


def test_saved_forged_issue_is_not_authority_for_ai_review(database_path: Path):
    llm = FakeLLM()
    with TestClient(app(database_path, llm, seed_demo=True)) as client:
        version = upload(client, VALID_DEMO_CSV)
        version["issues"] = [
            {
                "id": "A:R-07",
                "ruleId": "R-07",
                "rowId": "A",
                "field": "opening",
                "title": "forged",
                "actual": 90,
                "expected": 100,
                "repeated": False,
            }
        ]
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE versions SET payload_json = ? WHERE id = ?",
                (json.dumps(version), version["id"]),
            )
        response = client.get(suggestion_url(version))
        assert response.status_code == 404, response.text
        assert response.json()["code"] == "ISSUE_NOT_FOUND"
        assert llm.prompts == []


def test_life_upload_returns_text_cells_context_repeated_and_rule_summary(database_path: Path):
    source = Path(__file__).resolve().parents[2] / "examples" / "mock_life_policies_2025.csv"
    content = source.read_bytes()
    llm = FakeLLM(reply())
    with TestClient(app(database_path, llm, seed_demo=True)) as client:
        version = upload(client, content)
        assert version["schemaProfileId"] == "life_underwriting_v1"
        assert version["ruleVersion"] == "life_field_rules_v1"
        assert version["columns"] == LIFE_COLUMNS
        assert version["rows"][0] == {
            "id": "1",
            "row": 1,
            "values": dict(
                zip(
                    LIFE_COLUMNS,
                    [
                        "01",
                        "A00001",
                        "0001",
                        "00000",
                        "NEW",
                        "20250115",
                        "XED",
                        "00000000",
                    ],
                    strict=True,
                )
            ),
        }
        assert all(
            isinstance(value, str) for row in version["rows"] for value in row["values"].values()
        )
        assert version["summary"]["totalChecks"] == len(version["rows"]) * 11
        failed = len(
            {(issue["ruleId"], row) for issue in version["issues"] for row in issue["rows"]}
        )
        assert version["summary"] == {
            "totalChecks": len(version["rows"]) * 11,
            "passedChecks": len(version["rows"]) * 11 - failed,
            "failedChecks": failed,
            "notEvaluatedChecks": 0,
        }
        assert all(issue["repeated"] is False for issue in version["issues"])
        issue = next(item for item in version["issues"] if item["id"] == "6:L0303")
        assert issue["rowIds"] == ["6"]
        assert issue["contextRowIds"] == ["7"]
        assert issue["facts"] == {"退保別": "DEA"}
        assert {cell["column"] for cell in issue["cells"]} == {"異動序號", "退保別"}
        assert all(cell["rowId"] == "6" for cell in issue["cells"])
        assert llm.prompts == []
        response = client.get(suggestion_url(version, "6:L0303"))
        assert response.status_code == 200, response.text
        assert response.json()["source"] == "ai"
        second = upload(client, content)
        assert all(item["repeated"] is True for item in second["issues"])
        stored = client.get(REPORT_URL).json()
        assert stored["versions"][-2:] == [version, second]
        listed = next(item for item in client.get("/reports").json() if item["id"] == stored["id"])
        assert listed == stored


def test_life_profile_is_used_for_submission_revalidation(database_path: Path):
    with TestClient(app(database_path, FakeLLM(), seed_demo=True)) as client:
        version = upload(client, VALID_LIFE_CSV)
        assert version["issues"] == []
        assert client.get(REPORT_URL).json()["canSubmit"] is True
        response = client.post(f"{REPORT_URL}/submissions", json={"versionId": version["id"]})
        assert response.status_code == 204, response.text
        assert client.get(REPORT_URL).json()["submittedVersionId"] == version["id"]


def test_create_report_uploads_first_version_atomically_without_seed(database_path: Path):
    llm = FakeLLM()
    with TestClient(app(database_path, llm, seed_demo=False)) as client:
        response = client.post(
            "/reports",
            data={"name": "個人壽險承保", "period": "2025-12"},
            files={"file": ("life.csv", VALID_LIFE_CSV, "text/csv")},
        )
        assert response.status_code == 201, response.text
        report = response.json()
        assert report["name"] == "個人壽險承保"
        assert report["period"] == "2025-12"
        assert len(report["versions"]) == 1
        version = report["versions"][0]
        assert version["number"] == 1 and version["schemaProfileId"] == "life_underwriting_v1"
        assert client.get(f"/reports/{report['id']}").json() == report
        assert client.get("/reports").json() == [report]
        assert client.get(f"/versions/{version['id']}/source").content == VALID_LIFE_CSV
        assert llm.prompts == []


@pytest.mark.parametrize(
    ("name", "content", "filename", "status"),
    [
        ("valid", b"bad-header\nvalue\n", "invalid.csv", 422),
        ("valid", VALID_DEMO_CSV, "not-csv.txt", 422),
        (" ", VALID_DEMO_CSV, "valid.csv", 422),
    ],
)
def test_failed_report_creation_leaves_no_empty_report(
    database_path: Path, name: str, content: bytes, filename: str, status: int
):
    with TestClient(app(database_path, FakeLLM(), seed_demo=False)) as client:
        response = client.post(
            "/reports",
            data={"name": name, "period": "2025-12"},
            files={"file": (filename, content, "text/csv")},
        )
        assert response.status_code == status, response.text
        assert client.get("/reports").json() == []


def test_evaluation_is_returned_unchanged_and_missing_file_has_specific_404(database_path: Path):
    evaluation_path = database_path.parent / "evaluation.json"
    evaluation = {
        "schemaVersion": 1,
        "model": "evaluation-model",
        "generatedAt": "2026-10-28T00:00:00Z",
        "dataset": {"cases": 3},
        "runs": [],
        "metrics": {"handledCorrectly": {"count": 0, "total": 0, "rate": None}},
        "outcomes": {},
        "byRule": [],
        "extraField": "保留原格式",
    }
    evaluation_path.write_text(json.dumps(evaluation, ensure_ascii=False), encoding="utf-8")
    with TestClient(
        app(database_path, FakeLLM(), seed_demo=False, evaluation_path=evaluation_path)
    ) as client:
        response = client.get("/evaluations/latest")
        assert response.status_code == 200, response.text
        assert response.json() == evaluation
        evaluation_path.unlink()
        missing = client.get("/evaluations/latest")
        assert missing.status_code == 404
        assert missing.json()["code"] == "EVALUATION_NOT_FOUND"


def test_health_reports_injected_ai_and_missing_optional_knowledge(database_path: Path):
    with TestClient(app(database_path, FakeLLM(), seed_demo=False)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["ai"] == {
            "configured": True,
            "model": "fake-contract-model",
            "knowledgeBase": False,
        }


def test_slow_synchronous_ai_call_does_not_block_event_loop(database_path: Path):
    entered, release = Event(), Event()

    class SlowLLM(FakeLLM):
        def explain(self, system_prompt: str, user_prompt: str) -> AIExplanation:
            entered.set()
            assert release.wait(timeout=10), "The test failed to release the LLM"
            return reply()

    with TestClient(app(database_path, SlowLLM(), seed_demo=True)) as client:
        version = upload(client)
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(client.get, suggestion_url(version))
            try:
                assert entered.wait(timeout=5)
                health = pool.submit(client.get, "/health")
                assert health.result(timeout=3).status_code == 200
            finally:
                release.set()
            assert pending.result(timeout=5).status_code == 200
