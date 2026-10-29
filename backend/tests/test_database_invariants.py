"""The database independently guards immutable evidence, history and confirmation."""

import hashlib
import json
import sqlite3
from uuid import uuid4

import pytest

from once_wrong import database

LEGACY_SCHEMA = """
CREATE TABLE reports(id TEXT PRIMARY KEY,name TEXT NOT NULL,period TEXT NOT NULL,
 submitted_version_id TEXT);
CREATE TABLE versions(id TEXT PRIMARY KEY,report_id TEXT NOT NULL REFERENCES reports(id),
 number INTEGER NOT NULL,payload_json TEXT NOT NULL,source_bytes BLOB NOT NULL,
 source_sha256 TEXT NOT NULL,UNIQUE(report_id,number));
CREATE TABLE confirmations(id TEXT PRIMARY KEY,report_id TEXT NOT NULL REFERENCES reports(id),
 version_id TEXT NOT NULL REFERENCES versions(id),confirmed_at TEXT NOT NULL,
 source_sha256 TEXT NOT NULL,rule_version TEXT NOT NULL,UNIQUE(report_id,version_id));
CREATE TABLE suggestions(version_id TEXT NOT NULL REFERENCES versions(id),issue_id TEXT NOT NULL,
 payload_json TEXT NOT NULL,model TEXT NOT NULL,created_at TEXT NOT NULL,
 PRIMARY KEY(version_id,issue_id));
INSERT INTO reports(id,name,period) VALUES('R','Synthetic report','2025-10');
"""


def connection(*, initialize=True):
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(LEGACY_SCHEMA)
    if initialize:
        database.initialize(conn)
    return conn


@pytest.fixture
def conn():
    value = connection()
    yield value
    value.close()


def test_group_rule_requires_a_dataset_with_policy_group_fields(conn):
    rule_set = conn.execute(
        "SELECT id FROM rule_set WHERE profile_id='life_filing_v1'"
    ).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="requires policy fields"):
        conn.execute(
            "INSERT INTO rule(rule_set_id,code,dataset_type,title,scope,severity,handler,"
            "params,issue_key_level,manual_page) VALUES(?,?,'LIFE_SUBJECT','test',"
            "'single_record','error','test','{}','group','test')",
            (rule_set, "INVALID_GROUP"),
        )


def finding():
    return {
        "id": "A:R-07", "ruleId": "R-07", "rowId": "A", "field": "opening",
        "title": "Opening differs", "actual": 90, "expected": 100, "repeated": False,
    }


def insert_snapshot(conn, *, issues=None, not_evaluated=0, profile="demo_csv_v1"):
    number = conn.execute("SELECT COALESCE(max(number),0)+1 FROM versions").fetchone()[0]
    raw = b"id,product,previous,opening\nA,P,100,90\n"
    issues = [] if issues is None else issues
    issues = database.annotate_history(conn, "R", number, issues, profile)
    version = {
        "id": str(uuid4()), "number": number, "filename": "source.csv",
        "schemaProfileId": profile, "ruleVersion": database.RELEASES[profile],
        "rows": [{"id": "A", "product": "P", "previous": 100, "opening": 90}],
        "issues": issues, "summary": {
            "totalChecks": 2, "passedChecks": 2 - len(issues) - not_evaluated,
            "failedChecks": len(issues), "notEvaluatedChecks": not_evaluated,
        },
    }
    digest = hashlib.sha256(raw).hexdigest()
    conn.execute(
        "INSERT INTO versions VALUES(?,?,?,?,?,?)",
        (version["id"], "R", number, json.dumps(version), raw, digest),
    )
    files = [{
        "id": str(uuid4()), "datasetType": "DEMO", "filename": "source.csv",
        "sourceBytes": raw, "sourceSha256": digest,
        "columns": ["id", "product", "previous", "opening"], "rows": version["rows"],
    }]
    return version, files


def persist(conn, **kwargs):
    version, files = insert_snapshot(conn, **kwargs)
    database.persist_version(conn, version, "R", files)
    return version, files


