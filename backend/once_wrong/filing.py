"""Atomic, text-preserving life filing bundles with explicit rule coverage.

CSV is an interchange format for this prototype, not the official fixed-width
filing format. Extra official columns are retained but do not imply that their
rules were evaluated. Missing and unimplemented rule families remain visible.
"""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from once_wrong_ai.ai_review.api import issue_payloads
from once_wrong_ai.report import Report
from once_wrong_ai.rules import RuleSet
from once_wrong_ai.rules.life import life_field_rules

from .validation import LIFE_COLUMNS, MAX_FILE_BYTES, MAX_ROWS, ApiError, _check_quoting

FILING_SCHEMA_PROFILE = "life_filing_v1"
FILING_RULE_VERSION = "life_filing_rules_v1"
LIFE_UW = "LIFE_UW"
LIFE_CLAIM = "LIFE_CLAIM"
LIFE_SUBJECT = "LIFE_SUBJECT"
MAX_FILING_FILES = 3
POLICY_FIELDS = ("公司代號", "保單編號", "保單編號序號")
KEY_FIELDS = {
    LIFE_UW: (*POLICY_FIELDS, "加保日期", "異動序號"),
    LIFE_CLAIM: ("給付類別", *POLICY_FIELDS),
    LIFE_SUBJECT: ("公司代號", "填報年度", "險別", "保險商品編號", "公司保單險種代號"),
}
CLAIM_DATE_COLUMNS = ("發生日期", "事故日期", "死亡完全失能日期")
TERMINATED_EXITS = {"DEA", "ADS", "TDI", "ATS", "ABD"}
TERMINATION_CLAIMS = {"1", "2", "3"}
SOURCE_REFERENCES = [
    {
        "sourceTitle": "人壽保險業個人壽險填報手冊 2025",
        "section": "承保／給付／填報對象資料 key 值順序",
        "page": "5,31,37",
    },
    {
        "sourceTitle": "個人壽險填報說明手冊範例與檢核規則 2025",
        "section": "伍-28 D1001；伍-31 LD00-01、LD00-02（事故日期為關聯條件）",
        "page": "60,63,123",
    },
]


@dataclass
class ParsedFiling:
    files: list[dict]
    company_code: str
    filing_year: int | None
    raw_by_file: dict[str, bytes] = field(repr=False)
    schema_profile_id: str = FILING_SCHEMA_PROFILE
    rule_version: str = FILING_RULE_VERSION

    @property
    def rows(self) -> list[dict]:
        return [row for source in self.files for row in source["rows"]]

    @property
    def columns(self) -> list[str]:
        return list(dict.fromkeys(column for source in self.files for column in source["columns"]))


def _invalid(message: str, **details) -> ApiError:
    return ApiError(422, "INVALID_FILING", message, details or None)


def _dataset_type(columns: list[str]) -> tuple[str, str | None]:
    names = set(columns)
    claim_dates = names.intersection(CLAIM_DATE_COLUMNS)
    candidates = []
    if set(LIFE_COLUMNS).issubset(names):
        candidates.append(LIFE_UW)
    if set(KEY_FIELDS[LIFE_CLAIM]).issubset(names) and claim_dates:
        candidates.append(LIFE_CLAIM)
    if set(KEY_FIELDS[LIFE_SUBJECT]).issubset(names):
        candidates.append(LIFE_SUBJECT)
    if len(candidates) != 1:
        raise _invalid("無法唯一辨識申報檔種，請使用承保、給付或填報對象欄位。")
    kind = candidates[0]
    if kind == LIFE_CLAIM and len(claim_dates) != 1:
        raise _invalid("給付檔只能提供一個發生日期欄位名稱，避免日期別名衝突。")
    return kind, next(iter(claim_dates)) if kind == LIFE_CLAIM else None


