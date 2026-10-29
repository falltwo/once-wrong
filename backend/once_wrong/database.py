"""Normalized immutable evidence and history behind the compatible report API.

Schema initialization is additive. Public JSON snapshots remain untouched during
migration; callers may overlay the normalized history using ``enrich_version``.
All data writes belong to the caller's BEGIN IMMEDIATE transaction.
"""

import hashlib
import inspect
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from once_wrong_ai.rules import RuleSet
from once_wrong_ai.rules.examples import OpeningEqualsClosing, RequiredField
from once_wrong_ai.rules.life import life_field_rules

RELEASES = {
    "demo_csv_v1": "demo_rules_v1",
    "life_underwriting_v1": "life_field_rules_v1",
    "life_filing_v1": "life_filing_rules_v1",
}
POLICY_FIELDS = ["公司代號", "保單編號", "保單編號序號"]
DATASETS = (
    ("DEMO", "demo", "demo", "團隊示範 CSV", ["id"], None),
    (
        "LIFE_UW", "life", "underwriting", "個人壽險承保",
        [*POLICY_FIELDS, "加保日期", "異動序號"], POLICY_FIELDS,
    ),
    (
        "LIFE_CLAIM", "life", "claim", "個人壽險給付",
        ["給付類別", *POLICY_FIELDS], POLICY_FIELDS,
    ),
    (
        "LIFE_SUBJECT", "life", "subject", "個人壽險填報對象",
        ["公司代號", "填報年度", "險別", "保險商品編號", "公司保單險種代號"], None,
    ),
)
_LIFE_MANUAL_SHA256 = "3003e7cf521fb6cc0f69f888ba769a7394f490bd274a9a38dc687e3ae13ca660"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(value) -> str:
    raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def manifest_sha256(files: list[dict]) -> str:
    """Hash sorted [dataset type, exact source hash] pairs; exclude transient ids."""
    pairs = sorted((item["datasetType"], item["sourceSha256"]) for item in files)
    return _sha256(_json(pairs))


def _audit_hash(previous, occurred_at, actor, event_type, version_id, issue_id, payload):
    body = [occurred_at, actor, event_type, version_id, issue_id, json.loads(payload)]
    return _sha256(previous + _json(body))


def register_functions(connection: sqlite3.Connection) -> None:
    """Register deterministic verification functions on every database connection."""
    connection.create_function("sha256", 1, _sha256, deterministic=True)
    connection.create_function(
        "manifest_hash", 1, lambda raw: manifest_sha256(json.loads(raw)), deterministic=True
    )
    connection.create_function("audit_hash", 7, _audit_hash, deterministic=True)


def _handlers() -> dict:
    handlers = {type(rule).__name__: type(rule) for rule in life_field_rules().rules}
    handlers.update(RequiredField=RequiredField, OpeningEqualsClosing=OpeningEqualsClosing)
    return handlers


