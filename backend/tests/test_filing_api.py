"""HTTP filing snapshots retain files, history, atomicity and normalized evidence."""

import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_filing import (
    bundle,
    claim,
    source,
    subject,
    underwriting,
)

from once_wrong.database import verify_audit_chain
from once_wrong.filing import KEY_FIELDS, LIFE_CLAIM, LIFE_SUBJECT, LIFE_UW
from once_wrong.main import create_app
from once_wrong.validation import LIFE_COLUMNS


class NoCallsLLM:
    model_name = "filing-api-test-no-calls"

    def explain(self, system_prompt, user_prompt):
        raise AssertionError("Filing upload and reads must not call a model")


@pytest.fixture
def filing_client(database_path: Path):
    application = create_app(
        database_path, seed_demo=False, llm=NoCallsLLM(),
        knowledge_dir=database_path.parent / "missing-kb",
        memory_path=database_path.parent / "missing-notes.jsonl",
    )
    with TestClient(application) as client:
        yield client


def uploads(inputs):
    return [("files", (filename, raw, "text/csv")) for raw, filename in inputs]


def create(client, inputs=None, period="2025-10"):
    response = client.post(
        "/reports", data={"name": "合成壽險申報", "period": period},
        files=uploads(inputs if inputs is not None else bundle()),
    )
    assert response.status_code == 201, response.text
    return response.json()


def add(client, report_id, inputs):
    response = client.post(f"/reports/{report_id}/versions", files=uploads(inputs))
    assert response.status_code == 201, response.text
    return response.json()


def issue(version, rule="L1402"):
    return next(item for item in version["issues"] if item["ruleId"] == rule)


def snapshot(database_path):
    with sqlite3.connect(database_path) as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table}").fetchall()
            for table in (
                "reports", "versions", "confirmations", "version_state", "version_file",
                "record", "issue", "issue_cell", "issue_context", "audit_event",
            )
        }


def test_same_company_product_year_uses_one_report_and_duplicate_create_rolls_back(
    filing_client, database_path
):
    first = create(filing_client)
    before = snapshot(database_path)
    response = filing_client.post(
        "/reports", data={"name": "重複建立", "period": "2025-10"}, files=uploads(bundle())
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "REPORT_ALREADY_EXISTS"
    assert response.json()["details"]["reportId"] == first["id"]
    assert snapshot(database_path) == before
    with sqlite3.connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO reports(id,name,period,company_code,product,filing_year) "
                "SELECT 'duplicate','duplicate',period,company_code,product,filing_year "
                "FROM reports WHERE id=?", (first["id"],),
            )


def test_create_bundle_readback_and_each_original_file_hash(filing_client):
    inputs = bundle()
    report = create(filing_client, inputs)
    version = report["versions"][0]
    assert version["schemaProfileId"] == "life_filing_v1"
    assert version["ruleVersion"] == "life_filing_rules_v1"
    assert version["number"] == 1
    assert version["manifestSha256"] == version["sourceSha256"]
    assert {file["datasetType"] for file in version["files"]} == {
        LIFE_UW, LIFE_CLAIM, LIFE_SUBJECT
    }
    assert version["issues"] == []
    assert version["summary"]["notEvaluatedChecks"] > 0
    assert version["evidence"]["status"] == "partial"
    assert report["canSubmit"] is False
    assert filing_client.get(f"/reports/{report['id']}").json() == report
    assert filing_client.get("/reports").json() == [report]

    for file, (raw, filename) in zip(version["files"], inputs, strict=True):
        response = filing_client.get(f"/versions/{version['id']}/files/{file['id']}/source")
        assert response.status_code == 200, response.text
        assert response.content == raw
        digest = hashlib.sha256(raw).hexdigest()
        assert response.headers["x-source-sha256"] == file["sourceSha256"] == digest
        assert response.headers["cache-control"] == "no-store"
        assert filename in response.headers["content-disposition"]
        assert file["rows"][0]["id"] == f"{file['id']}:1"
        assert file["rows"][0]["fileId"] == file["id"]
        assert file["rows"][0]["datasetType"] == file["datasetType"]
    ids = [row["id"] for row in version["rows"]]
    assert len(set(ids)) == len(ids)


