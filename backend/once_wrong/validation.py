"""Strict demo CSV ingestion and two deterministic, non-official demo rules."""

import csv
import io
import re

from .models import MAX_SAFE_INTEGER

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1_000
SCHEMA_PROFILE = "demo_csv_v1"
RULE_VERSION = "demo_rules_v1"
REQUIRED_COLUMNS = ("id", "product", "previous", "opening")


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


def parse_csv(raw: bytes) -> list[dict]:
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
        missing = [column for column in REQUIRED_COLUMNS if column not in columns]
        if missing:
            raise _invalid("CSV 缺少必要欄位。", missingColumns=missing)
        for values in reader:
            if not any(value.strip() for value in values):
                continue
            if len(values) != len(columns):
                raise _invalid("CSV 每行欄位數須與標頭一致。", line=reader.line_num)
            if len(rows) >= MAX_ROWS:
                raise _invalid("CSV 最多可包含 1,000 筆資料。")
            source = dict(zip(columns, values, strict=True))
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
    return rows


def validate(rows: list[dict], previous_issues: list[dict] | None = None) -> list[dict]:
    """The frontend's R-01/R-07 only; neither is an official insurance rule."""
    previous_keys = {(issue["rowId"], issue["ruleId"]) for issue in previous_issues or []}
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
                    "repeated": (row["id"], "R-07") in previous_keys,
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
                    "repeated": (row["id"], "R-01") in previous_keys,
                }
            )
    return issues


def summary(rows: list[dict], issues: list[dict]) -> dict:
    total = len(rows) * 2
    return {
        "totalChecks": total,
        "passedChecks": total - len(issues),
        "failedChecks": len(issues),
        "notEvaluatedChecks": 0,
    }
