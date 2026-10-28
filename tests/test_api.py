import json
from decimal import Decimal

from conftest import FakeLLM

from once_wrong_ai.ai_review import AIReviewer, LLMError
from once_wrong_ai.ai_review.api import (
    SuggestionResponse,
    issue_payloads,
    json_value,
    suggestion_payload,
)
from once_wrong_ai.ai_review.models import AIChange, AIExplanation, AIFixCandidate
from once_wrong_ai.kb.models import Passage, PassageKind

# frontend/src/types/index.ts（codex/frontend-prototype）的 Suggestion 欄位
FRONTEND_SUGGESTION_FIELDS = {
    "title", "explanation", "suggestion", "rejectedSuggestions", "citations",
    "blockedNumbers", "model", "verification", "source",
}
FRONTEND_CHANGE_FIELDS = {"rowId", "row", "column", "value"}
FRONTEND_CITATION_FIELDS = {"id", "source", "section", "page"}


def _reply(*candidates):
    return AIExplanation(
        title="異動序號要從 00001 依序編",
        explanation="保單 A00002 共 3 筆，第 3 列應為 00002。",
        candidates=[
            AIFixCandidate(changes=[AIChange(row=r, column=c, new_value=v) for r, c, v in cs], reason="依序編號")
            for cs in candidates
        ],
        citations=["K1"],
    )


class _OneRuleKB:
    """只回一段假的手冊段落，讓引用有東西可轉。"""

    passage = Passage(
        id="LIFE-RULE-0068", product="個人壽險", manual="個人壽險填報說明手冊範例與檢核規則 2025",
        section=["參、欄位檢核", "一、承保資料欄位檢核"], kind=PassageKind.RULE, text="L0302 異動序號", page=46,
    )

    def for_violation(self, *args, **kwargs):
        return [self.passage]


def _review(life_report, life_rules, replies):
    reviewer = AIReviewer(FakeLLM(replies), life_rules, knowledge=_OneRuleKB())
    return reviewer.review(life_report)


def test_suggestion_matches_frontend_type(life_report, life_rules):
    items = _review(life_report, life_rules, [
        _reply([(3, "異動序號", "00001")], [(3, "異動序號", "00002")]),  # 第一個重驗不過，第二個過
        _reply(),
        _reply(),
    ])
    payload = json.loads(suggestion_payload(items[0], "gemini-test").model_dump_json())

    assert set(payload) == FRONTEND_SUGGESTION_FIELDS
    assert payload["source"] == "ai" and payload["verification"] == "passed"
    assert payload["suggestion"]["verification"] == "passed"
    [change] = payload["suggestion"]["changes"]
    assert set(change) == FRONTEND_CHANGE_FIELDS
    assert change == {"rowId": "3", "row": 3, "column": "異動序號", "value": "00002"}
    assert len(payload["rejectedSuggestions"]) == 1
    [citation] = payload["citations"]
    assert set(citation) == FRONTEND_CITATION_FIELDS
    assert citation["page"] == 46 and citation["section"][0] == "參、欄位檢核"


def test_no_verified_fix_is_unavailable(life_report, life_rules):
    items = _review(life_report, life_rules, [LLMError("timeout"), _reply(), _reply()])
    payload = suggestion_payload(items[0], "gemini-test")

    assert payload.source == "fallback_llm_error"
    assert payload.suggestion is None and payload.verification == "unavailable"
    assert payload.title == "L0302 未通過"


def test_issue_payloads_cover_cells_and_reference_rows(life_report, life_rules):
    issues = issue_payloads(life_report.rows, life_rules.check(life_report))

    assert [i.id for i in issues] == ["2:L0302", "5:L0302", "6:L0303"]
    l0303 = issues[2]
    assert l0303.rowIds == ["6"] and l0303.contextRowIds == ["7"]
    assert {(c.column, c.value) for c in l0303.cells} == {("異動序號", "00001"), ("退保別", "DEA")}
    assert l0303.facts == {"退保別": "DEA"}


def test_custom_row_id_is_used_everywhere(life_report, life_rules):
    row_id = lambda r: f"{life_report.row(r)['保單編號']}/{r}"  # noqa: E731
    [first, *_] = issue_payloads(life_report.rows, life_rules.check(life_report), row_id)
    assert first.id == "A00002/2:L0302"
    assert {c.rowId for c in first.cells} == {"A00002/2", "A00002/3", "A00002/4"}


def test_json_values_keep_precision():
    assert json_value(12_480_000) == 12_480_000
    assert json_value(2**60) == str(2**60)
    assert json_value(Decimal("3.10")) == "3.10"
    assert json_value(None) is None


def test_response_model_is_valid_json_schema():
    schema = SuggestionResponse.model_json_schema()
    assert set(schema["properties"]) == FRONTEND_SUGGESTION_FIELDS


def test_find_violation_by_issue_id(life_report, life_rules):
    from once_wrong_ai.ai_review.api import find_violation

    violations = life_rules.check(life_report)
    assert find_violation(violations, "6:L0303").rule_id == "L0303"
    assert find_violation(violations, "6:L0302") is None


def test_demo_rules_on_backend_columns_give_backend_issue_ids():
    """後端 demo_csv_v1 的欄位（id, product, previous, opening）可以直接用示範規則，issueId 跟後端一致。"""
    from once_wrong_ai.ai_review.api import issue_ids
    from once_wrong_ai.report import Report
    from once_wrong_ai.rules import RuleSet
    from once_wrong_ai.rules.examples import OpeningEqualsClosing, RequiredField

    columns = ["id", "product", "previous", "opening"]
    rows = [
        {"id": "ML-01", "product": "WL", "previous": 100, "opening": 100},
        {"id": "ML-05", "product": "WL", "previous": 12_480_000, "opening": 12_005_000},
        {"id": "CR-02", "product": "", "previous": 5, "opening": 5},
    ]
    report = Report("reserve-202609", 1, columns, rows, numeric_columns={"previous", "opening"})
    rules = RuleSet([
        RequiredField(rule_id="R-01", column="product"),
        OpeningEqualsClosing(rule_id="R-07", closing_column="previous", opening_column="opening"),
    ])
    violations = rules.check(report)
    # 後端 validation.py 的 id 是 f"{row['id']}:R-07"、f"{row['id']}:R-01"
    assert sorted(issue_ids(violations, lambda r: rows[r - 1]["id"])) == ["CR-02:R-01", "ML-05:R-07"]