def test_same_content_in_another_upload_has_new_file_ids_and_the_same_manifest(filing_client):
    inputs = bundle()
    report = create(filing_client, inputs)
    first = report["versions"][0]
    second = add(filing_client, report["id"], list(reversed(inputs)))
    assert second["number"] == 2
    assert second["manifestSha256"] == first["manifestSha256"]
    assert {file["id"] for file in first["files"]}.isdisjoint(
        file["id"] for file in second["files"]
    )


def test_bundle_download_requires_file_id_and_checks_its_version(filing_client):
    report = create(filing_client)
    first = report["versions"][0]
    second = add(filing_client, report["id"], bundle())
    unqualified = filing_client.get(f"/versions/{first['id']}/source")
    assert unqualified.status_code == 409
    assert unqualified.json()["code"] == "FILE_ID_REQUIRED"
    for version_id, file_id, code in (
        (first["id"], "missing", "FILE_NOT_FOUND"),
        (second["id"], first["files"][0]["id"], "FILE_NOT_FOUND"),
        ("missing", first["files"][0]["id"], "VERSION_NOT_FOUND"),
    ):
        response = filing_client.get(f"/versions/{version_id}/files/{file_id}/source")
        assert response.status_code == 404
        assert response.json()["code"] == code


def test_new_repeated_regressed_history_survives_new_upload_ids_and_row_reordering(filing_client):
    bad = underwriting(**{"加保日期": "20250230"})
    other = underwriting("A00005", **{"退保別": "XED", "退保日期": "00000000"})
    report = create(filing_client, bundle(uw=[other, bad]))
    first = report["versions"][0]
    assert issue(first)["repeatStatus"] == "new"
    assert issue(first)["firstSeenNumber"] == 1
    assert issue(first)["repeated"] is False

    repeated = add(filing_client, report["id"], bundle(uw=[bad, other]))
    assert issue(repeated)["repeatStatus"] == "repeated"
    assert issue(repeated)["prevSeenNumber"] == 1
    assert issue(repeated)["repeated"] is True
    fixed = add(filing_client, report["id"], bundle(uw=[underwriting(), other]))
    assert not any(item["ruleId"] == "L1402" for item in fixed["issues"])
    returned = add(filing_client, report["id"], bundle(uw=[
        other, {**bad, "加保日期": "20250231"}
    ]))
    before, after = issue(first), issue(returned)
    assert before["fileId"] != after["fileId"]
    assert before["id"] != after["id"]
    assert before["issueKey"] == after["issueKey"]
    assert after["repeatStatus"] == "regressed"
    assert after["firstSeenNumber"] == 1 and after["prevSeenNumber"] == 2
    assert after["fixedInNumber"] == 3 and after["repeated"] is False
    readback = filing_client.get(f"/reports/{report['id']}").json()
    assert [version["number"] for version in readback["versions"]] == [1, 2, 3, 4]
    assert issue(readback["versions"][-1]) == after


def test_another_policy_in_the_same_position_starts_new_history(filing_client):
    bad = underwriting(**{"加保日期": "20250230"})
    report = create(filing_client, bundle(uw=[bad]))
    first = issue(report["versions"][0])
    second = add(filing_client, report["id"], bundle(uw=[
        underwriting("A00005", **{"加保日期": "20250230"})
    ]))
    assert issue(second)["issueKey"] != first["issueKey"]
    assert issue(second)["repeatStatus"] == "new"
    assert issue(second)["firstSeenNumber"] == 2


