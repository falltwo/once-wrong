"""Profile boundaries preserve source text and expose all affected life cells."""

import csv
import io
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from once_wrong.models import Version
from once_wrong.validation import (
    LIFE_COLUMNS,
    LIFE_RULE_VERSION,
    LIFE_SCHEMA_PROFILE,
    RULE_VERSION,
    SCHEMA_PROFILE,
    ApiError,
    parse_csv,
    parse_profile_csv,
    report_for_version,
    rules_for_profile,
    summary,
    validate_profile,
)

EXAMPLE_CSV = Path(__file__).resolve().parents[2] / "examples" / "mock_life_policies_2025.csv"


def life_csv(columns=LIFE_COLUMNS, values=None) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(columns)
    row = dict(zip(LIFE_COLUMNS, [
        "01", "A00001", "0001", "00000", "NEW", "20250115", "XED", "00000000"
    ], strict=True))
    row.update(values or {})
    writer.writerow([row.get(column, "extra") for column in columns])
    return output.getvalue().encode("utf-8")


def version_payload(parsed):
    version = {
        "id": "test-version",
        "number": 1,
        "filename": "source.csv",
        "createdAt": "2026-10-29T00:00:00Z",
        "validationStatus": "completed",
        "validationRunId": "run-1",
        "sourceSha256": "0" * 64,
        "schemaProfileId": parsed.schema_profile_id,
        "ruleVersion": parsed.rule_version,
        "rows": parsed.rows,
        "issues": validate_profile(parsed.rows, parsed.schema_profile_id),
    }
    version["summary"] = summary(parsed.rows, version["issues"], parsed.schema_profile_id)
    if parsed.schema_profile_id == LIFE_SCHEMA_PROFILE:
        version["columns"] = parsed.columns
    return version


def test_life_text_values_and_source_column_order_survive_response_model():
    columns = tuple(reversed(LIFE_COLUMNS))
    parsed = parse_profile_csv(life_csv(columns, {"公司代號": "01", "保單編號": " A00001 "}))
    assert parsed.schema_profile_id == LIFE_SCHEMA_PROFILE
    assert parsed.rule_version == LIFE_RULE_VERSION
    assert parsed.columns == list(columns)
    assert parsed.rows[0]["id"] == "1" and parsed.rows[0]["row"] == 1
    assert parsed.rows[0]["values"]["公司代號"] == "01"
    assert parsed.rows[0]["values"]["退保日期"] == "00000000"
    assert parsed.rows[0]["values"]["保單編號"] == " A00001 "
    version = version_payload(parsed)
    assert TypeAdapter(Version).validate_python(version).model_dump() == version
    report = report_for_version(version, "life-report")
    assert report.numeric_columns == set()
    assert report.meta == {"險別": "個人壽險"}
    assert report.columns == list(columns)
    assert report.rows == [parsed.rows[0]["values"]]


@pytest.mark.parametrize("columns", [LIFE_COLUMNS[:-1], (*LIFE_COLUMNS, "其他")])
def test_life_profile_requires_exactly_the_eight_headers(columns):
    with pytest.raises(ApiError) as caught:
        parse_profile_csv(life_csv(columns))
    assert caught.value.status == 422
    assert caught.value.code == "INVALID_CSV"


def test_life_rule_issues_include_reference_rows_and_stable_repeated_ids():
    parsed = parse_profile_csv(EXAMPLE_CSV.read_bytes())
    first = validate_profile(parsed.rows, LIFE_SCHEMA_PROFILE)
    second = validate_profile(parsed.rows, LIFE_SCHEMA_PROFILE, first)
    assert first and all(not issue["repeated"] for issue in first)
    assert [issue["id"] for issue in second] == [issue["id"] for issue in first]
    assert all(issue["repeated"] for issue in second)
    l0302 = next(issue for issue in first if issue["id"] == "2:L0302")
    assert l0302["rows"] == [2, 3, 4]
    assert l0302["rowIds"] == ["2", "3", "4"]
    assert {cell["column"] for cell in l0302["cells"]} == {"異動序號"}
    l0303 = next(issue for issue in first if issue["id"] == "6:L0303")
    assert l0303["contextRowIds"] == ["7"]
    assert l0303["facts"] == {"退保別": "DEA"}
    assert len(rules_for_profile(LIFE_SCHEMA_PROFILE).rules) == 11
    counts = summary(parsed.rows, first, LIFE_SCHEMA_PROFILE)
    assert counts["totalChecks"] == len(parsed.rows) * 11
    failed = {(issue["ruleId"], row) for issue in first for row in issue["rows"]}
    assert counts["failedChecks"] == len(failed)
    assert counts["passedChecks"] + counts["failedChecks"] == counts["totalChecks"]


def test_demo_payload_keeps_original_shape_after_generic_profile_support():
    source = b"id,product,previous,opening\nA,P,10,9\nB,,1,1\n"
    parsed = parse_profile_csv(source)
    assert parsed.schema_profile_id == SCHEMA_PROFILE
    assert parsed.rule_version == RULE_VERSION
    assert parsed.rows == parse_csv(source)
    assert parsed.rows[0] == {"id": "A", "product": "P", "previous": 10, "opening": 9}
    version = version_payload(parsed)
    serialized = TypeAdapter(Version).validate_python(version).model_dump(exclude_none=True)
    assert "columns" not in serialized
    assert serialized == version
    assert version["summary"] == {
        "totalChecks": 4, "passedChecks": 2, "failedChecks": 2, "notEvaluatedChecks": 0
    }
    report = report_for_version(version, "demo-report")
    assert report.numeric_columns == {"previous", "opening"}
    assert report.meta == {}


def test_profile_switch_does_not_assume_previous_issue_has_demo_row_id():
    life = parse_profile_csv(EXAMPLE_CSV.read_bytes())
    previous = validate_profile(life.rows, LIFE_SCHEMA_PROFILE)
    demo = parse_profile_csv(b"id,product,previous,opening\nA,P,1,2\n")
    issues = validate_profile(demo.rows, SCHEMA_PROFILE, previous)
    assert issues[0]["id"] == "A:R-07" and issues[0]["repeated"] is False
