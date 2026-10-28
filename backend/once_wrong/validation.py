"""Strict profile-aware CSV ingestion and server-owned rule evaluation."""

import csv
import io
import re
from dataclasses import dataclass

from once_wrong_ai.ai_review.api import issue_payloads
from once_wrong_ai.report import Report
from once_wrong_ai.rules import RuleSet
from once_wrong_ai.rules.examples import OpeningEqualsClosing, RequiredField
from once_wrong_ai.rules.life import life_field_rules

from .models import MAX_SAFE_INTEGER

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1_000
SCHEMA_PROFILE = "demo_csv_v1"
RULE_VERSION = "demo_rules_v1"
REQUIRED_COLUMNS = ("id", "product", "previous", "opening")
LIFE_SCHEMA_PROFILE = "life_underwriting_v1"
LIFE_RULE_VERSION = "life_field_rules_v1"
LIFE_COLUMNS = (
    "公司代號", "保單編號", "保單編號序號", "異動序號", "加保別", "加保日期", "退保別", "退保日期"
)
PROFILE_RULE_VERSIONS = {
    SCHEMA_PROFILE: RULE_VERSION,
    LIFE_SCHEMA_PROFILE: LIFE_RULE_VERSION,
}


@dataclass
class ParsedCSV:
    schema_profile_id: str
    rule_version: str
    columns: list[str]
    rows: list[dict]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def _invalid(message: str, **details: object) -> ApiError:
    return ApiError(422, "INVALID_CSV", message, details or None)


def _check_quoting(text: str) -> None:
    """Reject quotes in unquoted fields as well as unterminated quoted fields.

    csv.reader(strict=True) checks closing quotes, but permits literal quotes in
    unquoted fields. The profile deliberately uses strict RFC-style CSV quoting.
    """
    state = "start"
    for character in text:
        if state == "quoted":
            if character == '"':
                state = "after_quote"
        elif state == "after_quote":
            if character == '"':
                state = "quoted"
            elif character in ",\r\n":
                state = "start"
            else:
                raise _invalid("CSV 引號結束後只能接逗號或換行。")
        elif character == '"':
            if state != "start":
                raise _invalid("CSV 未加引號的欄位中包含引號。")
            state = "quoted"
        elif character in ",\r\n":
            state = "start"
        else:
            state = "unquoted"
    if state == "quoted":
        raise _invalid("CSV 包含未結束的引號。")


def parse_profile_csv(raw: bytes) -> ParsedCSV:
    if len(raw) > MAX_FILE_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "檔案不可超過 2 MiB。")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise _invalid("檔案須使用 UTF-8 編碼。") from error
    _check_quoting(text)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    rows: list[dict] = []
    ids: set[str] = set()
    try:
        # Match the frontend's skipEmptyLines=greedy, including leading blank lines.
        header = next((row for row in reader if any(value.strip() for value in row)), None)
        if header is None:
            raise _invalid("CSV 缺少標頭與資料。")
        columns = [value.strip().removeprefix("\ufeff") for value in header]
        if any(not column for column in columns) or len(set(columns)) != len(columns):
            raise _invalid("CSV 標頭不可空白或重複。")
        is_life = set(columns) == set(LIFE_COLUMNS)
        if not is_life:
            missing = [column for column in REQUIRED_COLUMNS if column not in columns]
            if missing:
                raise _invalid(
                    "CSV 須包含 demo 必要欄位，或使用完整的 8 欄壽險承保資料。",
                    missingColumns=missing,
                    lifeColumns=list(LIFE_COLUMNS),
                )
        for values in reader:
            if not any(value.strip() for value in values):
                continue
            if len(values) != len(columns):
                raise _invalid("CSV 每行欄位數須與標頭一致。", line=reader.line_num)
            if len(rows) >= MAX_ROWS:
                raise _invalid("CSV 最多可包含 1,000 筆資料。")
            source = dict(zip(columns, values, strict=True))
            if is_life:
                number = len(rows) + 1
                rows.append({"id": str(number), "row": number, "values": source})
                continue
            row_id = source["id"].strip()
            if not row_id or row_id in ids:
                raise _invalid("資料 id 不可空白或重複。", line=reader.line_num, field="id")
            ids.add(row_id)
            row: dict = {"id": row_id, "product": source["product"].strip()}
            for field in ("previous", "opening"):
                value = source[field].strip()
                # Compare decimal text before int(): this avoids oversized integer
                # conversion limits and never rounds through a binary float.
                significant = value.lstrip("0") or "0"
                maximum = str(MAX_SAFE_INTEGER)
                if (
                    not re.fullmatch(r"[0-9]+", value)
                    or len(significant) > len(maximum)
                    or (len(significant) == len(maximum) and significant > maximum)
                ):
                    raise _invalid(
                        "金額須為非負 ASCII 十進位整數，且不超過 JavaScript 安全整數上限。",
                        line=reader.line_num,
                        field=field,
                    )
                row[field] = int(significant)
            rows.append(row)
    except csv.Error as error:
        raise _invalid("CSV 格式不完整，請檢查欄位及引號。", line=reader.line_num) from error
    if not rows:
        raise _invalid("CSV 至少須包含一筆資料。")
    return ParsedCSV(
        schema_profile_id=LIFE_SCHEMA_PROFILE if is_life else SCHEMA_PROFILE,
        rule_version=LIFE_RULE_VERSION if is_life else RULE_VERSION,
        columns=columns if is_life else list(REQUIRED_COLUMNS),
        rows=rows,
    )