def test_v1_error_fixed_in_v2_and_returning_after_row_swap_in_v3_is_regressed(filing_client):
    bad = underwriting(**{"加保日期": "20250230"})
    other = underwriting("A00005", **{"退保別": "XED", "退保日期": "00000000"})
    report = create(filing_client, bundle(uw=[other, bad]))
    before = issue(report["versions"][0])
    fixed = add(filing_client, report["id"], bundle(uw=[other, underwriting()]))
    assert not any(item["ruleId"] == "L1402" for item in fixed["issues"])
    returned = add(filing_client, report["id"], bundle(uw=[
        {**bad, "加保日期": "20250231"}, other
    ]))
    after = issue(returned)
    assert before["rows"] == [2] and after["rows"] == [1]
    assert returned["number"] == 3
    assert after["issueKey"] == before["issueKey"]
    assert after["repeatStatus"] == "regressed"
    assert after["firstSeenNumber"] == after["prevSeenNumber"] == 1
    assert after["fixedInNumber"] == 2


@pytest.mark.parametrize("date_column", ["發生日期", "事故日期", "死亡完全失能日期"])
def test_date_alias_metadata_and_original_headers_survive_readback_and_restart(
    database_path, date_column
):
    values = {key: value for key, value in claim().items() if key != "發生日期"}
    columns = (*KEY_FIELDS[LIFE_CLAIM], date_column)
    claims = source(columns, {**values, date_column: "20250201"})
    inputs = bundle()
    inputs[1] = (claims, "claim-alias.csv")
    application = create_app(database_path, seed_demo=False, llm=NoCallsLLM())
    with TestClient(application) as client:
        report = create(client, inputs)
        version = report["versions"][0]
        file = next(file for file in version["files"] if file["datasetType"] == LIFE_CLAIM)
        assert file["eventDateColumn"] == date_column
        assert file["columns"] == list(columns)
        assert file["rows"][0]["values"][date_column] == "20250201"
    restarted = create_app(database_path, seed_demo=False, llm=NoCallsLLM())
    with TestClient(restarted) as client:
        assert client.get(f"/reports/{report['id']}").json() == report
        raw = client.get(f"/versions/{version['id']}/files/{file['id']}/source")
        assert raw.status_code == 200 and raw.content == claims


@pytest.mark.parametrize("inputs,period", [
    (bundle(claims=[claim(**{"公司代號": "02"})]), "2025-10"),
    (bundle(subjects=[subject(), subject(**{"填報年度": "2024"})]), "2025-10"),
    (bundle(), "2024-10"),
    ([(source(LIFE_COLUMNS, underwriting()), "uw.csv"),
      ("給付類別,公司代號\n1\n".encode(), "broken.csv")], "2025-10"),
    ([(source(LIFE_COLUMNS, underwriting()), "uw.csv"), (b"\xff", "bad.csv")], "2025-10"),
])
def test_any_bad_file_or_inconsistent_batch_rolls_back_the_complete_new_report(
    filing_client, database_path, inputs, period
):
    before = snapshot(database_path)
    response = filing_client.post(
        "/reports", data={"name": "不應留下半版", "period": period}, files=uploads(inputs)
    )
    assert response.status_code == 422, response.text
    assert snapshot(database_path) == before
    assert filing_client.get("/reports").json() == []


def test_invalid_revision_keeps_existing_versions_sources_and_audit_unchanged(
    filing_client, database_path
):
    report = create(filing_client)
    before = snapshot(database_path)
    malformed = bundle()
    malformed[1] = ("給付類別,公司代號\n1\n".encode(), "broken.csv")
    response = filing_client.post(f"/reports/{report['id']}/versions", files=uploads(malformed))
    assert response.status_code == 422
    assert snapshot(database_path) == before
    assert filing_client.get(f"/reports/{report['id']}").json() == report


def test_revision_cannot_change_the_report_company(filing_client, database_path):
    report = create(filing_client)
    different_company = bundle(
        uw=[underwriting(**{"公司代號": "02"})],
        claims=[claim(**{"公司代號": "02"})], subjects=[subject(**{"公司代號": "02"})],
    )
    before = snapshot(database_path)
    response = filing_client.post(
        f"/reports/{report['id']}/versions", files=uploads(different_company)
    )
    assert response.status_code == 422
    assert response.json()["code"] == "FILING_COMPANY_MISMATCH"
    assert snapshot(database_path) == before


