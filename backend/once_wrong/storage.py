"""SQLite persistence with atomic raw-source, version and confirmation writes."""

import csv
import hashlib
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .validation import (
    PROFILE_RULE_VERSIONS,
    SCHEMA_PROFILE,
    ApiError,
    parse_profile_csv,
    summary,
    validate,
    validate_profile,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self):
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def initialize(self, *, seed_demo: bool) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    period TEXT NOT NULL,
                    submitted_version_id TEXT
                );
                CREATE TABLE IF NOT EXISTS versions (
                    id TEXT PRIMARY KEY,
                    report_id TEXT NOT NULL REFERENCES reports(id),
                    number INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    source_bytes BLOB NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    UNIQUE(report_id, number)
                );
                CREATE TABLE IF NOT EXISTS confirmations (
                    id TEXT PRIMARY KEY,
                    report_id TEXT NOT NULL REFERENCES reports(id),
                    version_id TEXT NOT NULL REFERENCES versions(id),
                    confirmed_at TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    rule_version TEXT NOT NULL,
                    UNIQUE(report_id, version_id)
                );
                CREATE INDEX IF NOT EXISTS versions_report_order
                    ON versions(report_id, number);
                CREATE TABLE IF NOT EXISTS suggestions (
                    version_id TEXT NOT NULL REFERENCES versions(id),
                    issue_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (version_id, issue_id)
                );
                """
            )
        if seed_demo:
            self._seed_demo()

    @staticmethod
    def _report_record(connection: sqlite3.Connection, report_id: str) -> sqlite3.Row:
        record = connection.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if record is None:
            raise ApiError(404, "REPORT_NOT_FOUND", "找不到這份報表。")
        return record

    @staticmethod
    def _version_record(connection: sqlite3.Connection, version_id: str) -> sqlite3.Row:
        record = connection.execute("SELECT * FROM versions WHERE id = ?", (version_id,)).fetchone()
        if record is None:
            raise ApiError(404, "VERSION_NOT_FOUND", "找不到這份修訂。")
        return record

    @staticmethod
    def _can_submit(version: dict | None) -> bool:
        if not version:
            return False
        profile = version["schemaProfileId"]
        supported = PROFILE_RULE_VERSIONS.get(profile)
        if supported is None:
            return False
        return (
            version["ruleVersion"] == supported
            and version["validationStatus"] == "completed"
            and version["summary"]["notEvaluatedChecks"] == 0
            and not (
                validate(version["rows"])
                if profile == SCHEMA_PROFILE
                else validate_profile(version["rows"], profile)
            )
        )

    def _report_payload(self, connection: sqlite3.Connection, record: sqlite3.Row) -> dict:
        versions = [
            json.loads(row["payload_json"])
            for row in connection.execute(
                "SELECT payload_json FROM versions WHERE report_id = ? ORDER BY number",
                (record["id"],),
            )
        ]
        payload = {
            "id": record["id"],
            "name": record["name"],
            "period": record["period"],
            "versions": versions,
            "canSubmit": bool(
                versions
                and record["submitted_version_id"] != versions[-1]["id"]
                and self._can_submit(versions[-1])
            ),
        }
        if record["submitted_version_id"]:
            payload["submittedVersionId"] = record["submitted_version_id"]
        return payload

    def list_reports(self) -> list[dict]:
        with self._connection() as connection:
            # Keep the report row and its version list on one SQLite read snapshot.
            connection.execute("BEGIN")
            records = connection.execute("SELECT * FROM reports ORDER BY id").fetchall()
            return [self._report_payload(connection, record) for record in records]

    def get_report(self, report_id: str) -> dict:
        with self._connection() as connection:
            connection.execute("BEGIN")
            return self._report_payload(connection, self._report_record(connection, report_id))

    @staticmethod
    def _insert_version(
        connection: sqlite3.Connection,
        report_id: str,
        raw: bytes,
        filename: str,
        *,
        version_id: str | None = None,
        created_at: str | None = None,
    ) -> dict:
        parsed = parse_profile_csv(raw)
        rows = parsed.rows
        previous_record = connection.execute(
            "SELECT payload_json FROM versions WHERE report_id = ? ORDER BY number DESC LIMIT 1",
            (report_id,),
        ).fetchone()
        previous = json.loads(previous_record["payload_json"]) if previous_record else None
        previous_issues = (
            previous["issues"]
            if previous and previous["schemaProfileId"] == parsed.schema_profile_id
            else None
        )
        issues = validate_profile(rows, parsed.schema_profile_id, previous_issues)
        source_hash = hashlib.sha256(raw).hexdigest()
        version = {
            "id": version_id or str(uuid4()),
            "number": previous["number"] + 1 if previous else 1,
            "filename": filename,
            "createdAt": created_at or _now(),
            "rows": rows,
            "issues": issues,
            "schemaProfileId": parsed.schema_profile_id,
            "ruleVersion": parsed.rule_version,
            "validationStatus": "completed",
            "validationRunId": str(uuid4()),
            "sourceSha256": source_hash,
            "summary": summary(rows, issues, profile_id=parsed.schema_profile_id),
        }
        if parsed.schema_profile_id != SCHEMA_PROFILE:
            version["columns"] = parsed.columns
        connection.execute(
            """INSERT INTO versions
               (id, report_id, number, payload_json, source_bytes, source_sha256)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                version["id"],
                report_id,
                version["number"],
                json.dumps(version, ensure_ascii=False),
                raw,
                source_hash,
            ),
        )
        return version

    def create_report(self, name: str, period: str, raw: bytes, filename: str) -> dict:
        """Commit a report and its validated first version together, or neither."""
        report_id = str(uuid4())
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO reports (id, name, period) VALUES (?, ?, ?)",
                (report_id, name, period),
            )
            self._insert_version(connection, report_id, raw, filename)
            return self._report_payload(connection, self._report_record(connection, report_id))

    def add_version(self, report_id: str, raw: bytes, filename: str) -> dict:
        with self._transaction() as connection:
            self._report_record(connection, report_id)
            version = self._insert_version(connection, report_id, raw, filename)
            # Confirmation history stays immutable; only the current pointer is cleared.
            connection.execute(
                "UPDATE reports SET submitted_version_id = NULL WHERE id = ?", (report_id,)
            )
            return version

    def get_source(self, version_id: str) -> tuple[bytes, str, str]:
        with self._connection() as connection:
            record = self._version_record(connection, version_id)
            payload = json.loads(record["payload_json"])
            return bytes(record["source_bytes"]), payload["filename"], record["source_sha256"]

    def get_version(self, version_id: str) -> dict:
        with self._connection() as connection:
            record = self._version_record(connection, version_id)
            return {**json.loads(record["payload_json"]), "reportId": record["report_id"]}

    def get_cached_suggestion(self, version_id: str, issue_id: str) -> dict | None:
        with self._connection() as connection:
            record = connection.execute(
                "SELECT payload_json FROM suggestions WHERE version_id = ? AND issue_id = ?",
                (version_id, issue_id),
            ).fetchone()
            return json.loads(record["payload_json"]) if record else None

    def save_suggestion(self, version_id: str, issue_id: str, payload: dict) -> None:
        if payload["source"] == "fallback_llm_error":
            return
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO suggestions
                   (version_id, issue_id, payload_json, model, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(version_id, issue_id) DO NOTHING""",
                (version_id, issue_id, json.dumps(payload, ensure_ascii=False),
                 payload["model"], _now()),
            )

    def confirm(self, report_id: str, version_id: str) -> None:
        with self._transaction() as connection:
            self._report_record(connection, report_id)
            record = connection.execute(
                "SELECT * FROM versions WHERE report_id = ? ORDER BY number DESC LIMIT 1",
                (report_id,),
            ).fetchone()
            version = json.loads(record["payload_json"]) if record else None
            if version is None or version["id"] != version_id:
                raise ApiError(409, "STALE_VERSION", "只能確認目前最新的修訂。")
            if not self._can_submit(version):
                raise ApiError(409, "VALIDATION_FAILED", "最新修訂尚未通過此資料格式的後端檢核。")
            # No remote submission occurs. Record the actual immutable input and rule release.
            connection.execute(
                """INSERT INTO confirmations
                   (id, report_id, version_id, confirmed_at, source_sha256, rule_version)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(report_id, version_id) DO NOTHING""",
                (
                    str(uuid4()),
                    report_id,
                    version_id,
                    _now(),
                    record["source_sha256"],
                    version["ruleVersion"],
                ),
            )
            connection.execute(
                "UPDATE reports SET submitted_version_id = ? WHERE id = ?", (version_id, report_id)
            )

    def _seed_demo(self) -> None:
        report_id = "reserve-202609"
        with self._transaction() as connection:
            if connection.execute("SELECT 1 FROM reports WHERE id = ?", (report_id,)).fetchone():
                return
            connection.execute(
                "INSERT INTO reports (id, name, period) VALUES (?, ?, ?)",
                (report_id, "準備金月報", "2026-09"),
            )
            rows = [
                ["POL-001", "CR-01", 9812400, 9812400],
                ["POL-002", "CR-02", 4105000, 4105000],
                ["POL-003", "ML-05", 12480000, 12005000],
                ["POL-004", "", 1020300, 1020300],
                ["POL-005", "WL-02", 7340000, 7340000],
                ["POL-006", "AN-03", 2560000, 2560000],
            ]
            first_rows = [row.copy() for row in rows]
            first_rows[0][3] = 9800000
            first_rows[3][1] = "CR-04"
            for number, fixture in ((1, first_rows), (2, rows)):
                output = io.StringIO(newline="")
                writer = csv.writer(output, lineterminator="\r\n")
                writer.writerow(["id", "product", "previous", "opening"])
                writer.writerows(fixture)
                self._insert_version(
                    connection,
                    report_id,
                    output.getvalue().encode("utf-8"),
                    f"reserve_202609_v{number}.csv",
                    version_id=f"v{number}",
                    created_at=(
                        "2026-10-24T09:30:00+08:00" if number == 1 else "2026-10-24T10:15:00+08:00"
                    ),
                )
