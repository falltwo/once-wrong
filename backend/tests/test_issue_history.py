"""Business history stays attached to policies and records when rows move."""

import csv
import hashlib
import io
import sqlite3
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from legacy_fixture import create_legacy_database

from once_wrong.main import create_app
from once_wrong.validation import LIFE_COLUMNS, parse_profile_csv, summary, validate_profile
from once_wrong_ai.ai_review.models import AIExplanation


class NoFixLLM:
    model_name = "history-test-model"

    def explain(self, system_prompt, user_prompt):
        return AIExplanation(title="請核對日期", explanation="日期格式有誤。", candidates=[])


def policy(policy_no="A00003", **values):
    row = dict(zip(LIFE_COLUMNS, [
        "01", policy_no, "0001", "00000", "NEW", "20250115", "XED", "00000000"
    ], strict=True))
    return {**row, **values}


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=LIFE_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def first_version(client, rows):
    response = client.post(
        "/reports", data={"name": "壽險測試", "period": "2025-10"},
        files={"file": ("life.csv", csv_bytes(rows), "text/csv")},
    )
    assert response.status_code == 201, response.text
    report = response.json()
    return report["id"], report["versions"][0]


def next_version(client, report_id, rows):
    response = client.post(
        f"/reports/{report_id}/versions",
        files={"file": ("life.csv", csv_bytes(rows), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def issue(version, rule="L1402"):
    return next(item for item in version["issues"] if item["ruleId"] == rule)


def legacy_version(source, *, findings=None):
    parsed = parse_profile_csv(source)
    findings = (
        validate_profile(parsed.rows, parsed.schema_profile_id) if findings is None else findings
    )
    legacy_issues = [
        {key: value for key, value in entry.items() if key not in {
            "issueKey", "repeatStatus", "firstSeenNumber", "prevSeenNumber", "fixedInNumber"
        }}
        for entry in findings
    ]
    return {
        "id": "legacy-life-version", "number": 1, "filename": "legacy-life.csv",
        "createdAt": "2026-10-28T00:00:00Z", "rows": parsed.rows, "issues": legacy_issues,
        "schemaProfileId": parsed.schema_profile_id, "ruleVersion": parsed.rule_version,
        "columns": parsed.columns, "validationStatus": "completed", "validationRunId": "old-run",
        "sourceSha256": hashlib.sha256(source).hexdigest(),
        "summary": summary(parsed.rows, legacy_issues, parsed.schema_profile_id),
    }


def test_reordering_policies_keeps_history_and_suggestion_lookup(database_path):
    bad = policy(**{"加保日期": "20250230"})
    good = policy("A00005")
    application = create_app(database_path, seed_demo=False, llm=NoFixLLM())
    with TestClient(application) as client:
        report_id, first = first_version(client, [good, bad])
        second = next_version(client, report_id, [bad, good])
        before, after = issue(first), issue(second)
        assert before["rowIds"] == ["2"] and after["rowIds"] == ["1"]
        assert before["id"] != after["id"]
        assert before["issueKey"] == after["issueKey"]
        assert before["repeated"] is False and after["repeated"] is True
        response = client.get(
            f"/versions/{second['id']}/issues/{quote(after['id'], safe='')}/suggestion"
        )
        assert response.status_code == 200, response.text
        assert response.json()["source"] == "ai"


def test_another_policy_at_the_same_position_is_a_new_issue(database_path):
    application = create_app(database_path, seed_demo=False, llm=NoFixLLM())
    with TestClient(application) as client:
        report_id, first = first_version(client, [
            policy("A00005"), policy(**{"加保日期": "20250230"})
        ])
        second = next_version(client, report_id, [
            policy(), policy("A00005", **{"加保日期": "20250230"})
        ])
        assert issue(first)["id"] == issue(second)["id"]
        assert issue(first)["issueKey"] != issue(second)["issueKey"]
        assert issue(second)["repeated"] is False


@pytest.mark.parametrize("rule,column,before,after", [
    ("L1402", "加保日期", "20250230", "20250231"),
    ("L0302", "異動序號", "00002", "00003"),
])
def test_changing_a_still_invalid_key_field_cannot_hide_history(
    database_path, rule, column, before, after
):
    with TestClient(create_app(database_path, seed_demo=False, llm=NoFixLLM())) as client:
        report_id, first = first_version(client, [policy(**{column: before})])
        second = next_version(client, report_id, [policy(**{column: after})])
        assert issue(first, rule)["issueKey"] == issue(second, rule)["issueKey"]
        assert issue(second, rule)["repeated"] is True


def test_different_records_of_the_same_policy_do_not_share_record_level_history(database_path):
    first_row = policy(**{
        "異動序號": "00001", "加保日期": "20250115", "退保別": "INN", "退保日期": "20250230"
    })
    second_row = policy(**{
        "異動序號": "00002", "加保別": "INN", "加保日期": "20250131"
    })
    with TestClient(create_app(database_path, seed_demo=False, llm=NoFixLLM())) as client:
        report_id, first = first_version(client, [first_row, second_row])
        second = next_version(client, report_id, [
            {**first_row, "退保日期": "20250131"},
            {**second_row, "退保別": "INN", "退保日期": "20250231"},
        ])
        assert issue(first, "L1602")["issueKey"] != issue(second, "L1602")["issueKey"]
        assert issue(second, "L1602")["repeated"] is False


@pytest.mark.parametrize("before,after", [
    ({"公司代號": "01"}, {"公司代號": "02"}),
    ({"保單編號序號": "0001"}, {"保單編號序號": "0002"}),
    (
        {"保單編號": "A|B", "保單編號序號": "C"},
        {"保單編號": "A", "保單編號序號": "B|C"},
    ),
])
def test_business_keys_keep_companies_subpolicies_and_delimiters_distinct(
    database_path, before, after
):
    with TestClient(create_app(database_path, seed_demo=False, llm=NoFixLLM())) as client:
        report_id, first = first_version(client, [policy(**{"加保日期": "bad", **before})])
        second = next_version(client, report_id, [policy(**{"加保日期": "bad", **after})])
        assert issue(first)["issueKey"] != issue(second)["issueKey"]
        assert issue(second)["repeated"] is False


def test_legacy_row_ids_are_recompared_from_saved_rows_without_rewriting_history(database_path):
    bad = policy(**{"加保日期": "20250230"})
    good = policy("A00005")
    source = csv_bytes([good, bad])
    first = legacy_version(source)
    report_id = "legacy-life-report"
    old_payload = create_legacy_database(database_path, report_id, first, source)
    with TestClient(create_app(database_path, seed_demo=False, llm=NoFixLLM())) as client:
        migrated = client.get(f"/reports/{report_id}").json()["versions"][0]
        assert issue(migrated)["repeatStatus"] == "new"
        second = next_version(client, report_id, [bad, good])
        assert issue(second)["repeated"] is True
        assert issue(second)["prevSeenNumber"] == 1
        assert issue(second)["issueKey"] == issue(migrated)["issueKey"]
        with sqlite3.connect(database_path) as connection:
            saved = connection.execute(
                "SELECT payload_json,source_bytes FROM versions WHERE id = ?", (first["id"],)
            ).fetchone()
        assert saved == (old_payload, source)
    backups = list((database_path.parent / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT payload_json FROM versions").fetchone()[0] == old_payload
        assert backup.execute(
            "SELECT 1 FROM sqlite_master WHERE name='version_state'"
        ).fetchone() is None


def test_fixed_then_returning_error_is_not_misrepresented_as_consecutive_repeat(database_path):
    bad = policy(**{"加保日期": "20250230"})
    with TestClient(create_app(database_path, seed_demo=False, llm=NoFixLLM())) as client:
        report_id, _ = first_version(client, [bad])
        fixed = next_version(client, report_id, [policy()])
        assert fixed["issues"] == []
        returned = next_version(client, report_id, [bad])
        state = issue(returned)
        assert state["repeated"] is False
        assert state["repeatStatus"] == "regressed"
        assert state["prevSeenNumber"] == state["firstSeenNumber"] == 1
        assert state["fixedInNumber"] == 2


def test_history_uses_saved_findings_instead_of_rerunning_old_rows(database_path):
    bad = policy(**{"加保日期": "20250230"})
    source = csv_bytes([bad])
    first = legacy_version(source, findings=[])
    report_id = "legacy-unobserved-rule"
    old_payload = create_legacy_database(database_path, report_id, first, source)
    with TestClient(create_app(database_path, seed_demo=False, llm=NoFixLLM())) as client:
        assert client.get(f"/reports/{report_id}").json()["versions"][0]["issues"] == []
        current = next_version(client, report_id, [bad])
        assert issue(current)["repeated"] is False
        assert issue(current)["repeatStatus"] == "new"
        assert issue(current)["firstSeenNumber"] == 2
        with sqlite3.connect(database_path) as connection:
            assert connection.execute(
                "SELECT payload_json FROM versions WHERE id=?", (first["id"],)
            ).fetchone()[0] == old_payload