def _parse_file(raw: bytes, filename: str) -> dict:
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not filename.lower().endswith(".csv"):
        raise ApiError(422, "UNSUPPORTED_FILE_TYPE", "申報組合目前只支援 UTF-8 CSV 檔。")
    if len(raw) > MAX_FILE_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "每個申報檔不可超過 2 MiB。")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise _invalid("申報檔須使用 UTF-8 編碼。", filename=filename) from error
    try:
        _check_quoting(text)
    except ApiError as error:
        raise _invalid(error.message, filename=filename) from error
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    file_id = str(uuid4())
    rows = []
    try:
        header = next((row for row in reader if any(value.strip() for value in row)), None)
        if header is None:
            raise _invalid("申報檔缺少標頭。", filename=filename)
        columns = [value.strip().removeprefix("\ufeff") for value in header]
        if any(not name for name in columns) or len(columns) != len(set(columns)):
            raise _invalid("申報檔標頭不可空白或重複。", filename=filename)
        dataset_type, date_column = _dataset_type(columns)
        for values in reader:
            if not any(value.strip() for value in values):
                continue
            if len(values) != len(columns):
                raise _invalid("申報檔每列欄位數須與標頭一致。", filename=filename,
                               line=reader.line_num)
            if len(rows) >= MAX_ROWS:
                raise _invalid("每個申報檔最多可包含 1,000 筆資料。", filename=filename)
            number = len(rows) + 1
            rows.append({
                "id": f"{file_id}:{number}", "row": number,
                "fileId": file_id, "datasetType": dataset_type,
                "values": dict(zip(columns, values, strict=True)),
            })
    except csv.Error as error:
        raise _invalid("申報 CSV 格式不完整，請檢查欄位及引號。", filename=filename,
                       line=reader.line_num) from error
    if dataset_type == LIFE_UW and not rows:
        raise _invalid("承保檔至少須包含一筆資料。", filename=filename)
    source = {
        "id": file_id, "datasetType": dataset_type, "filename": filename,
        "sourceSha256": hashlib.sha256(raw).hexdigest(), "columns": columns, "rows": rows,
        "prototype": True,
    }
    if date_column:
        source["eventDateColumn"] = date_column
    return source


def parse_filing(files: list[tuple[bytes, str]]) -> ParsedFiling:
    """Parse the entire batch before returning anything that storage can persist.

    Empty claim/subject CSVs with valid headers explicitly represent an empty
    file; this differs from an omitted file. At least one record is required in
    the complete bundle. Data values retain whitespace and leading zeroes.
    """
    if not 1 <= len(files) <= MAX_FILING_FILES:
        raise _invalid("每個版本須提供 1 至 3 個申報檔。")
    parsed = [_parse_file(raw, filename) for raw, filename in files]
    kinds = [source["datasetType"] for source in parsed]
    if len(kinds) != len(set(kinds)):
        raise _invalid("同一版本每種申報檔只能提供一份。")
    companies, years = set(), set()
    for source in parsed:
        for row in source["rows"]:
            values = row["values"]
            company = values["公司代號"].strip()
            if not company:
                raise _invalid("申報檔公司代號不可空白。", filename=source["filename"])
            companies.add(company)
            if "填報年度" in values:
                year = values["填報年度"].strip()
                if not re.fullmatch(r"[0-9]{4}", year):
                    raise _invalid("填報年度須為四位西元年份。", filename=source["filename"])
                years.add(int(year))
    if not companies:
        raise _invalid("申報組合至少須包含一筆資料。")
    if len(companies) != 1:
        raise _invalid("同一申報版本不可混用不同公司的資料。")
    if len(years) > 1:
        raise _invalid("同一申報版本不可混用不同填報年度。")
    return ParsedFiling(
        files=parsed, company_code=next(iter(companies)),
        filing_year=next(iter(years)) if years else None,
        raw_by_file={source["id"]: raw for source, (raw, _) in zip(parsed, files, strict=True)},
    )


