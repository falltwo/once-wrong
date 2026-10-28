from pathlib import Path

import pytest

from once_wrong_ai.kb.ingest import ingest
from once_wrong_ai.kb.memory import RuleMemory
from once_wrong_ai.kb.models import Passage, PassageKind
from once_wrong_ai.kb.search import Retriever, normalize, tokenize

KB_DIR = Path(__file__).parents[1] / "data" / "kb"


def _p(id, text, kind=PassageKind.RULE, product="個人壽險", caption=None, field=None):
    return Passage(
        id=id, product=product, manual="手冊", section=["檢核"], kind=kind, text=text,
        caption=caption, extra={"field": field} if field else {},
    )


@pytest.fixture
def retriever():
    return Retriever([
        _p("R1", "異動序號 L0302 30201_L0302 保單只有一筆時異動序號=00000，代號依『表 3．1．1 公司簡稱與代號表』"),
        _p("R2", "L03021 這是別條規則"),
        _p("R3", "L0302 年金的同名代碼", product="個人年金"),
        _p("F1", "4. 異動序號\n為五位數字，只有 1 筆資料者請填 00000", kind=PassageKind.FIELD, field="異動序號"),
        _p("T1", "代號 公司\n01 臺銀人壽", kind=PassageKind.CODE_TABLE, caption="表 3．1．1 公司簡稱與代號表"),
        _p("T2", "代號 通路\n1 業務員", kind=PassageKind.CODE_TABLE, caption="表 3．1．12 通路別代號表"),
    ])


def test_normalize_removes_spaces_between_chinese():
    assert normalize("保 險 金 額 (原幣)") == "保險金額 (原幣)"
    assert "異動" in tokenize("異 動 序 號")


def test_find_code_respects_boundaries_and_product(retriever):
    assert [p.id for p in retriever.find_code("L0302", "個人壽險")] == ["R1"]
    assert [p.id for p in retriever.find_code("L0302", "個人年金")] == ["R3"]


def test_find_table_does_not_match_longer_number(retriever):
    assert [p.id for p in retriever.find_table("表3.1.1")] == ["T1"]


def test_for_violation_collects_rule_table_and_field(retriever):
    ids = [p.id for p in retriever.for_violation("L0302", ["異動序號"], product="個人壽險")]
    assert ids == ["R1", "T1", "F1"]


def test_for_violation_respects_budget(retriever):
    budget = 90
    picked = retriever.for_violation("L0302", ["異動序號"], product="個人壽險", budget_chars=budget)
    assert picked[0].id == "R1"
    assert "F1" not in [p.id for p in picked]
    assert sum(len(p.text) for p in picked) <= budget


def test_ingest_docx_tags_sections_fields_and_tables(tmp_path):
    docx = pytest.importorskip("docx")
    from docx.enum.style import WD_STYLE_TYPE

    doc = docx.Document()
    doc.styles.add_style("欄位+標號1", WD_STYLE_TYPE.PARAGRAPH)
    doc.styles.add_style("表格標題1", WD_STYLE_TYPE.PARAGRAPH)
    doc.add_heading("資料欄位說明", level=1)
    doc.add_paragraph("異動序號", style="欄位+標號1")
    doc.add_paragraph("為五位數字，只有一筆資料者請填 00000，兩筆以上從 00001 開始依序填列。")
    doc.add_paragraph("表3．1．1　公司簡稱與代號表", style="表格標題1")
    table = doc.add_table(rows=3, cols=2)
    for row, (a, b) in zip(table.rows, [("代號", "公司簡稱"), ("01", "臺銀人壽"), ("02", "台灣人壽")]):
        row.cells[0].text, row.cells[1].text = a, b
    doc.add_heading("檢核規則", level=1)
    rules = doc.add_table(rows=2, cols=3)
    for row, cells in zip(rules.rows, [("欄位名稱", "檢核編號", "檢核說明"), ("異動序號", "L04B04", "同保單號碼資料第1筆資料之異動序號=(00000或00001)")]):
        for cell, text in zip(row.cells, cells):
            cell.text = text
    path = tmp_path / "manual.docx"
    doc.save(path)

    passages = ingest(path, product="傷害保險")
    by_kind = {p.kind: p for p in passages}

    assert by_kind[PassageKind.FIELD].extra["field"] == "異動序號"
    assert by_kind[PassageKind.CODE_TABLE].caption.startswith("表3．1．1")
    assert "01 | 臺銀人壽" in by_kind[PassageKind.CODE_TABLE].text
    rule = by_kind[PassageKind.RULE]
    assert rule.section == ["檢核規則"] and "L04B04" in rule.text


def test_rule_memory_persists(tmp_path):
    path = tmp_path / "notes.jsonl"
    RuleMemory(path).add("L0302", "只有一筆時填 00000", product="個人壽險")
    reloaded = RuleMemory(path)
    assert [n.note for n in reloaded.notes_for("L0302", "個人壽險")] == ["只有一筆時填 00000"]
    assert reloaded.notes_for("L0302", "傷害保險") == []


@pytest.mark.skipif(not (KB_DIR / "passages.jsonl").exists(), reason="需要先建立知識庫（手冊不進版控）")
def test_real_manuals_l0302():
    r = Retriever.from_dir(str(KB_DIR))
    picked = r.for_violation("L0302", ["異動序號"], product="個人壽險")
    assert any(p.kind is PassageKind.RULE and "L0302" in p.text for p in picked)
    assert any(p.extra.get("field") == "異動序號" for p in picked)
