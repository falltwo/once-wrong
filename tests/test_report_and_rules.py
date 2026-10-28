import dataclasses

import pytest

from conftest import LIFE_CSV

from once_wrong_ai.report import CellRef, Report
from once_wrong_ai.rules.examples import life_example_rules
from once_wrong_ai.rules.life import life_field_rules


def test_codes_with_leading_zeros_stay_text():
    report = Report.from_csv(LIFE_CSV)
    assert report.get(CellRef(1, "公司代號")) == "01"
    assert report.get(CellRef(1, "異動序號")) == "00000"
    assert "異動序號" not in report.numeric_columns


def test_life_rules_find_seeded_errors():
    report = Report.from_csv(LIFE_CSV)
    found = sorted((v.rule_id, tuple(v.rows)) for v in life_example_rules().check(report))
    assert found == [("L0302", (2, 3, 4)), ("L0302", (5,)), ("L0303", (6,))]


def test_l0303_brings_other_rows_of_same_policy():
    report = Report.from_csv(LIFE_CSV)
    by_rule = {(v.rule_id, tuple(v.rows)): v for v in life_example_rules().check(report)}
    # 保單 A00004 在第 6、7 列；出錯的是第 6 列，第 7 列只供參考
    assert by_rule["L0303", (6,)].reference_rows == [7]
    # L0302 的格子已涵蓋整張保單，不需要另外的參考列
    assert by_rule["L0302", (2, 3, 4)].reference_rows == []


def test_context_rows_do_not_change_violation_key():
    report = Report.from_csv(LIFE_CSV)
    [v] = [v for v in life_example_rules().check(report) if v.rule_id == "L0303"]
    assert v == dataclasses.replace(v, context_rows=())
    assert v.key == dataclasses.replace(v, context_rows=()).key


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


def _life(*rows):
    """用 (保單編號, 異動序號, 加保別, 加保日期, 退保別, 退保日期) 組一份小報表。"""
    columns = ["公司代號", "保單編號", "保單編號序號", "異動序號", "加保別", "加保日期", "退保別", "退保日期"]
    return Report(
        report_id="t",
        version=1,
        columns=columns,
        rows=[dict(zip(columns, ("01", p, "00001", *rest))) for p, *rest in rows],
    )


def _found(report):
    return sorted((v.rule_id, tuple(v.rows)) for v in life_field_rules().check(report))


def test_life_field_rules_accept_valid_policies():
    report = _life(
        ("P1", "00000", "NEW", "20250115", "XED", "00000000"),
        ("P2", "00001", "NEW", "20250301", "INN", "20250401"),
        ("P2", "00002", "INN", "20250401", "DEA", "20250920"),
    )
    assert _found(report) == []


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        # L1303：NEW 卻不是第一筆
        ([("P", "00001", "INN", "20250201", "NEW", "20250301"), ("P", "00002", "NEW", "20250301", "XED", "00000000")],
         [("L1303", (2,))]),
        # L1304：NEW 沒有加保日期
        ([("P", "00000", "NEW", "00000000", "XED", "00000000")], [("L1304", (1,))]),
        # L1305：加保日期沒接上一筆的退保日期
        ([("P", "00001", "NEW", "20250101", "INN", "20250401"), ("P", "00002", "INN", "20250402", "XED", "00000000")],
         [("L1305", (1, 2))]),
        # L1502 + L1304：加保別、退保別都是 XED
        ([("P", "00000", "XED", "20250101", "XED", "00000000")], [("L1304", (1,)), ("L1502", (1,))]),
        # L1504：終止卻沒有退保日期
        ([("P", "00000", "NEW", "20250101", "DEA", "00000000")], [("L1504", (1,))]),
        # L1402：加保日期不存在（9 月沒有 31 日）
        ([("P", "00000", "NEW", "20250931", "XED", "00000000")], [("L1402", (1,))]),
        # L1602：退保日期不存在（2025 不是閏年）
        ([("P", "00000", "NEW", "20250101", "DEA", "20250229")], [("L1602", (1,))]),
        # L1607：退保日期早於加保日期
        ([("P", "00000", "NEW", "20250601", "DEA", "20250501")], [("L1607", (1,))]),
    ],
)
def test_life_field_rules_find_errors(rows, expected):
    assert _found(_life(*rows)) == expected
