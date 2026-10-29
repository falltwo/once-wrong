"""Filing bundles keep file boundaries, business history and partial coverage explicit."""

import csv
import hashlib
import io

import pytest

from once_wrong.filing import (
    FILING_RULE_VERSION,
    FILING_SCHEMA_PROFILE,
    KEY_FIELDS,
    LIFE_CLAIM,
    LIFE_SUBJECT,
    LIFE_UW,
    evaluate_filing,
    parse_filing,
)
from once_wrong.validation import LIFE_COLUMNS, MAX_FILE_BYTES, ApiError

CLAIM_COLUMNS = (*KEY_FIELDS[LIFE_CLAIM], "發生日期")
SUBJECT_COLUMNS = (*KEY_FIELDS[LIFE_SUBJECT], "商品名稱", "有效契約件數")


def source(columns, *rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def underwriting(policy="A00003", **changes):
    return {
        "公司代號": "01", "保單編號": policy, "保單編號序號": "0001", "異動序號": "00000",
        "加保別": "NEW", "加保日期": "20250101", "退保別": "DEA", "退保日期": "20250201",
        **changes,
    }


def claim(policy="A00003", **changes):
    return {
        "給付類別": "1", "公司代號": "01", "保單編號": policy,
        "保單編號序號": "0001", "發生日期": "20250201", **changes,
    }


def subject(**changes):
    return {
        "公司代號": "01", "填報年度": "2025", "險別": "1", "保險商品編號": "SYNTHETIC-01",
        "公司保單險種代號": "TEST", "商品名稱": " 合成資料商品 ", "有效契約件數": "00001",
        **changes,
    }


def bundle(uw=None, claims=None, subjects=None):
    return [
        (source(LIFE_COLUMNS, *(uw if uw is not None else [underwriting()])), "uw.csv"),
        (source(CLAIM_COLUMNS, *(claims if claims is not None else [claim()])), "claim.csv"),
        (source(SUBJECT_COLUMNS, *(subjects if subjects is not None else [subject()])),
         "subject.csv"),
    ]


def finding(result, rule):
    return next(entry for entry in result["issues"] if entry["ruleId"] == rule)


def test_three_files_keep_original_text_bytes_and_distinct_row_locations():
    originals = bundle()
    parsed = parse_filing(originals)
    assert parsed.schema_profile_id == FILING_SCHEMA_PROFILE
    assert parsed.rule_version == FILING_RULE_VERSION
    assert parsed.company_code == "01" and parsed.filing_year == 2025
    assert [entry["datasetType"] for entry in parsed.files] == [LIFE_UW, LIFE_CLAIM, LIFE_SUBJECT]
    assert len(set(row["id"] for row in parsed.rows)) == 3
    assert all(row["row"] == 1 for row in parsed.rows)
    assert parsed.files[2]["rows"][0]["values"]["商品名稱"] == " 合成資料商品 "
    assert parsed.files[2]["rows"][0]["values"]["有效契約件數"] == "00001"
    assert all(isinstance(value, str) for row in parsed.rows for value in row["values"].values())
    for entry, (raw, filename) in zip(parsed.files, originals, strict=True):
        assert entry["filename"] == filename
        assert entry["sourceSha256"] == hashlib.sha256(raw).hexdigest()
        assert parsed.raw_by_file[entry["id"]] == raw
        assert entry["rows"][0]["id"] == f"{entry['id']}:1"
        assert entry["prototype"] is True
    assert set(parsed.columns).issuperset(LIFE_COLUMNS)


def test_matching_files_do_not_fabricate_errors_or_claim_full_official_coverage():
    result = evaluate_filing(parse_filing(bundle()))
    assert result["issues"] == []
    assert result["evidence"]["status"] == "partial"
    assert result["evidence"]["prototype"] is True
    assert {"30301_LD012", "30307_LD013", "D1001"}.issubset(
        result["evidence"]["executedRuleIds"]
    )
    summary = result["summary"]
    assert summary == {
        "totalChecks": 17, "passedChecks": 14, "failedChecks": 0, "notEvaluatedChecks": 3
    }
    assert all(item["code"].startswith("REMAINING_")
               for item in result["evidence"]["notEvaluated"])


@pytest.mark.parametrize("date_column", ["發生日期", "事故日期", "死亡完全失能日期"])
def test_claim_date_names_are_explicit_aliases_without_changing_raw_headers(date_column):
    dates = {date_column: "20250201"}
    values = {key: value for key, value in claim().items() if key != "發生日期"}
    parsed = parse_filing([
        (source(LIFE_COLUMNS, underwriting()), "uw.csv"),
        (source((*KEY_FIELDS[LIFE_CLAIM], date_column), {**values, **dates}), "claim.csv"),
    ])
    assert parsed.files[1]["eventDateColumn"] == date_column
    assert date_column in parsed.files[1]["columns"]
    assert evaluate_filing(parsed)["issues"] == []


def test_mismatching_event_date_references_the_other_file_without_row_id_collision():
    parsed = parse_filing(bundle(claims=[claim(**{"發生日期": "20250202"})]))
    result = evaluate_filing(parsed)
    forward = finding(result, "30307_LD013")
    reverse = finding(result, "30301_LD012")
    uw, claims = parsed.files[:2]
    assert forward["fileId"] == claims["id"]
    assert reverse["fileId"] == uw["id"]
    assert forward["contextRowIds"] == [uw["rows"][0]["id"]]
    assert reverse["contextRowIds"] == [claims["rows"][0]["id"]]
    assert forward["rowIds"] != forward["contextRowIds"]
    assert forward["rows"] == reverse["rows"] == [1]
    assert all(cell["fileId"] == claims["id"] and cell["datasetType"] == LIFE_CLAIM
               for cell in forward["cells"])
    assert result["summary"]["failedChecks"] == 2


def test_underwriting_issues_expose_local_id_for_ai_and_qualified_file_coordinates():
    parsed = parse_filing(bundle(uw=[underwriting(**{"加保日期": "20250230"})]))
    issue = finding(evaluate_filing(parsed), "L1402")
    file_id = parsed.files[0]["id"]
    assert issue["localIssueId"] == "1:L1402"
    assert issue["id"] == f"{file_id}:1:L1402"
    assert issue["rowIds"] == [f"{file_id}:1"]
    assert issue["cells"][0]["rowId"] == f"{file_id}:1"
    assert issue["cells"][0]["column"] == "加保日期"


def test_business_history_key_ignores_file_ids_row_order_and_invalid_key_value_changes():
    bad = underwriting(**{"加保日期": "20250230"})
    other = underwriting("A00005", **{"退保別": "XED", "退保日期": "00000000"})
    first = parse_filing(bundle(uw=[other, bad]))
    second = parse_filing(bundle(uw=[{**bad, "加保日期": "20250231"}, other]))
    before, after = (finding(evaluate_filing(parsed), "L1402") for parsed in (first, second))
    assert before["fileId"] != after["fileId"]
    assert before["rows"] == [2] and after["rows"] == [1]
    assert before["issueKey"] == after["issueKey"]
    third = parse_filing(bundle(uw=[underwriting("A00005", **{"加保日期": "20250231"})]))
    assert finding(evaluate_filing(third), "L1402")["issueKey"] != before["issueKey"]


def test_invalid_claim_date_fails_its_date_rule_and_skips_unreliable_cross_file_match():
    result = evaluate_filing(parse_filing(bundle(claims=[claim(**{"發生日期": "20250230"})])))
    assert finding(result, "D1001")["cells"][0]["column"] == "發生日期"
    assert "30307_LD013" not in result["evidence"]["executedRuleIds"]
    assert any(item["code"] == "30307_LD013" for item in result["evidence"]["notEvaluated"])


def test_empty_claim_file_is_explicit_and_differs_from_missing_claim_file():
    no_exit = underwriting(**{"退保別": "XED", "退保日期": "00000000"})
    parsed = parse_filing(bundle(uw=[no_exit], claims=[]))
    assert parsed.files[1]["rows"] == []
    result = evaluate_filing(parsed)
    assert result["issues"] == []
    assert "MISSING_LIFE_CLAIM" not in {
        item["code"] for item in result["evidence"]["notEvaluated"]
    }
    missing = evaluate_filing(parse_filing(bundle(uw=[no_exit])[:1]))
    assert "MISSING_LIFE_CLAIM" in {
        item["code"] for item in missing["evidence"]["notEvaluated"]
    }
    assert missing["summary"]["notEvaluatedChecks"] > 0


def test_claim_without_underwriting_is_unevaluated_instead_of_a_false_missing_match():
    parsed = parse_filing([(source(CLAIM_COLUMNS, claim()), "claim.csv")])
    result = evaluate_filing(parsed.files)
    assert result["issues"] == []
    assert any(item["code"] == "30307_LD013" for item in result["evidence"]["notEvaluated"])
    assert result["summary"]["notEvaluatedChecks"] > 0


def test_saved_file_headers_are_sufficient_when_optional_date_metadata_is_absent():
    parsed = parse_filing(bundle())
    parsed.files[1].pop("eventDateColumn")
    assert evaluate_filing(parsed.files)["issues"] == []


def test_nontermination_claim_type_is_not_checked_using_termination_rules():
    parsed = parse_filing(bundle(claims=[claim(**{"給付類別": "4"})]))
    result = evaluate_filing(parsed)
    assert not any(item["ruleId"] == "30307_LD013" for item in result["issues"])
    assert any(item["code"] == "CLAIM_OTHER_EVENT_LINK"
               for item in result["evidence"]["notEvaluated"])


@pytest.mark.parametrize("files", [
    [],
    bundle() + [(source(CLAIM_COLUMNS, claim()), "duplicate.csv")],
    [(source(LIFE_COLUMNS, underwriting()), "uw.csv"),
     (source(LIFE_COLUMNS, underwriting("A00005")), "uw2.csv")],
    [(source(LIFE_COLUMNS, underwriting()), "uw.xlsx")],
    [(b"\xff", "bad.csv")],
    [(b'"unterminated\n', "bad.csv")],
    [(b"x,x\n1,2\n", "bad.csv")],
    [(source(CLAIM_COLUMNS), "empty.csv")],
    [(source(LIFE_COLUMNS), "empty-uw.csv")],
])
def test_bad_batches_are_rejected_before_storage(files):
    with pytest.raises(ApiError) as caught:
        parse_filing(files)
    assert caught.value.status in {413, 422}


def test_mixed_companies_within_or_across_files_are_rejected():
    with pytest.raises(ApiError, match="不同公司"):
        parse_filing(bundle(claims=[claim(**{"公司代號": "02"})]))
    with pytest.raises(ApiError, match="不同公司"):
        parse_filing(bundle(uw=[underwriting(), underwriting("A00005", **{"公司代號": "02"})]))


def test_years_must_be_well_formed_and_agree_across_all_rows():
    with pytest.raises(ApiError, match="不同填報年度"):
        parse_filing(bundle(subjects=[subject(), subject(**{"填報年度": "2024"})]))
    with pytest.raises(ApiError, match="四位西元年份"):
        parse_filing(bundle(subjects=[subject(**{"填報年度": "２０２５"})]))


def test_ambiguous_dataset_or_date_alias_headers_are_rejected():
    combined = {**underwriting(), **claim()}
    with pytest.raises(ApiError, match="唯一辨識"):
        parse_filing([(source(tuple(combined), combined), "mixed.csv")])
    with pytest.raises(ApiError, match="別名衝突"):
        parse_filing([(
            source((*CLAIM_COLUMNS, "事故日期"), {**claim(), "事故日期": "20250201"}), "claim.csv"
        )])


def test_row_and_byte_limits_apply_to_each_file_before_persistence():
    with pytest.raises(ApiError, match="1,000"):
        parse_filing([(source(LIFE_COLUMNS, *[underwriting()] * 1001), "large.csv")])
    with pytest.raises(ApiError) as caught:
        parse_filing([(b"x" * (MAX_FILE_BYTES + 1), "large.csv")])
    assert caught.value.status == 413


def test_extra_official_fields_are_retained_without_inventing_full_rule_coverage():
    expanded = {**underwriting(), "保險商品編號": "SYNTHETIC-01", "保留欄位": "   "}
    parsed = parse_filing([(source(tuple(expanded), expanded), "expanded-uw.csv")])
    assert parsed.files[0]["rows"][0]["values"]["保留欄位"] == "   "
    assert parsed.files[0]["prototype"] is True
    summary = evaluate_filing(parsed)["summary"]
    assert summary["notEvaluatedChecks"] > 0
    assert summary["totalChecks"] == sum(
        summary[key] for key in ("passedChecks", "failedChecks", "notEvaluatedChecks")
    )
