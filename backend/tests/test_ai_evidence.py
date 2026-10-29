"""AI requests minimize data while normalized evidence preserves every decision."""

import json
import sqlite3
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from test_ai_integration import FakeLLM
from test_filing import bundle, claim, source, underwriting

from once_wrong.database import verify_audit_chain
from once_wrong.filing import LIFE_UW
from once_wrong.main import create_app
from once_wrong.validation import LIFE_COLUMNS, REQUIRED_COLUMNS
from once_wrong_ai.ai_review.llm import LLMError
from once_wrong_ai.ai_review.models import AIChange, AIExplanation, AIFixCandidate

PRIVATE_POLICY = "SYNTHETIC_PRIVATE_POLICY_ABC"
PRIVATE_PERSON = "SYNTHETIC_PRIVATE_PERSON"
PRIVATE_ID = "SYNTHETIC_ID_NEVER_SEND"
PRIVATE_BIRTH = "19840219"


def candidate(*changes, reason="依據資料核對修正"):
    return AIFixCandidate(
        changes=[AIChange(row=row, column=column, new_value=value)
                 for row, column, value in changes],
        reason=reason,
    )


def explanation(*candidates):
    return AIExplanation(
        title="請核對資料", explanation="此欄位未符合規則，請依原始資料確認。",
        candidates=list(candidates),
    )


def application(database_path, llm):
    return create_app(
        database_path, seed_demo=False, llm=llm,
        knowledge_dir=database_path.parent / "missing-kb",
        memory_path=database_path.parent / "missing-notes.jsonl",
    )