def initialize(connection: sqlite3.Connection) -> None:
    """Create the additive schema outside a transaction, then seed rule metadata."""
    register_functions(connection)
    connection.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
    immutable = (
        "dataset_type", "rule_set", "rule", "version_file", "record", "issue", "issue_cell",
        "issue_context", "ai_review", "suggestion", "suggestion_change", "citation",
        "confirmations", "audit_event",
    )
    for table in immutable:
        for action in ("UPDATE", "DELETE"):
            connection.execute(
                f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action.lower()} "
                f"BEFORE {action} ON {table} BEGIN "
                f"SELECT RAISE(ABORT,'{table} is immutable'); END"
            )
    connection.executemany(
        "INSERT OR IGNORE INTO dataset_type VALUES(?,?,?,?,?,?)",
        [(code, product, kind, name, _json(keys), _json(group) if group else None)
         for code, product, kind, name, keys, group in DATASETS],
    )
    for profile, release in RELEASES.items():
        is_life = profile != "demo_csv_v1"
        connection.execute(
            """INSERT OR IGNORE INTO rule_set
               (profile_id,version_label,manual_title,manual_sha256,created_at)
               VALUES(?,?,?,?,?)""",
            (
                profile, release,
                "個人壽險填報說明手冊範例與檢核規則 2025（八欄原型規則）"
                if is_life else "團隊示範規則，非官方申報規則",
                _LIFE_MANUAL_SHA256 if is_life else None, _now(),
            ),
        )
        rule_set = _rule_set(connection, profile, release)
        rules = life_field_rules().rules if is_life else [
            RequiredField(rule_id="R-01", column="product"),
            OpeningEqualsClosing(
                rule_id="R-07", closing_column="previous", opening_column="opening"
            ),
        ]
        for item in rules:
            handler = type(item).__name__
            params = {
                name: getattr(item, name)
                for name in inspect.signature(type(item)).parameters
                if name not in {"rule_id", "description"}
            }
            group = item.rule_id in {
                "L0302", "L0303", "L1303", "L1304", "L1305", "L1402", "L1607"
            }
            multi = item.rule_id in {"L0302", "L0303", "L1303", "L1305", "LU1504"}
            connection.execute(
                """INSERT OR IGNORE INTO rule
                   (rule_set_id,code,dataset_type,title,scope,severity,handler,params,
                    issue_key_level,manual_page) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    rule_set, item.rule_id, "LIFE_UW" if is_life else "DEMO",
                    getattr(item, "description", item.rule_id),
                    "multi_record" if multi else "single_record", "error", handler,
                    _json(params), "group" if group else "record",
                    "參、欄位檢核；依規則代碼定位（原型未涵蓋全部規則）" if is_life
                    else "團隊示範，無官方手冊頁碼",
                ),
            )
        if profile == "life_filing_v1":
            for code, dataset, scope, title, page in (
                (
                    "D1001", "LIFE_CLAIM", "single_record", "給付事件日期必須是合法日期",
                    "伍-28；規則手冊實體頁60",
                ),
                (
                    "30307_LD013", "LIFE_CLAIM", "cross_file", "給付須有相符承保終止事件",
                    "伍-31；規則手冊實體頁63、123",
                ),
                (
                    "30301_LD012", "LIFE_UW", "cross_file", "承保終止事件須有相符給付",
                    "伍-31；規則手冊實體頁63、123；未涵蓋30302/30303數量規則",
                ),
            ):
                connection.execute(
                    """INSERT OR IGNORE INTO rule(rule_set_id,code,dataset_type,title,scope,
                       severity,handler,params,issue_key_level,manual_page)
                       VALUES(?,?,?,?,?,'error','evaluate_filing',?,'record',?)""",
                    (rule_set, code, dataset, title, scope, _json({"check": code}), page),
                )


def _rule_set(connection, profile, release):
    row = connection.execute(
        "SELECT id FROM rule_set WHERE profile_id=? AND version_label=?", (profile, release)
    ).fetchone()
    if row is None:
        raise ValueError(f"Unregistered rule release: {profile}/{release}")
    return row[0]


def load_rules(connection, profile_id: str, rule_version: str | None = None) -> RuleSet:
    """Load approved handlers and parameters without dynamic imports or eval."""
    release = rule_version or RELEASES.get(profile_id)
    rule_set = _rule_set(connection, profile_id, release)
    definitions = connection.execute(
        "SELECT code,handler,params FROM rule WHERE rule_set_id=? AND scope<>'cross_file' "
        "AND dataset_type=? "
        "ORDER BY id", (rule_set, "DEMO" if profile_id == "demo_csv_v1" else "LIFE_UW"),
    ).fetchall()
    handlers = _handlers()
    rules = []
    for definition in definitions:
        code, handler, params_json = definition
        if handler not in handlers:
            raise ValueError(f"Unsupported rule handler: {handler}")
        constructor = handlers[handler]
        params = json.loads(params_json)
        allowed = set(inspect.signature(constructor).parameters) - {"rule_id", "description"}
        if not isinstance(params, dict) or not set(params).issubset(allowed):
            raise ValueError(f"Invalid rule parameters: {code}")
        rules.append(constructor(rule_id=code, **params))
    if not rules:
        raise ValueError(f"No executable rules for {profile_id}")
    return RuleSet(rules)


def _boundary(connection, report_id, number, profile):
    return connection.execute(
        """SELECT COALESCE(max(number),0) FROM versions WHERE report_id=? AND number<?
           AND json_extract(payload_json,'$.schemaProfileId')<>?""",
        (report_id, number, profile),
    ).fetchone()[0]


def _issue_key(item: dict, profile: str) -> str:
    if item.get("issueKey"):
        return item["issueKey"]
    return profile + ":" + item["id"]


def annotate_history(
    connection, report_id: str, version_number: int, issues: list[dict],
    profile_id: str = "demo_csv_v1",
) -> list[dict]:
    """Return snapshots annotated from all earlier findings in this profile epoch."""
    boundary = _boundary(connection, report_id, version_number, profile_id)
    annotated = []
    for item in issues:
        key = _issue_key(item, profile_id)
        first, previous = connection.execute(
            """SELECT min(version_number),max(version_number) FROM issue
               WHERE report_id=? AND profile_id=? AND issue_key=?
               AND version_number>? AND version_number<?""",
            (report_id, profile_id, key, boundary, version_number),
        ).fetchone()
        status = (
            "new" if previous is None else
            "repeated" if previous == version_number - 1 else "regressed"
        )
        annotated.append({
            **item, "issueKey": key, "repeatStatus": status,
            "firstSeenNumber": first or version_number, "prevSeenNumber": previous,
            "fixedInNumber": previous + 1 if status == "regressed" else None,
            "repeated": status == "repeated",
        })
    return annotated


def _global_id(*parts) -> str:
    return str(uuid5(NAMESPACE_URL, _json(parts)))


def _file_rows(file):
    for number, item in enumerate(file["rows"], start=1):
        values = item.get("values", item)
        fields = {key: str(value) for key, value in values.items()}
        yield number, item, fields


def _record_for(connection, version_id, location):
    file_id, row_id, number = location.get("fileId"), location.get("rowId"), location.get("row")
    clauses, params = ["version_id=?"], [version_id]
    if file_id is not None:
        clauses.append("file_id=?")
        params.append(file_id)
    if row_id is not None:
        clauses.append("api_row_id=?")
        params.append(str(row_id))
    elif number is not None:
        clauses.append("line_no=?")
        params.append(number)
    else:
        return None
    records = connection.execute(
        "SELECT id,fields,file_id FROM record WHERE " + " AND ".join(clauses), params
    ).fetchall()
    return records[0] if len(records) == 1 else None


def _ensure_rule(connection, rule_set, item, files):
    code = item["ruleId"]
    existing = connection.execute(
        "SELECT id FROM rule WHERE rule_set_id=? AND code=? ORDER BY id", (rule_set, code)
    ).fetchone()
    if existing:
        return existing[0]
    file_kinds = {
        cell.get("datasetType") for cell in item.get("cells", []) if cell.get("datasetType")
    }
    kind = next(iter(file_kinds)) if len(file_kinds) == 1 else files[0]["datasetType"]
    connection.execute(
        """INSERT INTO rule(rule_set_id,code,dataset_type,title,scope,severity,handler,
           params,issue_key_level,manual_page) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            rule_set, code, kind, item.get("title", code), "cross_file",
            item.get("severity", "error"), "ExternalFilingCheck", "{}", "record",
            item.get("manualPage", "跨檔原型檢查；完整手冊規則覆蓋另行記錄"),
        ),
    )
    return connection.execute("SELECT last_insert_rowid()").fetchone()[0]