def confirm(conn, version, *, source_hash=None):
    row = conn.execute("SELECT source_sha256 FROM versions WHERE id=?", (version["id"],)).fetchone()
    conn.execute(
        "INSERT INTO confirmations VALUES(?,?,?,?,?,?)",
        (str(uuid4()), "R", version["id"], "2026-10-29T00:00:00Z", source_hash or row[0],
         version["ruleVersion"]),
    )


def test_history_distinguishes_consecutive_and_returning_errors(conn):
    first, _ = persist(conn, issues=[finding()])
    repeated, _ = persist(conn, issues=[finding()])
    persist(conn)
    returned, _ = persist(conn, issues=[finding()])
    assert first["issues"][0]["repeatStatus"] == "new"
    assert repeated["issues"][0]["repeatStatus"] == "repeated"
    assert repeated["issues"][0]["prevSeenNumber"] == 1
    state = returned["issues"][0]
    assert state["repeatStatus"] == "regressed"
    assert state["firstSeenNumber"] == 1 and state["prevSeenNumber"] == 2
    assert state["fixedInNumber"] == 3 and state["repeated"] is False
    assert database.verify_audit_chain(conn)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_forged_history_is_rejected_even_by_direct_sql(conn):
    persist(conn, issues=[finding()])
    version, files = insert_snapshot(conn, issues=[finding()])
    rule_set = conn.execute(
        "SELECT id FROM rule_set WHERE profile_id='demo_csv_v1'"
    ).fetchone()[0]
    rule = conn.execute("SELECT id FROM rule WHERE code='R-07'").fetchone()[0]
    conn.execute(
        "INSERT INTO version_state VALUES(?,?,?,?,?,?,?,?,0)",
        (version["id"], "demo_csv_v1", rule_set, database.manifest_sha256(files), 1, 1, 1, 0),
    )
    with pytest.raises(sqlite3.IntegrityError, match="history"):
        conn.execute(
            """INSERT INTO issue VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid4()), "A:R-07", version["id"], "R", 2, "demo_csv_v1", rule,
             "demo_csv_v1:A:R-07", "Fake new", "{}", "new", None, 2),
        )


def test_version_cannot_be_inserted_as_already_sealed(conn):
    version, files = insert_snapshot(conn)
    rule_set = conn.execute(
        "SELECT id FROM rule_set WHERE profile_id='demo_csv_v1'"
    ).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="state does not match"):
        conn.execute(
            "INSERT INTO version_state VALUES(?,?,?,?,?,?,?,?,1)",
            (version["id"], "demo_csv_v1", rule_set, database.manifest_sha256(files), 1, 1, 0, 0),
        )


@pytest.mark.parametrize("table", [
    "versions", "version_file", "record", "issue", "issue_cell", "audit_event",
])
def test_evidence_cannot_be_updated_or_deleted(conn, table):
    persist(conn, issues=[finding()])
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute(f"DELETE FROM {table}")
    column = conn.execute(f"PRAGMA table_info({table})").fetchone()[1]
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute(f"UPDATE {table} SET {column}={column}")


def test_cannot_append_records_to_a_sealed_version(conn):
    version, files = persist(conn)
    old = conn.execute("SELECT * FROM record").fetchone()
    with pytest.raises(sqlite3.IntegrityError, match="record keys"):
        conn.execute(
            "INSERT INTO record VALUES(?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), version["id"], files[0]["id"], 2, "B", old[5], old[6], old[7], old[8]),
        )


def test_cells_and_context_cannot_point_into_another_version(conn):
    first, _ = persist(conn, issues=[finding()])
    old_record = conn.execute(
        "SELECT id FROM record WHERE version_id=?", (first["id"],)
    ).fetchone()[0]
    second, files = insert_snapshot(conn, issues=[finding()])
    rule_set = conn.execute(
        "SELECT id FROM rule_set WHERE profile_id='demo_csv_v1'"
    ).fetchone()[0]
    rule = conn.execute("SELECT id FROM rule WHERE code='R-07'").fetchone()[0]
    conn.execute(
        "INSERT INTO version_state VALUES(?,?,?,?,?,?,?,?,0)",
        (second["id"], "demo_csv_v1", rule_set, database.manifest_sha256(files), 1, 1, 1, 0),
    )
    normalized = str(uuid4())
    conn.execute(
        "INSERT INTO issue VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (normalized, "A:R-07", second["id"], "R", 2, "demo_csv_v1", rule,
         "demo_csv_v1:A:R-07", "Opening differs", "{}", "repeated", 1, 1),
    )
    with pytest.raises(sqlite3.IntegrityError, match="same open version"):
        conn.execute("INSERT INTO issue_cell VALUES(?,?,?)", (normalized, old_record, "opening"))
    with pytest.raises(sqlite3.IntegrityError, match="same open version"):
        conn.execute("INSERT INTO issue_context VALUES(?,?)", (normalized, old_record))


@pytest.mark.parametrize("problem", ["error", "not-evaluated", "wrong-hash", "stale"])
def test_confirmation_rejects_incomplete_or_wrong_evidence(conn, problem):
    version, _ = persist(
        conn, issues=[finding()] if problem == "error" else [],
        not_evaluated=1 if problem == "not-evaluated" else 0,
    )
    if problem == "stale":
        persist(conn)
    with pytest.raises(sqlite3.IntegrityError, match="confirmation requires"):
        confirm(conn, version, source_hash="0" * 64 if problem == "wrong-hash" else None)


def test_latest_complete_version_can_be_confirmed_and_confirmation_is_immutable(conn):
    version, _ = persist(conn)
    confirm(conn, version)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("DELETE FROM confirmations")


def test_version_numbers_cannot_skip(conn):
    version, _ = persist(conn)
    row = conn.execute("SELECT * FROM versions WHERE id=?", (version["id"],)).fetchone()
    with pytest.raises(sqlite3.IntegrityError, match="previous max"):
        conn.execute(
            "INSERT INTO versions VALUES(?,?,?,?,?,?)",
            (str(uuid4()), "R", 3, row[3], row[4], row[5]),
        )


def test_catalog_loads_whitelisted_rules_and_rejects_unknown_handler(conn):
    assert len(database.load_rules(conn, "life_underwriting_v1").rules) == 11
    assert len(database.load_rules(conn, "life_filing_v1").rules) == 11
    assert len(database.load_rules(conn, "demo_csv_v1").rules) == 2
    conn.execute(
        "INSERT INTO rule_set(profile_id,version_label,manual_title,created_at) VALUES(?,?,?,?)",
        ("demo_csv_v1", "unsafe", "Synthetic invalid catalog", "now"),
    )
    rule_set = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO rule(rule_set_id,code,dataset_type,title,scope,severity,handler,
           params,issue_key_level,manual_page) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (rule_set, "R-X", "DEMO", "Invalid", "single_record", "error", "os.system", "{}",
         "record", "none"),
    )
    with pytest.raises(ValueError, match="Unsupported rule handler"):
        database.load_rules(conn, "demo_csv_v1", "unsafe")


def test_ai_candidates_citations_and_rejections_are_retained(conn):
    version, _ = persist(conn, issues=[finding()])
    review_id = database.persist_ai_review(conn, version["id"], "A:R-07", {
        "model": "test-model", "source": "ai", "title": "Check opening", "explanation": "Check.",
        "blockedNumbers": [], "candidates": [
            {"rank": 1, "reason": "Use previous", "revalidation": "passed", "changes": [
                {"rowId": "A", "column": "opening", "value": 100}
            ]},
            {"rank": 2, "reason": "Invalid target", "revalidation": "invalid_target",
             "rejectionReason": "No such row", "changes": [
                 {"rowId": "missing", "column": "opening", "value": 100}
             ]},
        ], "citations": [
            {
                "id": "LIFE-RULE-0068", "source": "Manual snapshot",
                "section": ["Chapter"], "page": 46,
            }
        ],
    })
    assert conn.execute(
        "SELECT count(*) FROM suggestion WHERE ai_review_id=?", (review_id,)
    ).fetchone()[0] == 2
    rejected = conn.execute(
        "SELECT candidate_json FROM suggestion WHERE ai_review_id=? AND rank=2", (review_id,)
    ).fetchone()[0]
    assert json.loads(rejected)["changes"][0]["rowId"] == "missing"
    assert conn.execute(
        "SELECT source_title FROM citation WHERE ai_review_id=?", (review_id,)
    ).fetchone()[0] == "Manual snapshot"
    assert database.verify_audit_chain(conn)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("DELETE FROM suggestion")


def test_passed_candidate_cannot_change_a_fact_outside_issue_cells(conn):
    version, _ = persist(conn, issues=[finding()])
    with pytest.raises(sqlite3.IntegrityError, match="only change issue cells"):
        database.persist_ai_review(conn, version["id"], "A:R-07", {
            "model": "test", "source": "ai", "title": "Check", "explanation": "Check",
            "suggestion": {"reason": "Change fact", "changes": [
                {"rowId": "A", "column": "product", "value": "OTHER"}
            ]},
        })


@pytest.mark.parametrize("state,values,conflict", [
    ("invalid_target", [100, 101], False),
    ("passed", [100, "100"], False),
    ("passed", [100, 101], True),
])
def test_duplicate_raw_changes_are_preserved_without_duplicate_normalized_targets(
    conn, state, values, conflict
):
    version, _ = persist(conn, issues=[finding()])
    payload = {
        "model": "test", "source": "ai", "title": "Check", "explanation": "Check",
        "candidates": [{
            "rank": 1, "reason": "Raw duplicate changes", "revalidation": state,
            "rejectionReason": "Conflicting targets" if state != "passed" else None,
            "changes": [{"rowId": "A", "column": "opening", "value": value}
                        for value in values],
        }],
    }
    if conflict:
        with pytest.raises(ValueError, match="conflicting values"):
            database.persist_ai_review(conn, version["id"], "A:R-07", payload)
        return
    review = database.persist_ai_review(conn, version["id"], "A:R-07", payload)
    row = conn.execute(
        "SELECT id,candidate_json FROM suggestion WHERE ai_review_id=?", (review,)
    ).fetchone()
    assert len(json.loads(row[1])["changes"]) == 2
    assert conn.execute(
        "SELECT count(*) FROM suggestion_change WHERE suggestion_id=?", (row[0],)
    ).fetchone()[0] == 1


def test_audit_chain_rejects_a_forged_digest_or_fork(conn):
    version, _ = persist(conn)
    last = conn.execute("SELECT hash FROM audit_event ORDER BY id DESC LIMIT 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="unique valid chain"):
        conn.execute(
            "INSERT INTO audit_event VALUES(NULL,?,?,?,?,?,?,?,?)",
            ("now", "system", "forged", version["id"], None, "{}", last, "f" * 64),
        )
    assert database.verify_audit_chain(conn)


def test_additive_migration_preserves_legacy_rows_and_backfills_history():
    conn = connection(initialize=False)
    first, _ = insert_snapshot_without_catalog(conn, 1, [finding()])
    insert_snapshot_without_catalog(conn, 2, [])
    returned, _ = insert_snapshot_without_catalog(conn, 3, [finding()])
    before = [tuple(row) for row in conn.execute("SELECT * FROM versions ORDER BY number")]
    database.initialize(conn)
    assert database.migrate_existing(conn) == 3
    assert database.migrate_existing(conn) == 0
    assert [tuple(row) for row in conn.execute("SELECT * FROM versions ORDER BY number")] == before
    assert database.enrich_version(conn, first)["issues"][0]["repeatStatus"] == "new"
    state = database.enrich_version(conn, returned)["issues"][0]
    assert state["repeatStatus"] == "regressed" and state["fixedInNumber"] == 2
    assert database.verify_audit_chain(conn)
    conn.close()


def insert_snapshot_without_catalog(conn, number, issues):
    raw = b"id,product,previous,opening\nA,P,100,90\n"
    version = {
        "id": str(uuid4()), "number": number, "filename": "legacy.csv",
        "schemaProfileId": "demo_csv_v1", "ruleVersion": "demo_rules_v1",
        "rows": [{"id": "A", "product": "P", "previous": 100, "opening": 90}],
        "issues": issues, "summary": {"totalChecks": 2, "passedChecks": 2-len(issues),
                                       "failedChecks": len(issues), "notEvaluatedChecks": 0},
    }
    digest = hashlib.sha256(raw).hexdigest()
    conn.execute(
        "INSERT INTO versions VALUES(?,?,?,?,?,?)",
        (version["id"], "R", number, json.dumps(version), raw, digest),
    )
    return version, raw