def filing_issue_key(issue: dict, files: list[dict]) -> str:
    """Hash file kinds and business-key/cell pairs, never transient file ids."""
    sources = {source["id"]: source for source in files}
    group = any(
        cell["column"] in KEY_FIELDS[cell["datasetType"]]
        and cell["datasetType"] != LIFE_SUBJECT
        for cell in issue["cells"]
    )
    pairs = set()
    for cell in issue["cells"]:
        kind = cell["datasetType"]
        fields = POLICY_FIELDS if group and kind != LIFE_SUBJECT else KEY_FIELDS[kind]
        values = sources[cell["fileId"]]["rows"][cell["row"] - 1]["values"]
        pairs.add((kind, tuple(values[name] for name in fields), cell["column"]))
    canonical = json.dumps(
        [FILING_SCHEMA_PROFILE, issue["ruleId"], "group" if group else "record", sorted(pairs)],
        ensure_ascii=False, separators=(",", ":"),
    )
    return "filing-issue-v1:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cell(source: dict, row: dict, column: str) -> dict:
    return {
        "fileId": source["id"], "datasetType": source["datasetType"],
        "row": row["row"], "rowId": row["id"], "column": column,
        "value": row["values"][column],
    }


def _new_issue(source: dict, row: dict, rule: str, title: str, columns: tuple[str, ...],
               context: list[dict], facts: dict) -> dict:
    return {
        "id": f"{source['id']}:{row['row']}:{rule}", "ruleId": rule, "title": title,
        "localIssueId": f"{row['row']}:{rule}",
        "fileId": source["id"], "datasetType": source["datasetType"],
        "rows": [row["row"]], "rowIds": [row["id"]],
        "cells": [_cell(source, row, column) for column in columns],
        "contextRowIds": [reference["id"] for reference in context],
        "facts": facts, "repeated": False,
    }


def _policy(row: dict) -> tuple[str, ...]:
    return tuple(row["values"][column] for column in POLICY_FIELDS)


