from conftest import FakeLLM

from once_wrong.ai_review import AIReviewer, ExplanationSource, LLMError, MemoryAuditLog
from once_wrong.ai_review.models import AIChange, AIExplanation, AIFixCandidate
from once_wrong.report import CellRef


def _explain(text, *candidates):
    return AIExplanation(
        title="本月期初跟上月期末對不起來",
        explanation=text,
        candidates=[
            AIFixCandidate(changes=[AIChange(row=r, column=c, new_value=v) for r, c, v in cs], reason="")
            for cs in candidates
        ],
    )


def _row3_only(report):
    """只留下第 3 列的 R-07 錯誤，方便單獨測一筆。"""
    report.rows = [report.rows[2]]
    return report


def test_bad_candidate_hidden_good_candidate_shown(report, rules):
    report = _row3_only(report)
    llm = FakeLLM([
        _explain(
            "上月期末 12,480,000，本月期初卻是 12,005,000，差 475,000。",
            [(1, "本月期初", "12,408,000")],  # 抄錯數字：重驗不過
            [(1, "本月期初", "12,480,000")],
        )
    ])
    audit = MemoryAuditLog()
    [item] = AIReviewer(llm, rules, audit).review(report)

    assert item.source is ExplanationSource.AI
    assert item.suggestion.changes == {CellRef(1, "本月期初"): 12_480_000}
    assert len(item.rejected) == 1
    assert [e["event"] for e in audit.entries] == ["rule_check", "ai_review"]


def test_wrong_number_in_explanation_falls_back(report, rules):
    report = _row3_only(report)
    llm = FakeLLM([_explain("差了 457,000。", [(1, "本月期初", "12,480,000")])])
    [item] = AIReviewer(llm, rules).review(report)

    assert item.source is ExplanationSource.FALLBACK_NUMBER_GUARD
    assert item.blocked_numbers == ["457,000"]
    assert item.explanation == item.violation.message
    # 修法本身通過重驗，仍保留
    assert item.suggestion is not None and item.suggestion.reason == ""


def test_llm_error_falls_back(report, rules):
    report = _row3_only(report)
    llm = FakeLLM([LLMError("timeout")])
    audit = MemoryAuditLog()
    [item] = AIReviewer(llm, rules, audit).review(report)

    assert item.source is ExplanationSource.FALLBACK_LLM_ERROR
    assert item.suggestion is None
    assert audit.entries[-1]["event"] == "ai_error"


def test_only_error_rows_are_sent_to_ai(report, rules):
    llm = FakeLLM([_explain("x") for _ in range(3)])
    AIReviewer(llm, rules).review(report)

    prompt_for_row3 = next(p for p in llm.prompts if "ML-05" in p)
    assert "CR-01" not in prompt_for_row3
    assert "9,812,400" not in prompt_for_row3


def test_manual_passages_are_sent_and_cited(report, rules):
    from once_wrong.kb.models import Passage, PassageKind
    from once_wrong.kb.search import Retriever

    knowledge = Retriever([
        Passage(id="M1", product="準備金", manual="準備金手冊", section=["檢核規則"], kind=PassageKind.RULE,
                text="R-07 本月期初應等於上月期末，容許差異 0，差異超過 1,000 需附說明。", page=12),
    ])
    report = _row3_only(report)
    report.meta["險別"] = "準備金"
    reply = _explain("依手冊，差異超過 1,000 就要處理；這裡差 475,000。", [(1, "本月期初", "12,480,000")])
    reply.citations = ["K1", "K9"]
    llm = FakeLLM([reply])

    [item] = AIReviewer(llm, rules, knowledge=knowledge).review(report)

    assert "R-07 本月期初應等於上月期末" in llm.prompts[0]
    assert [p.id for p in item.sources] == ["M1"]  # K9 不存在，丟掉
    # 1,000 來自引用的段落，可以講
    assert item.source is ExplanationSource.AI


def test_uncited_passage_numbers_are_not_allowed(report, rules):
    from once_wrong.kb.models import Passage, PassageKind
    from once_wrong.kb.search import Retriever

    knowledge = Retriever([
        Passage(id="M1", product="準備金", manual="手冊", section=["檢核"], kind=PassageKind.RULE,
                text="R-07 差異超過 1,000 需附說明。"),
    ])
    report = _row3_only(report)
    report.meta["險別"] = "準備金"
    llm = FakeLLM([_explain("差異超過 1,000 要處理。")])  # 沒有引用 K1
    [item] = AIReviewer(llm, rules, knowledge=knowledge).review(report)
    assert item.source is ExplanationSource.FALLBACK_NUMBER_GUARD


def test_team_notes_are_sent(report, rules, tmp_path):
    from once_wrong.kb.memory import RuleMemory

    memory = RuleMemory(tmp_path / "notes.jsonl")
    memory.add("R-07", "月中調整一律記在本月期初之後，不可改上月期末。")
    report = _row3_only(report)
    llm = FakeLLM([_explain("x")])
    AIReviewer(llm, rules, memory=memory).review(report)
    assert "月中調整一律記在本月期初之後" in llm.prompts[0]


def test_full_report_reviews_every_violation(report, rules):
    llm = FakeLLM([_explain("x") for _ in range(3)])
    items = AIReviewer(llm, rules).review(report)
    assert sorted(i.violation.rule_id for i in items) == ["R-01", "R-07", "R-07"]


def test_reference_rows_are_sent_separately(life_report, life_rules):
    llm = FakeLLM([_explain("x") for _ in range(3)])
    AIReviewer(llm, life_rules).review(life_report)

    prompt_l0303 = next(p for p in llm.prompts if '"代碼": "L0303"' in p)
    # 同一保單（A00004）的第 7 列放在「相關資料列」，AI 才看得出這張保單有兩筆
    assert '"相關資料列"' in prompt_l0303
    assert "20251001" in prompt_l0303
    # 其他保單的資料不送
    assert "A00003" not in prompt_l0303

    prompt_a00003 = next(p for p in llm.prompts if "A00003" in p)
    assert '"相關資料列"' not in prompt_a00003


def test_other_errors_on_same_row_are_sent():
    from once_wrong.report import Report
    from once_wrong.rules.life import life_field_rules

    columns = ["公司代號", "保單編號", "保單編號序號", "異動序號", "加保別", "加保日期", "退保別", "退保日期"]
    report = Report("t", 1, columns, [dict(zip(columns, ("01", "P", "00001", "00000", "XED", "20250112", "XED", "00000000")))])
    llm = FakeLLM([_explain("x") for _ in range(2)])
    AIReviewer(llm, life_field_rules()).review(report)

    # 同一列同時錯 L1304、L1502，各自的 prompt 都要看得到另一條
    prompt_l1304 = next(p for p in llm.prompts if '"代碼": "L1304"' in p)
    prompt_l1502 = next(p for p in llm.prompts if '"代碼": "L1502"' in p)
    assert '"同一列的其他錯誤"' in prompt_l1304 and '"規則": "L1502"' in prompt_l1304
    assert '"規則": "L1304"' in prompt_l1502


def test_unrelated_rows_errors_are_not_sent(report, rules):
    llm = FakeLLM([_explain("x") for _ in range(3)])
    AIReviewer(llm, rules).review(report)
    assert all('"同一列的其他錯誤"' not in p for p in llm.prompts)