def parse_csv(raw: bytes) -> list[dict]:
    """Retain the original demo-only parser contract for existing integrations."""
    parsed = parse_profile_csv(raw)
    if parsed.schema_profile_id != SCHEMA_PROFILE:
        raise _invalid("此解析介面只接受 demo CSV；壽險資料請使用 profile 解析介面。")
    return parsed.rows


def validate(rows: list[dict], previous_issues: list[dict] | None = None) -> list[dict]:
    """The frontend's R-01/R-07 only; neither is an official insurance rule."""
    previous_ids = {issue["id"] for issue in previous_issues or []}
    issues: list[dict] = []
    for row in rows:
        if row["previous"] != row["opening"]:
            issues.append(
                {
                    "id": f"{row['id']}:R-07",
                    "ruleId": "R-07",
                    "rowId": row["id"],
                    "field": "opening",
                    "title": "期初與上期末金額不一致",
                    "actual": row["opening"],
                    "expected": row["previous"],
                    "repeated": f"{row['id']}:R-07" in previous_ids,
                }
            )
        if not row["product"].strip():
            issues.append(
                {
                    "id": f"{row['id']}:R-01",
                    "ruleId": "R-01",
                    "rowId": row["id"],
                    "field": "product",
                    "title": "險種代碼不可空白",
                    "actual": "空白",
                    "repeated": f"{row['id']}:R-01" in previous_ids,
                }
            )
    return issues


def rules_for_profile(profile_id: str) -> RuleSet:
    if profile_id == LIFE_SCHEMA_PROFILE:
        return life_field_rules()
    if profile_id == SCHEMA_PROFILE:
        return RuleSet([
            RequiredField(rule_id="R-01", column="product"),
            OpeningEqualsClosing(
                rule_id="R-07", closing_column="previous", opening_column="opening"
            ),
        ])
    raise ApiError(422, "UNSUPPORTED_SCHEMA_PROFILE", "不支援此報表資料格式。")


def report_for_version(version: dict, report_id: str) -> Report:
    is_life = version["schemaProfileId"] == LIFE_SCHEMA_PROFILE
    rules_for_profile(version["schemaProfileId"])
    return Report(
        report_id=report_id,
        version=version["number"],
        columns=list(version["columns"]) if is_life else list(REQUIRED_COLUMNS),
        rows=[dict(row["values"]) for row in version["rows"]] if is_life else version["rows"],
        numeric_columns=set() if is_life else {"previous", "opening"},
        meta={"險別": "個人壽險"} if is_life else {},
    )


def validate_profile(
    rows: list[dict], profile_id: str, previous_issues: list[dict] | None = None
) -> list[dict]:
    if profile_id == SCHEMA_PROFILE:
        return validate(rows, previous_issues)
    rules = rules_for_profile(profile_id)
    report = report_for_version(
        {
            "schemaProfileId": profile_id,
            "number": 1,
            "columns": list(LIFE_COLUMNS),
            "rows": rows,
        },
        report_id="validation",
    )
    previous_ids = {issue["id"] for issue in previous_issues or []}
    payloads = issue_payloads(report.rows, rules.check(report), row_id=str)
    issues = [item.model_dump() for item in payloads]
    for issue in issues:
        issue["repeated"] = issue["id"] in previous_ids
    return issues


def summary(rows: list[dict], issues: list[dict], profile_id: str = SCHEMA_PROFILE) -> dict:
    total = len(rows) * len(rules_for_profile(profile_id).rules)
    failed = (
        len({(issue["ruleId"], row) for issue in issues for row in issue["rows"]})
        if profile_id == LIFE_SCHEMA_PROFILE
        else len(issues)
    )
    return {
        "totalChecks": total,
        "passedChecks": total - failed,
        "failedChecks": failed,
        "notEvaluatedChecks": 0,
    }
