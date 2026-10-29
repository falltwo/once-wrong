"""Behavioral contracts for the demonstration CSV workflow, not official rules."""

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from once_wrong.main import create_app

REPORT_ID = "reserve-202609"
REPORT_URL = f"/reports/{REPORT_ID}"
UPLOAD_URL = f"{REPORT_URL}/versions"
SUBMISSION_URL = f"{REPORT_URL}/submissions"
HEADER = "id,product,previous,opening\n"


def upload(client: TestClient, content: bytes, filename: str = "report.csv"):
    return client.post(UPLOAD_URL, files={"file": (filename, content, "text/csv")})


def report(client: TestClient) -> dict:
    response = client.get(REPORT_URL)
    assert response.status_code == 200, response.text
    return response.json()


def issue_map(version: dict) -> dict[tuple[str, str], dict]:
    return {(item["rowId"], item["ruleId"]): item for item in version["issues"]}


def assert_validation_metadata(version: dict, content: bytes, failed: int) -> None:
    assert version["schemaProfileId"] == "demo_csv_v1"
    assert version["ruleVersion"] == "demo_rules_v1"
    assert version["validationStatus"] == "completed"
    assert version["validationRunId"]
    assert version["sourceSha256"] == hashlib.sha256(content).hexdigest()
    assert version["summary"] == {
        "totalChecks": len(version["rows"]) * 2,
        "passedChecks": len(version["rows"]) * 2 - failed,
        "failedChecks": failed,
        "notEvaluatedChecks": 0,
    }


def test_seed_matches_frontend_and_is_not_submittable(client: TestClient):
    assert client.get("/health").status_code == 200
    listing = client.get("/reports")
    assert listing.status_code == 200
    assert isinstance(listing.json(), list)
    assert REPORT_ID in {item["id"] for item in listing.json()}

    seeded = report(client)
    assert seeded["canSubmit"] is False
    first, second = seeded["versions"]
    assert [first["id"], second["id"]] == ["v1", "v2"]
    assert [first["number"], second["number"]] == [1, 2]
    assert set(issue_map(first)) == {("POL-001", "R-07"), ("POL-003", "R-07")}
    assert set(issue_map(second)) == {("POL-003", "R-07"), ("POL-004", "R-01")}
    assert issue_map(second)[("POL-003", "R-07")]["repeated"] is True
    assert issue_map(second)[("POL-004", "R-01")]["repeated"] is False
    assert all(issue["repeated"] is False for issue in first["issues"])


def test_upload_errors_then_fixed_preserves_previous_versions_and_raw_bytes(
    client: TestClient, csv_fixtures: dict[str, bytes]
):
    before = report(client)["versions"]
    errors = csv_fixtures["sample-errors.csv"]
    response = upload(client, errors, "sample-errors.csv")
    assert response.status_code == 201, response.text
    third = response.json()
    assert third["number"] == 3
    assert third["filename"] == "sample-errors.csv"
    assert third["createdAt"]
    assert third["id"] not in {item["id"] for item in before}
    assert set(issue_map(third)) == {("POL-003", "R-07"), ("POL-004", "R-01")}
    assert all(issue["repeated"] is True for issue in third["issues"])
    assert_validation_metadata(third, errors, failed=2)
    assert report(client)["canSubmit"] is False
    raw = client.get(f"/versions/{third['id']}/source")
    assert raw.status_code == 200
    assert raw.content == errors

    fixed = csv_fixtures["sample-fixed.csv"]
    response = upload(client, fixed, "sample-fixed.csv")
    assert response.status_code == 201, response.text
    fourth = response.json()
    assert fourth["number"] == 4
    assert fourth["issues"] == []
    assert_validation_metadata(fourth, fixed, failed=0)
    after = report(client)
    assert after["canSubmit"] is True
    assert after["versions"] == [*before, third, fourth]
    assert client.get(f"/versions/{third['id']}/source").content == errors


