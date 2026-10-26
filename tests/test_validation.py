from once_wrong.ai_review.models import AIChange, AIFixCandidate
from once_wrong.ai_review.validation import validate_candidate
from once_wrong.report import CellRef


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
    # 把險種清空不會修好 R-07，但先確認「修好 A、弄壞 B」也會被擋
    outcome = _check(
        report, rules, "R-07", 3,
        (3, "本月期初", "12,480,000"),
        (3, "險種", ""),
    )
    assert not outcome.passed
    assert "新的錯誤" in outcome.why and "R-01" in outcome.why


def test_no_op_fix_is_rejected(report, rules):
    outcome = _check(report, rules, "R-07", 3, (3, "本月期初", "12,005,000"))
    assert not outcome.passed
