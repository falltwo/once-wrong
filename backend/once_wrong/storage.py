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

from . import database
from .filing import (
    FILING_RULE_VERSION,
    FILING_SCHEMA_PROFILE,
    evaluate_filing,
    parse_filing,
)
from .validation import (
    PROFILE_RULE_VERSIONS,
    SCHEMA_PROFILE,
    ApiError,
    parse_profile_csv,
    summary,
    validate,
    validate_profile,
)

SUGGESTION_CACHE_REVISION = "error-cells-v2-normalized"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        database.register_functions(connection)
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
        self._backup_before_migration()
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
                    cache_revision TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (version_id, issue_id)
                );
                """
            )
        with self._transaction() as connection:
            # Old caches were validated against whole rows. Preserve them, but
            # never serve them under the stricter error-cell policy.
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(suggestions)")}
            if "cache_revision" not in columns:
                connection.execute(
                    "ALTER TABLE suggestions ADD COLUMN cache_revision TEXT NOT NULL DEFAULT ''"
                )
            report_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(reports)")
            }
            for name, kind in (
                ("company_code", "TEXT"), ("product", "TEXT"), ("filing_year", "INTEGER")
            ):
                if name not in report_columns:
                    connection.execute(f"ALTER TABLE reports ADD COLUMN {name} {kind}")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS reports_filing_identity "
                "ON reports(company_code,product,filing_year) "
                "WHERE company_code IS NOT NULL AND product IS NOT NULL "
                "AND filing_year IS NOT NULL"
            )
        with self._connection() as connection:
            database.initialize(connection)
        with self._transaction() as connection:
            database.migrate_existing(connection)
        if seed_demo:
            self._seed_demo()

    def _backup_before_migration(self) -> None:
        if not self.database_path.exists() or self.database_path.stat().st_size == 0:
            return
        with self._connection() as connection:
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='version_state'"
            ).fetchone():
                return
            backup_dir = self.database_path.parent / "backups"
            backup_dir.mkdir(exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            target = backup_dir / f"{self.database_path.stem}.pre-normalized-{stamp}.sqlite3"
            with sqlite3.connect(target) as backup:
                connection.backup(backup)

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
    def _can_submit(version: dict | None, connection: sqlite3.Connection) -> bool:
        if not version:
            return False
        profile = version["schemaProfileId"]
        if profile == FILING_SCHEMA_PROFILE:
            check = evaluate_filing(
                version["files"], rules=database.load_rules(connection, profile)
            )
            return (
                version["ruleVersion"] == FILING_RULE_VERSION
                and check["summary"]["notEvaluatedChecks"] == 0
                and not check["issues"]
            )
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
                else validate_profile(
                    version["rows"], profile,
                    rules=database.load_rules(connection, profile, version["ruleVersion"]),
                )
            )
        )

    def _report_payload(self, connection: sqlite3.Connection, record: sqlite3.Row) -> dict:
        versions = [
            database.enrich_version(connection, json.loads(row["payload_json"]))
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
                and self._can_submit(versions[-1], connection)
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
        issues = validate_profile(
            rows, parsed.schema_profile_id,
            rules=database.load_rules(connection, parsed.schema_profile_id, parsed.rule_version),
        )
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
        source = {
            "id": str(uuid4()),
            "datasetType": "DEMO" if parsed.schema_profile_id == SCHEMA_PROFILE else "LIFE_UW",
            "filename": filename, "sourceBytes": raw, "sourceSha256": source_hash,
            "columns": parsed.columns, "rows": rows,
        }
        return Store._persist_version(connection, report_id, version, [source], raw)

    @staticmethod
    def _persist_version(connection, report_id, version, files, raw):
        version["issues"] = [
            {key: value for key, value in item.items() if value is not None}
            for item in database.annotate_history(
                connection, report_id, version["number"], version["issues"],
                version["schemaProfileId"],
            )
        ]
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
                version["sourceSha256"],
            ),
        )
        database.persist_version(connection, version, report_id, files)
        return version

    @staticmethod
    def _insert_filing(connection, report_id, inputs):
        parsed = parse_filing(inputs)
        report = Store._report_record(connection, report_id)
        year = int(report["period"][:4])
        if parsed.filing_year is not None and parsed.filing_year != year:
            raise ApiError(422, "FILING_YEAR_MISMATCH", "申報檔年度與報表期間不一致。")
        if report["company_code"] and report["company_code"] != parsed.company_code:
            raise ApiError(422, "FILING_COMPANY_MISMATCH", "修訂必須屬於同一家公司。")
        existing = connection.execute(
            "SELECT id FROM reports WHERE company_code=? AND product='life' "
            "AND filing_year=? AND id<>?", (parsed.company_code, year, report_id),
        ).fetchone()
        if existing:
            raise ApiError(
                409, "REPORT_ALREADY_EXISTS", "該公司、險種與年度已有申報，請在原報表新增修訂。",
                {"reportId": existing["id"]},
            )
        connection.execute(
            "UPDATE reports SET company_code=?, product='life', filing_year=? WHERE id=?",
            (parsed.company_code, year, report_id),
        )
        result = evaluate_filing(
            parsed, rules=database.load_rules(connection, FILING_SCHEMA_PROFILE)
        )
        number = connection.execute(
            "SELECT COALESCE(max(number),0)+1 FROM versions WHERE report_id=?", (report_id,)
        ).fetchone()[0]
        digest = database.manifest_sha256(parsed.files)
        manifest = sorted((file["datasetType"], file["sourceSha256"]) for file in parsed.files)
        raw = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        version = {
            "id": str(uuid4()), "number": number,
            "filename": " + ".join(file["filename"] for file in parsed.files),
            "createdAt": _now(), "rows": parsed.rows, "columns": parsed.columns,
            "files": parsed.files, "issues": result["issues"],
            "schemaProfileId": FILING_SCHEMA_PROFILE, "ruleVersion": FILING_RULE_VERSION,
            "validationStatus": "completed", "validationRunId": str(uuid4()),
            "sourceSha256": digest, "manifestSha256": digest,
            "summary": result["summary"], "evidence": result["evidence"],
        }
        sources = [
            {**file, "sourceBytes": parsed.raw_by_file[file["id"]]} for file in parsed.files
        ]
        return Store._persist_version(connection, report_id, version, sources, raw)

    def create_filing(self, name, period, inputs):
        report_id = str(uuid4())
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO reports(id,name,period) VALUES(?,?,?)", (report_id, name, period)
            )
            self._insert_filing(connection, report_id, inputs)
            return self._report_payload(connection, self._report_record(connection, report_id))

    def add_filing(self, report_id, inputs):
        with self._transaction() as connection:
            version = self._insert_filing(connection, report_id, inputs)
            connection.execute(
                "UPDATE reports SET submitted_version_id=NULL WHERE id=?", (report_id,)
            )
            return version

    def rule_sets(self):
        with self._connection() as connection:
            return {
                profile: database.load_rules(connection, profile)
                for profile in PROFILE_RULE_VERSIONS
            }

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
            if payload["schemaProfileId"] == FILING_SCHEMA_PROFILE:
                raise ApiError(
                    409, "FILE_ID_REQUIRED", "此版本有申報檔案清單，請指定 fileId 下載。"
                )
            return bytes(record["source_bytes"]), payload["filename"], record["source_sha256"]

    def get_file_source(self, version_id, file_id):
        with self._connection() as connection:
            self._version_record(connection, version_id)
            source = connection.execute(
                "SELECT source_bytes,filename,source_sha256 FROM version_file "
                "WHERE version_id=? AND id=?", (version_id, file_id),
            ).fetchone()
            if source is None:
                raise ApiError(404, "FILE_NOT_FOUND", "此版本找不到指定檔案。")
            return bytes(source[0]), source[1], source[2]

    def get_version(self, version_id: str) -> dict:
        with self._connection() as connection:
            record = self._version_record(connection, version_id)
            version = database.enrich_version(connection, json.loads(record["payload_json"]))
            return {**version, "reportId": record["report_id"]}

    def save_review(self, version_id, issue_id, payload):
        with self._transaction() as connection:
            review = {**payload, "candidates": payload.get("_candidates")}
            database.persist_ai_review(connection, version_id, issue_id, review)

    def get_cached_suggestion(self, version_id: str, issue_id: str) -> dict | None:
        with self._connection() as connection:
            record = connection.execute(
                """SELECT payload_json FROM suggestions
                   WHERE version_id = ? AND issue_id = ? AND cache_revision = ?""",
                (version_id, issue_id, SUGGESTION_CACHE_REVISION),
            ).fetchone()
            payload = json.loads(record["payload_json"]) if record else None
            return payload if payload and payload["source"] == "ai" else None

    def save_suggestion(self, version_id: str, issue_id: str, payload: dict) -> None:
        if payload["source"] != "ai":
            return
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO suggestions
                   (version_id, issue_id, payload_json, model, created_at, cache_revision)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(version_id, issue_id) DO UPDATE SET
                     payload_json = excluded.payload_json, model = excluded.model,
                     created_at = excluded.created_at, cache_revision = excluded.cache_revision""",
                (version_id, issue_id, json.dumps(payload, ensure_ascii=False),
                 payload["model"], _now(), SUGGESTION_CACHE_REVISION),
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
            if not self._can_submit(version, connection):
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
            database.append_audit(
                connection, "version_confirmed", version_id=version_id,
                payload={"sourceSha256": record["source_sha256"],
                         "ruleVersion": version["ruleVersion"]},
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
