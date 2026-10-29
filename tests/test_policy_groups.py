"""Policy rules must not combine records or evidence from different insurers."""

import pytest

from once_wrong_ai.report import Report
from once_wrong_ai.rules.life import (
    FirstTransactionNotTerminated,
    NewContractIsFirst,
    life_field_rules,
)


def _row(company, sequence, entry, entry_date, exit_, exit_date):
    return {
        "公司代號": company,
        "保單編號": "A00003",
        "保單編號序號": "0001",
        "異動序號": sequence,
        "加保別": entry,
        "加保日期": entry_date,
        "退保別": exit_,
        "退保日期": exit_date,
    }


def _report(*rows):
    return Report(
        report_id="company-policy-groups",
        version=1,
        columns=list(rows[0]),
        rows=list(rows),
    )


def test_same_policy_number_in_two_companies_is_two_valid_singletons():
    report = _report(
        _row("01", "00000", "NEW", "20250101", "XED", "00000000"),
        _row("02", "00000", "NEW", "20250101", "XED", "00000000"),
    )

    assert life_field_rules().check(report) == []


def test_interleaved_companies_keep_their_own_transaction_sequence_and_chain():
    report = _report(
        _row("01", "00001", "NEW", "20250101", "INN", "20250301"),
        _row("02", "00001", "NEW", "20250201", "DNN", "20250401"),
        _row("01", "00002", "INN", "20250301", "DEA", "20250601"),
        _row("02", "00002", "DNN", "20250401", "XED", "00000000"),
    )

    assert life_field_rules().check(report) == []


@pytest.mark.parametrize(
    ("rule", "bad_row"),
    [
        (
            FirstTransactionNotTerminated(),
            _row("01", "00001", "NEW", "20250101", "DEA", "20250201"),
        ),
        (
            NewContractIsFirst(),
            _row("01", "00002", "NEW", "20250101", "INN", "20250201"),
        ),
    ],
)
def test_reference_rows_exclude_other_company_with_same_policy_number(rule, bad_row):
    report = _report(
        bad_row,
        _row("02", "00001", "NEW", "20250101", "INN", "20250201"),
        _row("01", "00003", "INN", "20250201", "XED", "00000000"),
        _row("02", "00002", "INN", "20250201", "XED", "00000000"),
    )

    violations = rule.check(report)

    assert len(violations) == 1
    assert violations[0].rows == [1]
    assert violations[0].reference_rows == [3]