def persist_version(connection, version: dict, report_id: str, files: list[dict]) -> None:
    """Write complete normalized evidence after inserting the immutable JSON version."""
    profile = version["schemaProfileId"]
    rule_set = _rule_set(connection, profile, version["ruleVersion"])
    issues = annotate_history(
        connection, report_id, version["number"], version["issues"], profile
    )
    connection.execute(
        """INSERT INTO version_state(version_id,profile_id,rule_set_id,manifest_sha256,
           file_count,record_count,issue_count,not_evaluated_checks,sealed)
           VALUES(?,?,?,?,?,?,?,?,0)""",
        (
            version["id"], profile, rule_set, manifest_sha256(files), len(files),
            sum(len(file["rows"]) for file in files), len(issues),
            version["summary"]["notEvaluatedChecks"],
        ),
    )
    for file in files:
        connection.execute(
            """INSERT INTO version_file(id,version_id,dataset_type,filename,source_bytes,
               source_sha256,columns_json) VALUES(?,?,?,?,?,?,?)""",
            (
                file["id"], version["id"], file["datasetType"], file["filename"],
                file["sourceBytes"], file["sourceSha256"], _json(file["columns"]),
            ),
        )
        dataset = connection.execute(
            "SELECT key_fields,group_fields FROM dataset_type WHERE code=?", (file["datasetType"],)
        ).fetchone()
        keys, groups = json.loads(dataset[0]), json.loads(dataset[1]) if dataset[1] else None
        for number, item, fields in _file_rows(file):
            row_id = str(item.get("id", number))
            connection.execute(
                """INSERT INTO record(id,version_id,file_id,line_no,api_row_id,record_key,
                   group_key,fields,raw_line) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    _global_id(version["id"], file["id"], row_id), version["id"], file["id"],
                    item.get("row", number), row_id, _json([fields[key] for key in keys]),
                    _json([fields[key] for key in groups]) if groups else None,
                    _json(fields), item.get("rawLine", _json(fields)),
                ),
            )
    for item in issues:
        normalized_id = _global_id(version["id"], item["id"])
        rule = _ensure_rule(connection, rule_set, item, files)
        connection.execute(
            """INSERT INTO issue(id,api_id,version_id,report_id,version_number,profile_id,
               rule_id,issue_key,message,facts,repeat_status,prev_seen_number,first_seen_number)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                normalized_id, item["id"], version["id"], report_id, version["number"], profile,
                rule, item["issueKey"], item.get("title", item["ruleId"]),
                _json(item.get("facts", {})), item["repeatStatus"], item["prevSeenNumber"],
                item["firstSeenNumber"],
            ),
        )
        cells = item.get("cells")
        if not cells:
            # The legacy demo response has one display field, while the shared
            # comparison rule identifies both input cells. Preserve that actual
            # rule boundary for AI revalidation and normalized evidence.
            definition = connection.execute(
                "SELECT handler,params FROM rule WHERE id=?", (rule,)
            ).fetchone()
            fields = [item["field"]]
            if definition[0] == "OpeningEqualsClosing":
                params = json.loads(definition[1])
                fields = [params["closing_column"], params["opening_column"]]
            cells = [{"rowId": item.get("rowId"), "column": field} for field in fields]
        for cell in cells:
            record = _record_for(connection, version["id"], cell)
            if record is None:
                raise ValueError(f"Ambiguous or absent issue cell: {item['id']}")
            connection.execute(
                "INSERT OR IGNORE INTO issue_cell VALUES(?,?,?)",
                (normalized_id, record[0], cell["column"]),
            )
        for context in item.get("contextRowIds", []):
            location = context if isinstance(context, dict) else {"rowId": context}
            record = _record_for(connection, version["id"], location)
            if record is None:
                raise ValueError(f"Ambiguous or absent issue context: {item['id']}")
            connection.execute(
                "INSERT OR IGNORE INTO issue_context VALUES(?,?)", (normalized_id, record[0])
            )
    connection.execute("UPDATE version_state SET sealed=1 WHERE version_id=?", (version["id"],))
    append_audit(
        connection, "version_uploaded", version_id=version["id"],
        payload={"fileCount": len(files), "manifestSha256": manifest_sha256(files)},
    )
    append_audit(
        connection, "validation_completed", version_id=version["id"],
        payload={"ruleVersion": version["ruleVersion"], "summary": version["summary"]},
    )


