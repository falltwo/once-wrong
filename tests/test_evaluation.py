import random

import pytest

from once_wrong.ai_review.models import ExplanationSource, FixSuggestion, ReviewItem
from once_wrong.evaluation.cases import MUTATIONS, clean_life_report, make_cases
from once_wrong.evaluation.run import score_item
from once_wrong.report import CellRef
from once_wrong.rules.life import life_field_rules


@pytest.mark.parametrize("seed", range(50))
def test_clean_report_passes_every_rule(seed):
    assert life_field_rules().check(clean_life_report(random.Random(seed))) == []


def test_every_mutation_is_caught_and_has_an_answer():
    rules = life_field_rules()
    cases = make_cases(len(MUTATIONS) * 5, seed=3)
    assert {c.mutation for c in cases} == set(MUTATIONS)
    for case in cases:
        assert rules.check(case.report), case.description
        assert all(case.report.get(ref) != original for ref, original in case.changed.items())


def test_same_seed_gives_same_cases():
    a, b = make_cases(13, seed=5), make_cases(13, seed=5)
    assert [c.report.rows for c in a] == [c.report.rows for c in b]


def _item(case, violation, changes=None, rejected=()):
    return ReviewItem(
        violation=violation,
        title="",
        explanation="",
        source=ExplanationSource.AI,
        suggestion=FixSuggestion(changes, "") if changes else None,
        rejected=list(rejected),
    )


def _case(mutation):
    return next(c for c in make_cases(len(MUTATIONS), seed=1) if c.mutation == mutation)


def test_fix_back_to_original_counts_as_restored():
    case = _case("new_date_missing")
    [v] = life_field_rules().check(case.report)
    [(ref, original)] = case.changed.items()

    score = score_item(case, _item(case, v, {ref: original}))
    assert score.restored and not score.other_fix


def test_other_passing_fix_is_not_restored():
    case = _case("new_date_missing")
    [v] = life_field_rules().check(case.report)
    [ref] = case.changed

    score = score_item(case, _item(case, v, {ref: "20250101"}))
    assert score.other_fix and not score.restored


def test_swap_across_rows_is_not_restorable_for_single_row_error():
    case = _case("new_not_first")
    v = next(v for v in life_field_rules().check(case.report) if v.rule_id == "L1303")

    score = score_item(case, _item(case, v))
    assert score.answer == "other_rows" and score.abstained


def test_missing_date_with_no_clue_is_unknowable():
    case = _case("new_date_missing")
    [v] = life_field_rules().check(case.report)
    assert score_item(case, _item(case, v)).answer == "unknowable"


def test_chain_break_is_inferable_from_previous_row():
    case = _case("chain_date")
    [v] = life_field_rules().check(case.report)
    assert score_item(case, _item(case, v)).answer == "inferable"


def test_date_shown_via_other_error_on_same_row_is_inferable():
    # 漏填退保日、後面還有一筆：L1504 本身看不到下一筆，但同一列的 L1305 錯誤會帶出下一筆的加保日
    case = next(
        c for c in make_cases(len(MUTATIONS) * 5, seed=1)
        if c.mutation == "ended_without_date" and len(life_field_rules().check(c.report)) == 2
    )
    violations = life_field_rules().check(case.report)
    v = next(v for v in violations if v.rule_id == "L1504")
    assert score_item(case, _item(case, v)).answer == "unknowable"
    assert score_item(case, _item(case, v), violations).answer == "inferable"