def create_single(client, raw):
    response = client.post(
        "/reports", data={"name": PRIVATE_PERSON, "period": "2025-10"},
        files={"file": ("synthetic.csv", raw, "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_bundle(client, inputs):
    response = client.post(
        "/reports", data={"name": PRIVATE_PERSON, "period": "2025-10"},
        files=[("files", (filename, raw, "text/csv")) for raw, filename in inputs],
    )
    assert response.status_code == 201, response.text
    return response.json()


def issue(version, rule):
    return next(item for item in version["issues"] if item["ruleId"] == rule)


def review(client, version, finding):
    response = client.get(
        f"/versions/{version['id']}/issues/{quote(finding['id'], safe='')}/suggestion"
    )
    assert response.status_code == 200, response.text
    return response.json()


def prompt_payload(llm):
    [prompt] = llm.prompts
    return json.loads(prompt[prompt.index("{"):])


def stored_records(database_path, version_id):
    with sqlite3.connect(database_path) as connection:
        return connection.execute(
            "SELECT id,fields,raw_line FROM record WHERE version_id=? ORDER BY id", (version_id,)
        ).fetchall()


def assert_metadata_only_audit(database_path):
    with sqlite3.connect(database_path) as connection:
        events = connection.execute("SELECT payload FROM audit_event ORDER BY id").fetchall()
        assert verify_audit_chain(connection) is True
    for (raw,) in events:
        payload = json.loads(raw)
        assert "prompt" not in payload and "ai_output" not in payload
        assert PRIVATE_ID not in raw and PRIVATE_BIRTH not in raw and PRIVATE_PERSON not in raw


def test_demo_prompt_pseudonymizes_id_and_does_not_send_extra_source_fields(database_path):
    columns = (*REQUIRED_COLUMNS, "證件編號", "出生日期", "姓名")
    raw = source(columns, {
        "id": PRIVATE_POLICY, "product": "P", "previous": "100", "opening": "90",
        "證件編號": PRIVATE_ID, "出生日期": PRIVATE_BIRTH, "姓名": PRIVATE_PERSON,
    })
    llm = FakeLLM(explanation(candidate((1, "opening", "100"))))
    with TestClient(application(database_path, llm)) as client:
        report = create_single(client, raw)
        version = report["versions"][0]
        records_before = stored_records(database_path, version["id"])
        result = review(client, version, issue(version, "R-07"))
        assert result["verification"] == "passed"
        assert result["suggestion"]["changes"][0]["rowId"] == PRIVATE_POLICY
        outbound = prompt_payload(llm)
        assert outbound["欄位"] == list(REQUIRED_COLUMNS)
        assert outbound["出錯的資料列"][0]["id"].startswith("POLICY_")
        for private in (PRIVATE_POLICY, PRIVATE_ID, PRIVATE_PERSON, PRIVATE_BIRTH):
            assert private not in llm.prompts[0]
        assert stored_records(database_path, version["id"]) == records_before
        original = client.get(f"/versions/{version['id']}/source")
        assert original.status_code == 200 and original.content == raw
        assert client.get(f"/reports/{report['id']}").json() == report
    assert_metadata_only_audit(database_path)


def test_life_policy_is_pseudonymized_consistently_in_rows_facts_and_rule_message(database_path):
    first = underwriting(PRIVATE_POLICY, **{
        "異動序號": "00001", "退保別": "INN", "退保日期": "20250201"
    })
    second = underwriting(PRIVATE_POLICY, **{
        "異動序號": "00003", "加保別": "INN", "加保日期": "20250201",
        "退保別": "XED", "退保日期": "00000000",
    })
    raw = source(LIFE_COLUMNS, first, second)
    llm = FakeLLM(explanation())
    with TestClient(application(database_path, llm)) as client:
        report = create_single(client, raw)
        version = report["versions"][0]
        records_before = stored_records(database_path, version["id"])
        result = review(client, version, issue(version, "L0302"))
        assert result["source"] == "ai"
        outbound = prompt_payload(llm)
        assert outbound["欄位"] == list(LIFE_COLUMNS)
        rows = outbound["出錯的資料列"]
        assert len(rows) == 2
        assert rows[0]["保單編號"] == rows[1]["保單編號"]
        assert rows[0]["保單編號"].startswith("POLICY_")
        assert outbound["程式算好的數字"]["保單編號"] == rows[0]["保單編號"]
        assert PRIVATE_POLICY not in llm.prompts[0]
        assert stored_records(database_path, version["id"]) == records_before
        assert client.get(f"/versions/{version['id']}/source").content == raw
    assert_metadata_only_audit(database_path)


def test_full_underwriting_extra_identity_name_and_birth_fields_stay_local(database_path):
    values = underwriting(PRIVATE_POLICY, **{
        "加保日期": "20250230", "證件編號": PRIVATE_ID,
        "出生日期": PRIVATE_BIRTH, "姓名": PRIVATE_PERSON,
    })
    inputs = bundle(claims=[claim(PRIVATE_POLICY)])
    raw = source(tuple(values), values)
    inputs[0] = (raw, "full-underwriting.csv")
    llm = FakeLLM(explanation())
    with TestClient(application(database_path, llm)) as client:
        report = create_bundle(client, inputs)
        version = report["versions"][0]
        file = next(item for item in version["files"] if item["datasetType"] == LIFE_UW)
        records_before = stored_records(database_path, version["id"])
        assert file["rows"][0]["values"]["證件編號"] == PRIVATE_ID
        result = review(client, version, issue(version, "L1402"))
        assert result["source"] == "ai"
        outbound = prompt_payload(llm)
        assert outbound["欄位"] == list(LIFE_COLUMNS)
        assert set(outbound["出錯的資料列"][0]) == {"列號", *LIFE_COLUMNS}
        for private in (PRIVATE_POLICY, PRIVATE_ID, PRIVATE_PERSON, PRIVATE_BIRTH):
            assert private not in llm.prompts[0]
        assert stored_records(database_path, version["id"]) == records_before
        assert client.get(f"/versions/{version['id']}/files/{file['id']}/source").content == raw
        assert client.get(f"/reports/{report['id']}").json() == report
    assert_metadata_only_audit(database_path)


def test_every_candidate_including_second_pass_and_failed_raw_is_persisted(database_path):
    llm = FakeLLM(explanation(
        candidate((1, "opening", "100"), reason="依原期末值修正期初"),
        candidate((1, "previous", "90"), reason="另一個通過重驗的候選"),
        candidate((1, "opening", "95"), reason="仍未符合規則的候選"),
    ))
    raw = b"id,product,previous,opening\nA,P,100,90\n"
    with TestClient(application(database_path, llm)) as client:
        report = create_single(client, raw)
        version = report["versions"][0]
        result = review(client, version, issue(version, "R-07"))
        assert result["suggestion"]["changes"] == [
            {"rowId": "A", "row": 1, "column": "opening", "value": 100}
        ]
        assert "_candidates" not in result
        with sqlite3.connect(database_path) as connection:
            candidates = connection.execute(
                "SELECT rank,revalidation,rejection_reason,candidate_json "
                "FROM suggestion ORDER BY rank"
            ).fetchall()
            assert [(row[0], row[1]) for row in candidates] == [
                (1, "passed"), (2, "passed"), (3, "failed")
            ]
            assert candidates[0][2] is None and candidates[1][2] is None
            assert candidates[2][2]
            second = json.loads(candidates[1][3])
            assert second["rank"] == 2
            assert second["changes"] == [
                {"rowId": "A", "row": 1, "column": "previous", "value": "90"}
            ]
            assert json.loads(candidates[2][3])["changes"][0]["value"] == "95"
            changes = connection.execute(
                "SELECT s.rank,c.field_name,c.old_value,c.new_value FROM suggestion_change c "
                "JOIN suggestion s ON s.id=c.suggestion_id ORDER BY s.rank"
            ).fetchall()
            assert changes == [(1, "opening", "90", "100"), (2, "previous", "100", "90"),
                               (3, "opening", "90", "95")]
        assert client.get(f"/reports/{report['id']}").json() == report
    assert_metadata_only_audit(database_path)


@pytest.mark.parametrize("invalid", [
    candidate((9, "opening", "100"), reason="越界目標應保留原始證據"),
    candidate((1, "opening", "100"), (1, "opening", "99"), reason="同格衝突應保留兩個值"),
])
def test_invalid_target_retains_raw_changes_and_rank_without_turning_into_provider_failure(
    database_path, invalid
):
    llm = FakeLLM(explanation(invalid))
    with TestClient(application(database_path, llm)) as client:
        report = create_single(client, b"id,product,previous,opening\nA,P,100,90\n")
        version = report["versions"][0]
        result = review(client, version, issue(version, "R-07"))
        assert result["source"] == "ai"
        assert result["suggestion"] is None and result["rejectedSuggestions"]
        with sqlite3.connect(database_path) as connection:
            rank, state, raw = connection.execute(
                "SELECT rank,revalidation,candidate_json FROM suggestion"
            ).fetchone()
            assert rank == 1 and state == "invalid_target"
            stored = json.loads(raw)
            assert stored["reason"] == invalid.reason
            assert [(change["row"], change["column"], change["value"])
                    for change in stored["changes"]] == [
                (change.row, change.column, change.new_value) for change in invalid.changes
            ]
            assert connection.execute("SELECT count(*) FROM suggestion_change").fetchone()[0] <= 1
        assert client.get(f"/versions/{version['id']}/source").content.endswith(b"A,P,100,90\n")


def test_provider_failure_is_audited_without_cache_and_retry_writes_another_review(database_path):
    llm = FakeLLM(LLMError("synthetic provider failure"), explanation(
        candidate((1, "opening", "100"))
    ))
    with TestClient(application(database_path, llm)) as client:
        report = create_single(client, b"id,product,previous,opening\nA,P,100,90\n")
        version = report["versions"][0]
        target = issue(version, "R-07")
        first = review(client, version, target)
        assert first["source"] == "fallback_llm_error"
        with sqlite3.connect(database_path) as connection:
            assert connection.execute("SELECT source FROM ai_review").fetchall() == [
                ("fallback_llm_error",)
            ]
            assert connection.execute("SELECT count(*) FROM suggestions").fetchone()[0] == 0
            assert connection.execute("SELECT count(*) FROM suggestion").fetchone()[0] == 0
            audit = connection.execute(
                "SELECT payload FROM audit_event WHERE event_type='ai_review_completed'"
            ).fetchall()
            assert len(audit) == 1
            assert json.loads(audit[0][0])["source"] == "fallback_llm_error"
        second = review(client, version, target)
        assert second["source"] == "ai" and len(llm.prompts) == 2
        with sqlite3.connect(database_path) as connection:
            assert connection.execute("SELECT count(*) FROM ai_review").fetchone()[0] == 2
            assert connection.execute("SELECT count(*) FROM suggestions").fetchone()[0] == 1
        assert client.get(f"/reports/{report['id']}").json() == report
    assert_metadata_only_audit(database_path)


def test_bundle_rejects_single_file_pass_that_creates_new_ld_error_then_uses_second_candidate(
    database_path
):
    llm = FakeLLM(explanation(
        candidate((1, "退保別", "DEA"), reason="單檔通過但跨檔有問題的候選"),
        candidate((1, "退保日期", "00000000"), reason="符合整組資料的候選"),
    ))
    inputs = bundle(uw=[underwriting(**{"退保別": "XED"})], claims=[])
    with TestClient(application(database_path, llm)) as client:
        report = create_bundle(client, inputs)
        version = report["versions"][0]
        finding = issue(version, "L1504")
        records_before = stored_records(database_path, version["id"])
        result = review(client, version, finding)
        assert result["verification"] == "passed"
        assert result["suggestion"]["reason"] == "符合整組資料的候選"
        assert result["suggestion"]["changes"] == [{
            "rowId": f"{finding['fileId']}:1", "row": 1, "column": "退保日期",
            "value": "00000000", "fileId": finding["fileId"], "datasetType": LIFE_UW,
        }]
        assert any("跨檔" in reason for reason in result["rejectedSuggestions"])
        with sqlite3.connect(database_path) as connection:
            states = connection.execute(
                "SELECT rank,revalidation,rejection_reason,candidate_json "
                "FROM suggestion ORDER BY rank"
            ).fetchall()
            assert [(row[0], row[1]) for row in states] == [(1, "failed"), (2, "passed")]
            assert "跨檔" in states[0][2]
            assert json.loads(states[0][3])["changes"][0]["value"] == "DEA"
            assert json.loads(states[1][3])["changes"][0]["fileId"] == finding["fileId"]
        assert stored_records(database_path, version["id"]) == records_before
        assert client.get(f"/reports/{report['id']}").json() == report


@pytest.mark.parametrize("rule,date", [
    ("30307_LD013", "20250202"), ("D1001", "20250230")
])
def test_cross_file_or_claim_issue_returns_explicit_fixed_fallback_without_model_call(
    database_path, rule, date
):
    llm = FakeLLM()
    with TestClient(application(database_path, llm)) as client:
        report = create_bundle(client, bundle(claims=[claim(**{"發生日期": date})]))
        version = report["versions"][0]
        result = review(client, version, issue(version, rule))
        assert result["source"] == "fallback_llm_error"
        assert result["suggestion"] is None and result["verification"] == "unavailable"
        assert "人工核對" in result["explanation"]
        assert llm.prompts == []
        with sqlite3.connect(database_path) as connection:
            assert connection.execute("SELECT count(*) FROM ai_review").fetchone()[0] == 1
            assert connection.execute("SELECT count(*) FROM suggestions").fetchone()[0] == 0
            assert connection.execute("SELECT count(*) FROM suggestion").fetchone()[0] == 0
    assert_metadata_only_audit(database_path)


def test_bundle_rechecks_numbers_when_it_switches_to_a_later_candidate(database_path):
    llm = FakeLLM(explanation(
        candidate((1, "退保別", "DEA"), reason="單檔通過的候選"),
        candidate((1, "退保日期", "00000000"), reason="差額為 999999"),
    ))
    with TestClient(application(database_path, llm)) as client:
        report = create_bundle(client, bundle(uw=[underwriting(**{"退保別": "XED"})], claims=[]))
        version = report["versions"][0]
        result = review(client, version, issue(version, "L1504"))
        assert result["source"] == "fallback_number_guard"
        assert result["blockedNumbers"] == ["999999"]
        assert result["suggestion"]["reason"] == ""
        assert result["suggestion"]["changes"][0]["value"] == "00000000"
        assert "999999" not in result["explanation"]
        with sqlite3.connect(database_path) as connection:
            assert connection.execute("SELECT count(*) FROM suggestions").fetchone()[0] == 0
            raw = connection.execute(
                "SELECT candidate_json FROM suggestion WHERE rank=2"
            ).fetchone()[0]
            assert json.loads(raw)["blockedNumbers"] == ["999999"]