def test_suggestions_return_complete_contract_without_credentials(client: TestClient):
    before = report(client)
    current = before["versions"][-1]
    for issue in current["issues"]:
        issue_id = quote(issue["id"], safe="")
        response = client.get(f"/versions/{current['id']}/issues/{issue_id}/suggestion")
        assert response.status_code == 200, response.text
        suggestion = response.json()
        assert suggestion["source"] == "fallback_llm_error"
        assert suggestion["verification"] == "unavailable"
        assert suggestion["suggestion"] is None
        assert suggestion["rejectedSuggestions"] == []
        assert suggestion["citations"] == []
        assert suggestion["blockedNumbers"] == []
        assert suggestion["title"]
        assert suggestion["model"]
        assert suggestion["explanation"].strip()
    assert report(client) == before


def test_confirmation_is_latest_only_idempotent_and_invalidated_by_upload(
    client: TestClient, database_path: Path, csv_fixtures: dict[str, bytes]
):
    invalid_latest = report(client)["versions"][-1]
    assert client.post(SUBMISSION_URL, json={"versionId": invalid_latest["id"]}).status_code == 409

    fixed_response = upload(client, csv_fixtures["sample-fixed.csv"])
    assert fixed_response.status_code == 201
    fixed = fixed_response.json()
    for _ in range(2):
        response = client.post(SUBMISSION_URL, json={"versionId": fixed["id"]})
        assert response.status_code == 204, response.text
        assert response.content == b""
    assert report(client)["submittedVersionId"] == fixed["id"]
    assert report(client)["canSubmit"] is False
    with sqlite3.connect(database_path) as connection:
        confirmation_history = connection.execute(
            "SELECT id, report_id, version_id, confirmed_at, source_sha256, rule_version "
            "FROM confirmations ORDER BY id"
        ).fetchall()
    assert len(confirmation_history) == 1
    confirmation = confirmation_history[0]
    assert confirmation[1:3] == (REPORT_ID, fixed["id"])
    assert confirmation[3]
    assert confirmation[4:] == (fixed["sourceSha256"], fixed["ruleVersion"])

    newer_response = upload(client, csv_fixtures["sample-errors.csv"])
    assert newer_response.status_code == 201
    newer = newer_response.json()
    latest = report(client)
    assert latest.get("submittedVersionId") is None
    assert latest["canSubmit"] is False
    assert latest["versions"][-2] == fixed
    assert client.get(f"/versions/{fixed['id']}/source").content == csv_fixtures["sample-fixed.csv"]
    assert client.post(SUBMISSION_URL, json={"versionId": fixed["id"]}).status_code == 409
    assert client.post(SUBMISSION_URL, json={"versionId": newer["id"]}).status_code == 409
    assert report(client).get("submittedVersionId") is None
    with sqlite3.connect(database_path) as connection:
        assert (
            connection.execute(
                "SELECT id, report_id, version_id, confirmed_at, source_sha256, rule_version "
                "FROM confirmations ORDER BY id"
            ).fetchall()
            == confirmation_history
        )


def test_confirmation_rechecks_rules_instead_of_trusting_cached_success(
    client: TestClient, csv_fixtures: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
):
    from once_wrong import storage

    response = upload(client, csv_fixtures["sample-fixed.csv"])
    assert response.status_code == 201
    version = response.json()
    assert version["issues"] == []
    assert report(client)["canSubmit"] is True
    checked_rows = []

    def newly_failing_validator(rows, previous_issues=None):
        checked_rows.append(rows)
        return [{"id": "new-rule-failure"}]

    # Model a server-side rule evaluation now failing while persisted metadata
    # still says completed with no issues. Confirmation must run the gate again.
    monkeypatch.setattr(storage, "validate", newly_failing_validator)
    response = client.post(SUBMISSION_URL, json={"versionId": version["id"]})
    assert response.status_code == 409, response.text
    assert checked_rows == [version["rows"]]
    current = report(client)
    assert current["versions"][-1]["issues"] == []
    assert current.get("submittedVersionId") is None