def append_audit(
    connection, event_type: str, *, version_id: str | None = None,
    issue_id: str | None = None, payload: dict | None = None, actor: str = "system",
) -> str:
    previous = connection.execute(
        "SELECT hash FROM audit_event ORDER BY id DESC LIMIT 1"
    ).fetchone()
    previous_hash = previous[0] if previous else "0" * 64
    at, content = _now(), _json(payload or {})
    digest = _audit_hash(previous_hash, at, actor, event_type, version_id, issue_id, content)
    connection.execute(
        """INSERT INTO audit_event(occurred_at,actor,event_type,version_id,issue_id,payload,
           prev_hash,hash) VALUES(?,?,?,?,?,?,?,?)""",
        (at, actor, event_type, version_id, issue_id, content, previous_hash, digest),
    )
    return digest


def verify_audit_chain(connection) -> bool:
    previous = "0" * 64
    for row in connection.execute(
        "SELECT occurred_at,actor,event_type,version_id,issue_id,payload,prev_hash,hash "
        "FROM audit_event ORDER BY id"
    ):
        if row[6] != previous or row[7] != _audit_hash(previous, *row[:6]):
            return False
        previous = row[7]
    return True


def persist_ai_review(connection, version_id: str, issue_id: str, payload: dict) -> str:
    normalized = connection.execute(
        "SELECT id FROM issue WHERE version_id=? AND api_id=?", (version_id, issue_id)
    ).fetchone()
    if normalized is None:
        raise ValueError("AI review has no normalized issue")
    review_id = str(uuid4())
    connection.execute(
        """INSERT INTO ai_review(id,issue_id,model,source,title,explanation,blocked_numbers,
           created_at) VALUES(?,?,?,?,?,?,?,?)""",
        (
            review_id, normalized[0], payload["model"], payload["source"], payload["title"],
            payload["explanation"], _json(payload.get("blockedNumbers", [])), _now(),
        ),
    )
    candidates = payload.get("candidates")
    if candidates is None:
        candidates = []
        if payload.get("suggestion"):
            candidates.append({**payload["suggestion"], "revalidation": "passed"})
        candidates.extend(
            {"revalidation": "failed", "rejectionReason": reason, "changes": []}
            for reason in payload.get("rejectedSuggestions", [])
        )
    for rank, candidate in enumerate(candidates, start=1):
        state = candidate.get("revalidation", "failed")
        reason = None if state == "passed" else candidate.get("rejectionReason") or "規則重驗未通過"
        cursor = connection.execute(
            """INSERT INTO suggestion(ai_review_id,rank,reason,revalidation,rejection_reason,
               candidate_json) VALUES(?,?,?,?,?,?)""",
            (review_id, candidate.get("rank", rank), candidate.get("reason", ""), state,
             reason, _json(candidate)),
        )
        seen_changes = {}
        for change in candidate.get("changes", []):
            record = _record_for(connection, version_id, change)
            column = change.get("column")
            if record is None or column not in json.loads(record[1]):
                if state == "passed":
                    raise ValueError("Passed suggestion has an invalid target")
                continue  # Full rejected target remains in candidate_json.
            old = json.loads(record[1])[column]
            new = change.get("value", change.get("new_value"))
            new_text = None if new is None else str(new)
            target = (record[0], column)
            if target in seen_changes:
                if state == "passed" and seen_changes[target] != new_text:
                    raise ValueError("Passed suggestion has conflicting values for one cell")
                continue  # candidate_json retains every raw attempted change.
            seen_changes[target] = new_text
            connection.execute(
                "INSERT INTO suggestion_change VALUES(?,?,?,?,?)",
                (cursor.lastrowid, record[0], column, old, new_text),
            )
    for citation in payload.get("citations", []):
        connection.execute(
            "INSERT OR IGNORE INTO citation VALUES(?,?,?,?,?)",
            (
                review_id, citation["id"], citation["source"], _json(citation.get("section", [])),
                str(citation.get("page", "")),
            ),
        )
    append_audit(
        connection, "ai_review_completed", version_id=version_id, issue_id=normalized[0],
        payload={
            "reviewId": review_id, "source": payload["source"], "candidateCount": len(candidates)
        },
    )
    return review_id


