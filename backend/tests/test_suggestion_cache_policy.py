"""Retry fallback responses and safely retire caches created before cell validation."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

from fastapi.testclient import TestClient
from test_ai_integration import (
    DEMO_CSV,
    VALID_DEMO_CSV,
    FakeLLM,
    app,
    reply,
    suggestion_url,
    upload,
)

from once_wrong.storage import SUGGESTION_CACHE_REVISION, Store
from once_wrong_ai.ai_review.models import AIExplanation


def test_number_guard_response_is_not_cached_and_next_request_can_retry(database_path: Path):
    guarded = AIExplanation(
        title="請核對資料",
        explanation="差額是 999999。",
        candidates=reply((1, "opening", "100")).candidates,
    )
    llm = FakeLLM(guarded, reply((1, "opening", "100")))
    application = app(database_path, llm, seed_demo=True)
    with TestClient(application) as client:
        version = upload(client)
        first = client.get(suggestion_url(version))
        assert first.status_code == 200, first.text
        assert first.json()["source"] == "fallback_number_guard"
        assert first.json()["blockedNumbers"] == ["999999"]
        # A verified fix can accompany the guarded explanation; the whole response
        # must still be retried so the bad explanation does not become permanent.
        assert first.json()["suggestion"]["verification"] == "passed"
        assert application.state.store.get_cached_suggestion(
            version["id"], version["issues"][0]["id"]
        ) is None
        with sqlite3.connect(database_path) as connection:
            assert connection.execute("SELECT count(*) FROM suggestions").fetchone()[0] == 0
        assert not application.state.suggestion_locks

        second = client.get(suggestion_url(version))
        assert second.status_code == 200, second.text
        assert second.json()["source"] == "ai"
        assert second.json()["blockedNumbers"] == []
        assert second.json()["verification"] == "passed"
        assert len(llm.prompts) == 2
        assert client.get(suggestion_url(version)).json() == second.json()
        assert len(llm.prompts) == 2
        assert not application.state.suggestion_locks


def _authoritative_rows(database_path: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(database_path) as connection:
        return {
            name: connection.execute(f"SELECT * FROM {name} ORDER BY id").fetchall()
            for name in ("reports", "versions", "confirmations")
        }


def test_legacy_cache_migrates_without_changing_sources_versions_or_confirmations(
    database_path: Path,
):
    store = Store(database_path)
    store.initialize(seed_demo=False)
    error_report = store.create_report("待修資料", "2025-12", DEMO_CSV, "error.csv")
    error_version = error_report["versions"][0]
    valid_report = store.create_report("已確認資料", "2025-12", VALID_DEMO_CSV, "fixed.csv")
    valid_version = valid_report["versions"][0]
    store.confirm(valid_report["id"], valid_version["id"])
    issue_id = error_version["issues"][0]["id"]
    legacy_payload = {
        "source": "ai",
        "title": "舊版整列驗證快取",
        "model": "old-model",
        "suggestion": {"changes": [{"rowId": "A", "column": "previous", "value": 90}]},
    }
    # Recreate the exact pre-revision table while keeping actual populated report
    # tables, source bytes and confirmation history from the public Store flow.
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            DROP TABLE suggestions;
            CREATE TABLE suggestions (
                version_id TEXT NOT NULL REFERENCES versions(id),
                issue_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (version_id, issue_id)
            );
            """
        )
        connection.execute(
            "INSERT INTO suggestions VALUES (?, ?, ?, ?, ?)",
            (error_version["id"], issue_id, json.dumps(legacy_payload), "old-model", "old-time"),
        )
        assert "cache_revision" not in {
            row[1] for row in connection.execute("PRAGMA table_info(suggestions)")
        }
    before = _authoritative_rows(database_path)
    source_before = store.get_source(error_version["id"])
    llm = FakeLLM(reply((1, "opening", "100")))
    application = app(database_path, llm, seed_demo=False)
    with TestClient(application) as client:
        assert _authoritative_rows(database_path) == before
        assert application.state.store.get_cached_suggestion(error_version["id"], issue_id) is None
        with sqlite3.connect(database_path) as connection:
            assert "cache_revision" in {
                row[1] for row in connection.execute("PRAGMA table_info(suggestions)")
            }
            assert connection.execute("SELECT cache_revision FROM suggestions").fetchone() == ("",)

        response = client.get(suggestion_url(error_version))
        assert response.status_code == 200, response.text
        assert response.json()["model"] == llm.model_name
        assert response.json()["source"] == "ai"
        assert response.json()["suggestion"]["changes"] == [
            {"rowId": "A", "row": 1, "column": "opening", "value": 100}
        ]
        assert len(llm.prompts) == 1
        assert client.get(suggestion_url(error_version)).json() == response.json()
        assert len(llm.prompts) == 1
        with sqlite3.connect(database_path) as connection:
            stored, revision = connection.execute(
                "SELECT payload_json, cache_revision FROM suggestions"
            ).fetchone()
            assert json.loads(stored) == response.json()
            assert revision == SUGGESTION_CACHE_REVISION
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert _authoritative_rows(database_path) == before
        assert application.state.store.get_source(error_version["id"]) == source_before
        assert client.get(f"/versions/{error_version['id']}/source").content == DEMO_CSV
        confirmed = client.get(f"/reports/{valid_report['id']}").json()
        assert confirmed["submittedVersionId"] == valid_version["id"]
        assert not application.state.suggestion_locks


def test_concurrent_requests_share_one_model_call_and_release_issue_lock(database_path: Path):
    entered, release = Event(), Event()

    class BlockingLLM(FakeLLM):
        def explain(self, system_prompt: str, user_prompt: str):
            entered.set()
            assert release.wait(timeout=10), "The test failed to release the model"
            return super().explain(system_prompt, user_prompt)

    llm = BlockingLLM(reply((1, "opening", "100")))
    application = app(database_path, llm, seed_demo=True)
    with TestClient(application) as client:
        version = upload(client)
        url = suggestion_url(version)
        arrival = Barrier(6)

        def request():
            arrival.wait(timeout=5)
            return client.get(url)

        with ThreadPoolExecutor(max_workers=6) as pool:
            pending = [pool.submit(request) for _ in range(6)]
            try:
                assert entered.wait(timeout=5)
                assert len(application.state.suggestion_locks) == 1
            finally:
                release.set()
            responses = [future.result(timeout=10) for future in pending]
        assert all(response.status_code == 200 for response in responses)
        assert all(response.json() == responses[0].json() for response in responses)
        assert responses[0].json()["source"] == "ai"
        assert len(llm.prompts) == 1
        assert not application.state.suggestion_locks

        missing = client.get("/versions/missing/issues/A%3AR-07/suggestion")
        assert missing.status_code == 404
        assert not application.state.suggestion_locks