def test_forged_client_verdict_cannot_confirm_a_failing_version(client: TestClient):
    latest = report(client)["versions"][-1]
    response = client.post(
        SUBMISSION_URL,
        json={"versionId": latest["id"], "issues": [], "canSubmit": True},
    )
    assert response.status_code in {409, 422}, response.text
    assert report(client)["canSubmit"] is False
    assert report(client).get("submittedVersionId") is None


def test_restart_retains_upload_confirmation_and_does_not_reset_seed(
    database_path: Path, csv_fixtures: dict[str, bytes]
):
    content = csv_fixtures["sample-fixed.csv"]
    with TestClient(create_app(database_path, seed_demo=True)) as first:
        response = upload(first, content, "persisted.csv")
        assert response.status_code == 201
        version = response.json()
        assert first.post(SUBMISSION_URL, json={"versionId": version["id"]}).status_code == 204
        stored = report(first)

    with TestClient(create_app(database_path, seed_demo=True)) as second:
        assert report(second) == stored
        assert second.get(f"/versions/{version['id']}/source").content == content
        assert second.post(SUBMISSION_URL, json={"versionId": version["id"]}).status_code == 204
        response = upload(second, content)
        assert response.status_code == 201
        assert response.json()["number"] == 4
        assert report(second).get("submittedVersionId") is None


def test_seed_can_be_disabled_for_an_empty_database(database_path: Path):
    with TestClient(create_app(database_path, seed_demo=False)) as empty:
        assert empty.get("/health").status_code == 200
        assert empty.get("/reports").json() == []
        assert empty.get(REPORT_URL).status_code == 404


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    [
        ("get", "/reports/no-such-report", {}),
        (
            "post",
            "/reports/no-such-report/versions",
            {"files": {"file": ("valid.csv", (HEADER + "A,P,1,1\n").encode(), "text/csv")}},
        ),
        ("post", "/reports/no-such-report/submissions", {"json": {"versionId": "v2"}}),
        ("get", "/versions/no-such-version/source", {}),
        ("get", "/versions/no-such-version/issues/no-such-issue/suggestion", {}),
        ("get", "/versions/v2/issues/no-such-issue/suggestion", {}),
    ],
    ids=[
        "report",
        "upload-report",
        "confirm-report",
        "source",
        "suggestion-version",
        "suggestion-issue",
    ],
)
def test_unknown_resources_return_404(client: TestClient, method: str, url: str, kwargs: dict):
    before = report(client)
    response = client.request(method, url, **kwargs)
    assert response.status_code == 404, response.text
    assert report(client) == before


INVALID_CSVS = [
    ("invalid-utf8", b"id,product,previous,opening\nA,\xff,1,1\n"),
    ("unclosed-quote", (HEADER + 'A,"P,1,1\n').encode()),
    ("too-many-columns", (HEADER + "A,P,1,1,unexpected\n").encode()),
    ("too-few-columns", (HEADER + "A,P,1\n").encode()),
    ("missing-header", b"id,product,previous\nA,P,1\n"),
    ("duplicate-header", b"id,product,previous,opening,opening\nA,P,1,1,1\n"),
    ("empty-header", b"id,product,previous,opening,\nA,P,1,1,extra\n"),
    ("no-rows", HEADER.encode()),
    ("only-blank-rows", (HEADER + "\n\r\n").encode()),
    ("blank-id", (HEADER + " ,P,1,1\n").encode()),
    ("duplicate-id", (HEADER + "A,P,1,1\nA,Q,2,2\n").encode()),
    ("blank-previous", (HEADER + "A,P,,1\n").encode()),
    ("blank-opening", (HEADER + "A,P,1,\n").encode()),
    ("negative-money", (HEADER + "A,P,-1,1\n").encode()),
    ("fractional-money", (HEADER + "A,P,1,1.5\n").encode()),
    ("exponent-money", (HEADER + "A,P,1e3,1000\n").encode()),
    ("hexadecimal-money", (HEADER + "A,P,0x10,16\n").encode()),
    ("non-ascii-money", (HEADER + "A,P,１２,12\n").encode()),
    ("unsafe-integer", (HEADER + "A,P,9007199254740992,1\n").encode()),
    ("nonnumeric-money", (HEADER + "A,P,NaN,1\n").encode()),
    ("over-row-limit", (HEADER + "".join(f"P-{index},P,1,1\n" for index in range(1001))).encode()),
]