@pytest.mark.parametrize("inputs", [bundle(), bundle()[:1], bundle()[1:]])
def test_missing_or_unimplemented_coverage_blocks_confirmation_even_without_errors(
    filing_client, database_path, inputs
):
    # An empty explicit claim file with no UW termination also has pending
    # official coverage; a missing file must never silently count as passed.
    report = create(filing_client, inputs)
    version = report["versions"][0]
    assert report["canSubmit"] is False
    assert version["summary"]["notEvaluatedChecks"] > 0
    before = snapshot(database_path)
    response = filing_client.post(
        f"/reports/{report['id']}/submissions", json={"versionId": version["id"]}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "VALIDATION_FAILED"
    assert snapshot(database_path) == before


def test_mixed_upload_contract_is_rejected_and_legacy_single_file_remains_supported(
    filing_client, database_path
):
    inputs = uploads(bundle()) + [("file", ("single.csv", source(LIFE_COLUMNS, underwriting()),
                                           "text/csv"))]
    before = snapshot(database_path)
    rejected = filing_client.post(
        "/reports", data={"name": "混用入口", "period": "2025-10"}, files=inputs
    )
    assert rejected.status_code == 422
    assert snapshot(database_path) == before

    raw = source(LIFE_COLUMNS, underwriting())
    legacy = filing_client.post(
        "/reports", data={"name": "單檔相容", "period": "2025-10"},
        files={"file": ("single.csv", raw, "text/csv")},
    )
    assert legacy.status_code == 201, legacy.text
    report = legacy.json()
    version = report["versions"][0]
    assert version["schemaProfileId"] == "life_underwriting_v1"
    assert "files" not in version
    assert filing_client.get(f"/versions/{version['id']}/source").content == raw
    next_legacy = filing_client.post(
        f"/reports/{report['id']}/versions", files={"file": ("next.csv", raw, "text/csv")}
    )
    assert next_legacy.status_code == 201, next_legacy.text
    assert next_legacy.json()["number"] == 2


def test_normalized_cells_and_cross_file_context_share_version_and_audit_chain(
    filing_client, database_path
):
    report = create(filing_client, bundle(claims=[claim(**{"發生日期": "20250202"})]))
    first = report["versions"][0]
    add(filing_client, report["id"], bundle())
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert verify_audit_chain(connection) is True
        assert connection.execute(
            "SELECT count(*) FROM version_file WHERE version_id=?", (first["id"],)
        ).fetchone()[0] == 3
        assert connection.execute(
            "SELECT file_count,record_count,sealed FROM version_state WHERE version_id=?",
            (first["id"],),
        ).fetchone() == (3, 3, 1)
        for table in ("issue_cell", "issue_context"):
            invalid = connection.execute(
                f"SELECT count(*) FROM {table} c "
                "JOIN issue i ON i.id=c.issue_id JOIN record r ON r.id=c.record_id "
                "JOIN version_file f ON f.id=r.file_id "
                "WHERE i.version_id<>r.version_id OR r.version_id<>f.version_id"
            ).fetchone()[0]
            assert invalid == 0
        claim_context = connection.execute(
            "SELECT f.dataset_type FROM issue_context c JOIN issue i ON i.id=c.issue_id "
            "JOIN rule q ON q.id=i.rule_id JOIN record r ON r.id=c.record_id "
            "JOIN version_file f ON f.id=r.file_id "
            "WHERE i.version_id=? AND q.code='30307_LD013'", (first["id"],),
        ).fetchall()
        assert claim_context == [(LIFE_UW,)]
        reverse_context = connection.execute(
            "SELECT f.dataset_type FROM issue_context c JOIN issue i ON i.id=c.issue_id "
            "JOIN rule q ON q.id=i.rule_id JOIN record r ON r.id=c.record_id "
            "JOIN version_file f ON f.id=r.file_id "
            "WHERE i.version_id=? AND q.code='30301_LD012'", (first["id"],),
        ).fetchall()
        assert reverse_context == [(LIFE_CLAIM,)]
