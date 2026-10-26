from once_wrong.ai_review.guard import allowed_numbers, extract_numbers, find_unsupported_numbers


def _r07_row3(report, rules):
    return next(v for v in rules.check(report) if v.rule_id == "R-07" and v.rows == [3])


def test_codes_are_not_numbers():
    assert extract_numbers("規則 R-07 在 ML-05 這列沒通過") == []


def test_extracts_numbers_with_commas_and_fullwidth():
    assert extract_numbers("差 475,000，原本 １２,００５,０００。") == ["475,000", "12,005,000"]


def test_numbers_from_data_are_allowed(report, rules):
    v = _r07_row3(report, rules)
    text = "第 3 列上月期末 12,480,000，本月期初卻是 12,005,000，差 475,000。"
    assert find_unsupported_numbers([text], allowed_numbers(report, v)) == []


def test_made_up_number_is_caught(report, rules):
    v = _r07_row3(report, rules)
    text = "本月期初少了 457,000。"
    assert find_unsupported_numbers([text], allowed_numbers(report, v)) == ["457,000"]


def test_numbers_from_other_rows_are_not_allowed(report, rules):
    v = _r07_row3(report, rules)
    # 9,812,400 是第 1 列的值，不在這次送給 AI 的資料裡
    assert find_unsupported_numbers(["參考 9,812,400"], allowed_numbers(report, v)) == ["9,812,400"]