def migrate_existing(connection) -> int:
    """Backfill old JSON snapshots in order without altering any original table row."""
    rows = connection.execute(
        """SELECT v.id,v.report_id,v.payload_json,v.source_bytes,v.source_sha256
           FROM versions AS v LEFT JOIN version_state AS s ON s.version_id=v.id
           WHERE s.version_id IS NULL ORDER BY v.report_id,v.number"""
    ).fetchall()
    for row in rows:
        version = json.loads(row[2])
        is_demo = version["schemaProfileId"] == "demo_csv_v1"
        if not is_demo:
            from .issue_identity import life_issue_key

            for item in version["issues"]:
                item["issueKey"] = item.get("issueKey") or life_issue_key(item, version["rows"])
        file = {
            "id": _global_id("legacy-file", row[0]),
            "datasetType": "DEMO" if is_demo else "LIFE_UW",
            "filename": version["filename"], "sourceBytes": bytes(row[3]),
            "sourceSha256": row[4], "columns": version.get("columns") or [
                "id", "product", "previous", "opening"
            ], "rows": version["rows"],
        }
        persist_version(connection, version, row[1], [file])
    return len(rows)


def enrich_version(connection, version: dict) -> dict:
    """Overlay normalized history on a copied public snapshot, including legacy rows."""
    states = {
        row[0]: row[1:]
        for row in connection.execute(
            "SELECT api_id,issue_key,repeat_status,prev_seen_number,first_seen_number "
            "FROM issue WHERE version_id=?", (version["id"],)
        )
    }
    enriched = []
    for item in version["issues"]:
        state = states.get(item["id"])
        if state:
            key, status, previous, first = state
            item = {
                **item, "issueKey": key, "repeatStatus": status, "prevSeenNumber": previous,
                "firstSeenNumber": first,
                "fixedInNumber": previous + 1 if status == "regressed" else None,
                "repeated": status == "repeated",
            }
        enriched.append(item)
    return {**version, "issues": enriched}
