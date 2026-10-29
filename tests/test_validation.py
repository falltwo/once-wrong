from once_wrong_ai.ai_review.models import AIChange, AIFixCandidate
from once_wrong_ai.ai_review.validation import validate_candidate
from once_wrong_ai.report import CellRef
from once_wrong_ai.rules import RuleSet, Violation
from once_wrong_ai.rules.examples import RequiredField


def _check(report, rules, rule_id, row, *changes):
    before = rules.check(report)
    v = next(v for v in before if v.rule_id == rule_id and v.rows == [row])
    candidate = AIFixCandidate(changes=[AIChange(row=r, column=c, new_value=val) for r, c, val in changes], reason="")
    return validate_candidate(report, v, candidate, rules, before)


def test_correct_fix_passes(report, rules):
    outcome = _check(report, rules, "R-07", 3, (3, "本月期初", "12,480,000"))
    assert outcome.passed
    assert outcome.suggestion.changes == {CellRef(3, "本月期初"): 12_480_000}


def test_wrong_value_is_rejected(report, rules):
    outcome = _check(report, rules, "R-07", 3, (3, "本月期初", "12,408,000"))
    assert not outcome.passed
    assert "仍未通過" in outcome.why


def test_editing_other_rows_is_rejected(report, rules):
    outcome = _check(report, rules, "R-07", 3, (1, "本月期初", "1"))
    assert not outcome.passed
    assert "出錯列以外" in outcome.why


def test_non_number_in_numeric_column_is_rejected(report, rules):
    outcome = _check(report, rules, "R-07", 3, (3, "本月期初", "約一千兩百萬"))
    assert not outcome.passed


def test_unknown_column_is_rejected(report, rules):
    outcome = _check(report, rules, "R-07", 3, (3, "期初", "12,480,000"))
    assert not outcome.passed
    assert "不存在" in outcome.why


def test_fix_that_creates_new_error_is_rejected(report, rules):
    # 本月期初是 R-07 的出錯格子；清空雖讓比對跳過，卻會新增必填錯誤。
    rules = RuleSet([*rules.rules, RequiredField(rule_id="R-OPEN", column="本月期初")])
    outcome = _check(
        report, rules, "R-07", 3,
        (3, "本月期初", ""),
    )
    assert not outcome.passed
    assert "新的錯誤" in outcome.why and "R-OPEN" in outcome.why


def test_editing_other_column_on_error_row_is_rejected(report, rules):
    outcome = _check(
        report, rules, "R-07", 3,
        (3, "本月期初", "12,480,000"),
        (3, "險種", "WL-01"),
    )
    assert not outcome.passed
    assert outcome.suggestion is None
    assert "出錯格子以外" in outcome.why and "險種" in outcome.why
    assert report.row(3)["險種"] == "ML-05"


def test_violation_without_explicit_cells_requires_manual_review(report, rules):
    violation = Violation(rule_id="GROUP", message="整組資料需人工核對", cells=())
    candidate = AIFixCandidate(
        changes=[AIChange(row=3, column="本月期初", new_value="12,480,000")], reason=""
    )
    outcome = validate_candidate(report, violation, candidate, rules, rules.check(report))
    assert not outcome.passed
    assert outcome.suggestion is None
    assert "未指定出錯格子" in outcome.why


def test_multiple_explicit_cells_across_rows_can_be_fixed(life_report, life_rules):
    life_report.rows[1]["異動序號"] = "00003"
    before = life_rules.check(life_report)
    violation = next(v for v in before if v.rule_id == "L0302" and v.rows == [2, 3, 4])
    candidate = AIFixCandidate(
        changes=[
            AIChange(row=2, column="異動序號", new_value="00001"),
            AIChange(row=3, column="異動序號", new_value="00002"),
        ],
        reason="依序編號",
    )
    outcome = validate_candidate(life_report, violation, candidate, life_rules, before)
    assert outcome.passed
    assert outcome.suggestion.changes == {
        CellRef(2, "異動序號"): "00001", CellRef(3, "異動序號"): "00002"
    }
    assert life_report.row(2)["異動序號"] == "00003"


def test_no_op_fix_is_rejected(report, rules):
    outcome = _check(report, rules, "R-07", 3, (3, "本月期初", "12,005,000"))
    assert not outcome.passed


def test_editing_reference_row_is_rejected(life_report, life_rules):
    before = life_rules.check(life_report)
    [v] = [v for v in before if v.rule_id == "L0303"]
    candidate = AIFixCandidate(changes=[AIChange(row=7, column="異動序號", new_value="00001")], reason="")
    outcome = validate_candidate(life_report, v, candidate, life_rules, before)
    assert not outcome.passed
    assert "出錯列以外" in outcome.why