@pytest.mark.parametrize(("case", "content"), INVALID_CSVS, ids=[case for case, _ in INVALID_CSVS])
def test_invalid_uploads_reject_without_creating_version(
    client: TestClient, case: str, content: bytes
):
    before = report(client)
    response = upload(client, content, f"{case}.csv")
    assert response.status_code == 422, response.text
    assert report(client) == before


def test_oversized_upload_rejects_before_creating_version(client: TestClient):
    before = report(client)
    content = (HEADER + "A,").encode() + b"P" * (2 * 1024 * 1024) + b",1,1\n"
    response = upload(client, content, "too-large.csv")
    assert response.status_code == 413, response.text
    assert report(client) == before


def test_blank_product_is_a_business_finding_not_an_upload_rejection(client: TestClient):
    content = (HEADER + "A,,1,1\n").encode()
    response = upload(client, content)
    assert response.status_code == 201, response.text
    version = response.json()
    assert set(issue_map(version)) == {("A", "R-01")}
    assert version["issues"][0]["repeated"] is False
    assert_validation_metadata(version, content, failed=1)
    assert report(client)["canSubmit"] is False


def test_bom_quoted_field_and_crlf_preserve_source_bytes(client: TestClient):
    content = b'\xef\xbb\xbfid,product,previous,opening\r\nA,"CR, special",1,1\r\n'
    response = upload(client, content, "quoted.csv")
    assert response.status_code == 201, response.text
    version = response.json()
    assert version["rows"][0]["product"] == "CR, special"
    assert version["issues"] == []
    assert_validation_metadata(version, content, failed=0)
    source = client.get(f"/versions/{version['id']}/source")
    assert source.status_code == 200
    assert source.content == content


def test_row_limit_boundary_accepts_one_thousand_records(client: TestClient):
    content = (HEADER + "".join(f"P-{index},P,1,1\n" for index in range(1000))).encode()
    response = upload(client, content)
    assert response.status_code == 201, response.text
    version = response.json()
    assert len(version["rows"]) == 1000
    assert version["issues"] == []
    assert_validation_metadata(version, content, failed=0)


def test_concurrent_uploads_allocate_unique_sequential_persisted_versions(
    client: TestClient, database_path: Path, csv_fixtures: dict[str, bytes]
):
    original = report(client)["versions"]
    worker_count = 4
    ready = Barrier(worker_count)
    content = csv_fixtures["sample-fixed.csv"]

    def upload_from_independent_client(index: int) -> dict:
        with TestClient(create_app(database_path, seed_demo=False)) as worker:
            ready.wait(timeout=20)
            response = upload(worker, content, f"parallel-{index}.csv")
            assert response.status_code == 201, response.text
            return response.json()

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        versions = list(pool.map(upload_from_independent_client, range(worker_count)))

    assert len({version["id"] for version in versions}) == worker_count
    assert sorted(version["number"] for version in versions) == [3, 4, 5, 6]
    after = report(client)
    assert after["versions"][:2] == original
    assert [item["number"] for item in after["versions"]] == list(range(1, 7))
    assert {item["id"] for item in after["versions"][2:]} == {item["id"] for item in versions}
    with TestClient(create_app(database_path, seed_demo=False)) as reopened:
        assert report(reopened) == after
        for version in versions:
            assert reopened.get(f"/versions/{version['id']}/source").content == content
