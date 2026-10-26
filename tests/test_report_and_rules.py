from conftest import EXAMPLE_CSV

from once_wrong.report import CellRef, Report
from once_wrong.rules.examples import life_example_rules

LIFE_CSV = EXAMPLE_CSV.parent / "mock_life_policies_2025.csv"


def test_codes_with_leading_zeros_stay_text():
    report = Report.from_csv(LIFE_CSV)
    assert report.get(CellRef(1, "公司代號")) == "01"
    assert report.get(CellRef(1, "異動序號")) == "00000"
    assert "異動序號" not in report.numeric_columns


def test_life_rules_find_seeded_errors():
    report = Report.from_csv(LIFE_CSV)
    found = sorted((v.rule_id, tuple(v.rows)) for v in life_example_rules().check(report))
    assert found == [("L0302", (2, 3, 4)), ("L0302", (5,)), ("L0303", (6,))]


def test_csv_detects_numeric_columns(report):
    assert report.numeric_columns == {"上月期末", "本月期初"}
    assert report.get(CellRef(3, "上月期末")) == 12_480_000
    assert report.get(CellRef(4, "險種")) is None


def test_with_changes_leaves_original_untouched(report):
    changed = report.with_changes({CellRef(3, "本月期初"): 12_480_000})
    assert changed.get(CellRef(3, "本月期初")) == 12_480_000
    assert report.get(CellRef(3, "本月期初")) == 12_005_000


def test_example_rules_find_seeded_errors(report, rules):
    found = sorted((v.rule_id, v.rows[0]) for v in rules.check(report))
    assert found == [("R-01", 4), ("R-07", 3), ("R-07", 5)]


def test_opening_rule_computes_facts(report, rules):
    v = next(v for v in rules.check(report) if v.rule_id == "R-07" and v.rows == [3])
    assert v.facts == {"上月期末": 12_480_000, "本月期初": 12_005_000, "差額": 475_000}