def _valid_date(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{8}", value):
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
        return True
    except ValueError:
        return False


def _claim_date_column(source: dict) -> str:
    """Recover the alias from saved headers if an older API omitted metadata."""
    return source.get("eventDateColumn") or next(
        name for name in CLAIM_DATE_COLUMNS if name in source["columns"]
    )


def evaluate_filing(parsed: ParsedFiling | list[dict], *, rules: RuleSet | None = None) -> dict:
    """Evaluate implemented rules and report every missing coverage family.

    Summary counts describe implemented rule/row checks plus explicit pending
    families, not a claim to enumerate the complete official rule inventory.
    Every prototype bundle has pending official coverage and cannot be confirmed.
    """
    files = parsed.files if isinstance(parsed, ParsedFiling) else parsed
    by_kind = {source["datasetType"]: source for source in files}
    issues, pending = [], []
    executed = []
    covered = 0
    failed = set()

    def unevaluated(code, reason, count=1):
        pending.append({"code": code, "reason": reason, "checks": count})

    uw = by_kind.get(LIFE_UW)
    claim = by_kind.get(LIFE_CLAIM)
    uw_groups, claim_groups = {}, {}
    for source, groups in ((uw, uw_groups), (claim, claim_groups)):
        if source:
            for row in source["rows"]:
                groups.setdefault(_policy(row), []).append(row)
    if uw:
        report = Report(
            report_id="filing-validation", version=1, columns=uw["columns"],
            rows=[row["values"] for row in uw["rows"]], numeric_columns=set(),
            meta={"險別": "個人壽險"},
        )
        rules = rules or life_field_rules()
        executed.extend(rule.rule_id for rule in rules.rules)
        covered += len(uw["rows"]) * len(rules.rules)
        for payload in issue_payloads(report.rows, rules.check(report), row_id=str):
            entry = payload.model_dump(exclude_none=True)
            entry["localIssueId"] = entry["id"]
            entry["id"] = f"{uw['id']}:{entry['id']}"
            entry.update(fileId=uw["id"], datasetType=LIFE_UW)
            entry["rowIds"] = [f"{uw['id']}:{number}" for number in entry["rows"]]
            entry["contextRowIds"] = [f"{uw['id']}:{number}" for number in entry["contextRowIds"]]
            for cell in entry["cells"]:
                cell.update(fileId=uw["id"], datasetType=LIFE_UW)
                cell["rowId"] = f"{uw['id']}:{cell['row']}"
            issues.append(entry)
            failed.update((entry["ruleId"], uw["id"], row) for row in entry["rows"])

    if claim:
        if claim["rows"]:
            executed.append("D1001")
        covered += len(claim["rows"])
        date_column = _claim_date_column(claim)
        for row in claim["rows"]:
            if not _valid_date(row["values"][date_column]):
                issues.append(_new_issue(
                    claim, row, "D1001", "給付發生日期不是合法的西元年月日。",
                    (date_column,), [], {date_column: row["values"][date_column]},
                ))
                failed.add(("D1001", claim["id"], row["row"]))

        for row in claim["rows"]:
            values = row["values"]
            if values["給付類別"] not in TERMINATION_CLAIMS:
                unevaluated("CLAIM_OTHER_EVENT_LINK", "其他給付類別的跨檔勾稽尚未實作。")
                continue
            if not uw or not _valid_date(values[date_column]):
                unevaluated("30307_LD013", "缺少承保檔或給付發生日期不合法，未執行跨檔匹配。")
                continue
            candidates = uw_groups.get(_policy(row), [])
            matching = [reference for reference in candidates if (
                reference["values"]["退保別"] in TERMINATED_EXITS
                and reference["values"]["退保日期"] == values[date_column]
            )]
            executed.append("30307_LD013")
            covered += 1
            if not matching:
                issues.append(_new_issue(
                    claim, row, "30307_LD013",
                    "給付資料找不到同一保單、同一事故日期的承保終止紀錄。",
                    ("保單編號", "保單編號序號", "給付類別", date_column), candidates,
                    {"保單編號": values["保單編號"], "事故日期": values[date_column],
                     "符合的承保筆數": 0},
                ))
                failed.add(("30307_LD013", claim["id"], row["row"]))

    if uw:
        for row in uw["rows"]:
            values = row["values"]
            if values["退保別"] not in TERMINATED_EXITS:
                continue
            if not claim or not _valid_date(values["退保日期"]):
                unevaluated("30301_LD012", "缺少給付檔或承保退保日期不合法，未執行跨檔匹配。")
                continue
            date_column = _claim_date_column(claim)
            candidates = claim_groups.get(_policy(row), [])
            matching = [reference for reference in candidates if (
                reference["values"][date_column] == values["退保日期"]
                and reference["values"]["給付類別"] in TERMINATION_CLAIMS
            )]
            executed.append("30301_LD012")
            covered += 1
            if not matching:
                issues.append(_new_issue(
                    uw, row, "30301_LD012", "承保終止紀錄找不到同一保單、同一事故日期的給付資料。",
                    ("退保別", "退保日期"), candidates,
                    {"保單編號": values["保單編號"], "退保日期": values["退保日期"],
                     "符合的給付筆數": 0},
                ))
                failed.add(("30301_LD012", uw["id"], row["row"]))

    for kind in (LIFE_UW, LIFE_CLAIM, LIFE_SUBJECT):
        if kind not in by_kind:
            unevaluated(f"MISSING_{kind}", f"未提供 {kind}，相關規則未評估。")
        else:
            unevaluated(f"REMAINING_{kind}_RULES", f"{kind} 尚有未實作的官方欄位與完整性規則。")
    for entry in issues:
        entry["issueKey"] = filing_issue_key(entry, files)
    skipped = sum(item["checks"] for item in pending)
    return {
        "issues": issues,
        "summary": {
            "totalChecks": covered + skipped, "passedChecks": covered - len(failed),
            "failedChecks": len(failed), "notEvaluatedChecks": skipped,
        },
        "evidence": {
            "status": "partial", "prototype": True,
            "countingScope": "implemented_rule_rows_and_pending_rule_families",
            "executedRuleIds": list(dict.fromkeys(executed)),
            "notEvaluated": pending, "sources": SOURCE_REFERENCES,
            "notice": "已執行的檢查不等於官方完整申報驗收；尚有未評估項目，不能確認申報。",
        },
    }
