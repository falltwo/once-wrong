"""Materialize an actual pre-normalization database without disabling live guards."""

import hashlib
import json
import sqlite3


def create_legacy_database(path, report_id, version, source):
    payload = json.dumps(version, ensure_ascii=False)
    digest = hashlib.sha256(source).hexdigest()
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE reports (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, period TEXT NOT NULL,
                submitted_version_id TEXT
            );
            CREATE TABLE versions (
                id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES reports(id),
                number INTEGER NOT NULL, payload_json TEXT NOT NULL,
                source_bytes BLOB NOT NULL, source_sha256 TEXT NOT NULL,
                UNIQUE(report_id,number)
            );
            CREATE TABLE confirmations (
                id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES reports(id),
                version_id TEXT NOT NULL REFERENCES versions(id), confirmed_at TEXT NOT NULL,
                source_sha256 TEXT NOT NULL, rule_version TEXT NOT NULL,
                UNIQUE(report_id,version_id)
            );
            CREATE TABLE suggestions (
                version_id TEXT NOT NULL REFERENCES versions(id), issue_id TEXT NOT NULL,
                payload_json TEXT NOT NULL, model TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(version_id,issue_id)
            );
            """
        )
        connection.execute(
            "INSERT INTO reports(id,name,period) VALUES(?,?,?)",
            (report_id, "舊版壽險資料", "2025-10"),
        )
        connection.execute(
            "INSERT INTO versions VALUES(?,?,?,?,?,?)",
            (version["id"], report_id, version["number"], payload, source, digest),
        )
    return payload
