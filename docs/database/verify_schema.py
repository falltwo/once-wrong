"""實際驗證 schema.sql：建表、塞模擬資料、跑重複錯誤情境、測觸發器、看查詢計畫。

執行：python -X utf8 verify_schema.py
只用 Python 內建 sqlite3（需 3.44+），不連網、不寫檔（資料庫在記憶體）。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOW = "2026-10-29T16:00:00Z"
ZERO = "0" * 64
REPORT = "life-01-2025"
failures: list[str] = []

# 填報手冊的 key 值順序（人壽保險業個人壽險填報手冊 2025，承保 p.5、給付 p.31、填報對象 p.37）
UW_KEY = ["公司代號", "保單編號", "保單編號序號", "加保日期", "異動序號"]
CLAIM_KEY = ["給付類別", "公司代號", "保單編號", "保單編號序號"]
SUBJECT_KEY = ["公司代號", "填報年度", "險別", "保險商品編號", "公司保單險種代號"]
POLICY = ["公司代號", "保單編號", "保單編號序號"]
DATASETS = {
    "LIFE_UW": ("underwriting", "個人壽險承保資料", UW_KEY, POLICY),
    "LIFE_CLAIM": ("claim", "個人壽險給付資料", CLAIM_KEY, POLICY),
    "LIFE_SUBJECT": ("subject", "個人壽險填報對象資料", SUBJECT_KEY, None),
}


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def keys(dataset: str, fields: dict) -> tuple[str, str | None]:
    _, _, key_fields, group_fields = DATASETS[dataset]
    group = dumps([fields[f] for f in group_fields]) if group_fields else None
    return dumps([fields[f] for f in key_fields]), group


def issue_key(rule_code: str, level: str, cells: list[tuple[dict, str]], dataset: str = "LIFE_UW") -> str:
    """規則代碼＋層級＋排序去重後的（定位鍵, 欄位）→ sha256。不用列號。"""
    pick = 0 if level == "record" else 1
    located = sorted({(keys(dataset, row)[pick], field) for row, field in cells})
    return hashlib.sha256(dumps([rule_code, level, located]).encode("utf-8")).hexdigest()


def check(label: str, ok: bool) -> None:
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        failures.append(label)


def expect_abort(db: sqlite3.Connection, label: str, sql: str, params: tuple = ()) -> None:
    try:
        db.execute(sql, params)
    except sqlite3.DatabaseError as error:
        print(f"PASS {label}  ({error})")
        return
    print(f"FAIL {label}  (statement was accepted)")
    failures.append(label)


def uw(policy: str, seq: str, entry: str, entry_date: str, exit_kind: str = "XED", exit_date: str = "00000000") -> dict:
    """承保檔模擬資料（欄名照手冊；值參考 feat/ai-review 的 mock_life_policies_2025.csv 改寫）。"""
    return {"公司代號": "01", "保單編號": policy, "保單編號序號": "0001", "異動序號": seq,
            "加保別": entry, "加保日期": entry_date, "退保別": exit_kind, "退保日期": exit_date}


def main() -> int:
    print("sqlite", sqlite3.sqlite_version)
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript((HERE / "schema.sql").read_text(encoding="utf-8"))
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")]
    print("tables:", ", ".join(tables))

    # --- 參照資料 ---
    for code, (kind, name, key_fields, group_fields) in DATASETS.items():
        db.execute("INSERT INTO dataset_type VALUES (?,'life',?,?,?,?)",
                   (code, kind, name, dumps(key_fields), dumps(group_fields) if group_fields else None))
    db.execute(
        "INSERT INTO rule_set VALUES (1,'life','life-2025','新式個人壽險填報手冊範例&檢核規則_2025',?,2025,?)",
        ("3003e7cf521fb6cc0f69f888ba769a7394f490bd274a9a38dc687e3ae13ca660", NOW),
    )
    rules = [  # handler 名稱為示意；頁碼為手冊「資料欄位檢核」頁
        (1, "L1305", "multi_record", "EntryContinuesPreviousExit", "{}", "record", "伍-16"),
        (2, "L1402", "single_record", "ValidDate", '{"column":"加保日期"}', "group", "伍-17"),
        (3, "L0302", "multi_record", "TxnSeqInOrder", "{}", "group", "伍-14"),
    ]
    for rid, code, scope, handler, params, level, page in rules:
        db.execute(
            "INSERT INTO rule (id,rule_set_id,code,dataset_type,title,scope,handler,params,issue_key_level,manual_page)"
            " VALUES (?,1,?,'LIFE_UW',?,?,?,?,?,?)",
            (rid, code, f"規則 {code}", scope, handler, params, level, page),
        )
    expect_abort(db, "保單層級規則不能用在沒有保單的填報對象檔",
                 "INSERT INTO rule (id,rule_set_id,code,dataset_type,title,scope,handler,issue_key_level,manual_page)"
                 " VALUES (9,1,'X0001','LIFE_SUBJECT','x','single_record','x','group','x')")
    db.execute("INSERT INTO report VALUES (?,'01','LIFE_UW',2025,'個人壽險承保 2025',?)", (REPORT, NOW))

    def add_version(report: str, dataset: str, number: int, rows: list[dict]) -> tuple[str, dict]:
        vid = f"{report}:v{number}"
        raw = dumps(rows).encode("utf-8")
        db.execute("INSERT INTO version VALUES (?,?,?,?,?,?,1,?,'tester',?)",
                   (vid, report, number, f"v{number}.txt", raw, hashlib.sha256(raw).hexdigest(), len(rows), NOW))
        ids = {}
        for line_no, fields in enumerate(rows, start=1):
            record_key, group_key = keys(dataset, fields)
            cur = db.execute(
                "INSERT INTO record (version_id,line_no,record_key,group_key,raw_line,fields) VALUES (?,?,?,?,?,?)",
                (vid, line_no, record_key, group_key, "".join(fields.values()), dumps(fields)))
            ids[record_key] = cur.lastrowid
        return vid, ids

    def add_issue(vid: str, number: int, rule_id: int, code: str, level: str, cells, status: str,
                  prev: int | None, first: int, ids: dict) -> str:
        key = issue_key(code, level, cells)
        iid = f"{vid}:{code}:{key[:8]}"
        db.execute(
            "INSERT INTO issue (id,version_id,report_id,version_number,rule_id,issue_key,message,"
            "repeat_status,prev_seen_number,first_seen_number,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (iid, vid, REPORT, number, rule_id, key, f"{code} 違規", status, prev, first, NOW))
        for row, field in cells:
            db.execute("INSERT INTO issue_cell VALUES (?,?,?)", (iid, ids[keys("LIFE_UW", row)[0]], field))
        return iid

    def history(code: str, level: str, cells) -> list:
        return db.execute(
            "SELECT version_number, repeat_status, prev_seen_number, first_seen_number FROM issue"
            " WHERE issue_key=? ORDER BY version_number", (issue_key(code, level, cells),)).fetchall()

    # v1：L1305（A00002 第 2 筆加保別）、L1402（A00003 加保日期 13 月）、L0302（A00004 異動序號 00001、00003、00003）
    p2 = [uw("A00002", "00001", "NEW", "20250301"),
          uw("A00002", "00002", "RNN", "20250801", "INN", "20250801")]
    p3_bad = uw("A00003", "00000", "NEW", "20251340")
    p4_v1 = [uw("A00004", "00001", "NEW", "20250105"),
             uw("A00004", "00003", "INN", "20250601"),
             uw("A00004", "00003", "INN", "20250901")]
    v1, ids1 = add_version(REPORT, "LIFE_UW", 1, [*p2, p3_bad, *p4_v1])
    l1305 = [(p2[1], "加保別")]
    l1402_v1 = [(p3_bad, "加保日期")]
    l0302_v1 = [(p4_v1[1], "異動序號"), (p4_v1[2], "異動序號")]
    iid1 = add_issue(v1, 1, 1, "L1305", "record", l1305, "new", None, 1, ids1)
    add_issue(v1, 1, 2, "L1402", "group", l1402_v1, "new", None, 1, ids1)
    add_issue(v1, 1, 3, "L0302", "group", l0302_v1, "new", None, 1, ids1)
    db.execute("INSERT INTO issue_context VALUES (?,?)", (iid1, ids1[keys("LIFE_UW", p2[0])[0]]))

    # v2：L1402 修好；L1305 沒改；L0302 改成 00001、00002、00004，序號變了但還是錯
    p3_ok = {**p3_bad, "加保日期": "20251201"}
    p4_v2 = [p4_v1[0], {**p4_v1[1], "異動序號": "00002"}, {**p4_v1[2], "異動序號": "00004"}]
    v2, ids2 = add_version(REPORT, "LIFE_UW", 2, [*p2, p3_ok, *p4_v2])
    l0302_v2 = [(p4_v2[2], "異動序號")]
    add_issue(v2, 2, 1, "L1305", "record", l1305, "repeated", 1, 1, ids2)
    add_issue(v2, 2, 3, "L0302", "group", l0302_v2, "repeated", 1, 1, ids2)
    check("L0302：序號從 00003 改成 00004 仍錯，用整筆主鍵會判成不同的錯（AI 端舉的例子）",
          issue_key("L0302", "record", l0302_v1) != issue_key("L0302", "record", l0302_v2))
    check("L0302：改用保單層級後 v2 判成 repeated", history("L0302", "group", l0302_v2) == [(1, "new", None, 1), (2, "repeated", 1, 1)])
    check("L1305：v1 new → v2 repeated", history("L1305", "record", l1305) == [(1, "new", None, 1), (2, "repeated", 1, 1)])

    # v3：資料順序整個反過來；L1305、L0302 修好；L1402 又壞掉，而且壞成另一個值
    p2_ok = [p2[0], {**p2[1], "加保別": "INN"}]
    p3_bad2 = {**p3_bad, "加保日期": "20251399"}
    p4_ok = [p4_v1[0], {**p4_v1[1], "異動序號": "00002"}, {**p4_v1[2], "異動序號": "00003"}]
    v3, ids3 = add_version(REPORT, "LIFE_UW", 3, list(reversed([*p2_ok, p3_bad2, *p4_ok])))
    l1402_v3 = [(p3_bad2, "加保日期")]
    iid3 = add_issue(v3, 3, 2, "L1402", "group", l1402_v3, "regressed", 1, 1, ids3)
    check("L1402：加保日期是主鍵的一部分，壞成另一個值時整筆主鍵會變",
          issue_key("L1402", "record", l1402_v1) != issue_key("L1402", "record", l1402_v3))
    check("L1402：用保單層級，v1 new → v2 修好 → v3 regressed（v3 列順序已打亂）",
          history("L1402", "group", l1402_v3) == [(1, "new", None, 1), (3, "regressed", 1, 1)])
    fixed_in = db.execute("SELECT prev_seen_number + 1 FROM issue WHERE id=?", (iid3,)).fetchone()[0]
    check("regressed 的錯查得到在哪一版修好（v2，給前端顯示）", fixed_in == 2)

    # 觸發器與 CHECK：判定寫錯會被擋
    k = issue_key("L1402", "group", l1402_v3)
    cols = ("INSERT INTO issue (id,version_id,report_id,version_number,rule_id,issue_key,message,"
            "repeat_status,prev_seen_number,first_seen_number,created_at) VALUES ")
    expect_abort(db, "把 regressed 謊報成 new 會被擋", cols + "('bad',?,?,3,2,?,'x','new',NULL,3,?)", (v3, REPORT, k, NOW))
    expect_abort(db, "prev_seen_number 寫錯會被擋", cols + "('bad2',?,?,3,2,?,'x','regressed',2,1,?)", (v3, REPORT, k, NOW))
    expect_abort(db, "把 regressed 謊報成 repeated 會被擋", cols + "('bad3',?,?,3,2,?,'x','repeated',1,1,?)", (v3, REPORT, k, NOW))
    expect_abort(db, "first_seen_number 寫錯會被擋",
                 cols + "('bad4',?,?,3,1,?,'x','regressed',1,2,?)", (v3, REPORT, issue_key("L1305", "record", l1305), NOW))

    # 主鍵欄位與 fields 必須一致
    good = uw("A00009", "00000", "NEW", "20250101")
    rk, gk = keys("LIFE_UW", good)
    insert = "INSERT INTO record (version_id,line_no,record_key,group_key,raw_line,fields) VALUES (?,?,?,?,?,?)"
    missing = {f: v for f, v in good.items() if f != "加保日期"}
    expect_abort(db, "缺主鍵欄位（加保日期）的資料列會被擋", insert, (v3, 99, rk, gk, "x", dumps(missing)))
    expect_abort(db, "record_key 跟 fields 對不上會被擋", insert, (v3, 99, rk.replace("A00009", "A00008"), gk, "x", dumps(good)))
    expect_abort(db, "group_key 跟 fields 對不上會被擋", insert, (v3, 99, rk, None, "x", dumps(good)))

    # 給付檔、填報對象檔：主鍵欄位不同也放得進去
    db.execute("INSERT INTO report VALUES ('life-01-2025-claim','01','LIFE_CLAIM',2025,'個人壽險給付 2025',?)", (NOW,))
    db.execute("INSERT INTO report VALUES ('life-01-2025-subject','01','LIFE_SUBJECT',2025,'個人壽險填報對象 2025',?)", (NOW,))
    claim = {"給付類別": "1", "公司代號": "01", "保單編號": "A00002", "保單編號序號": "0001", "死亡完全失能或應給付生存還本日期": "20250801"}
    subject = {"公司代號": "01", "填報年度": "2025", "險別": "1", "商品名稱": "模擬終身壽險",
               "保險商品編號": "201A1X1IA00ETI000000000000000", "公司保單險種代號": "WL01", "有效契約件數": "000000000000000120"}
    add_version("life-01-2025-claim", "LIFE_CLAIM", 1, [claim])
    add_version("life-01-2025-subject", "LIFE_SUBJECT", 1, [subject])
    stored = db.execute("SELECT r.record_key, r.group_key FROM record r JOIN version v ON v.id = r.version_id"
                        " WHERE v.report_id IN ('life-01-2025-claim','life-01-2025-subject') ORDER BY v.report_id").fetchall()
    check("給付檔（沒有異動序號）與填報對象檔（沒有保單號碼）都存得進去，填報對象檔沒有 group_key",
          stored == [keys("LIFE_CLAIM", claim), keys("LIFE_SUBJECT", subject)] and stored[1][1] is None)

    # 確認：v3 還有錯 → 擋；v2 不是最新 → 擋
    sha = lambda vid: db.execute("SELECT source_sha256 FROM version WHERE id=?", (vid,)).fetchone()[0]
    expect_abort(db, "有 error 等級的錯不能確認",
                 "INSERT INTO confirmation VALUES ('c1',?,?,'tester',?,1,?)", (REPORT, v3, sha(v3), NOW))
    expect_abort(db, "舊版本不能確認",
                 "INSERT INTO confirmation VALUES ('c2',?,?,'tester',?,1,?)", (REPORT, v2, sha(v2), NOW))
    # v4：全部修好 → 可以確認
    v4, _ = add_version(REPORT, "LIFE_UW", 4, list(reversed([*p2_ok, p3_ok, *p4_ok])))
    expect_abort(db, "確認時雜湊值對不上會被擋",
                 "INSERT INTO confirmation VALUES ('c3',?,?,'tester',?,1,?)", (REPORT, v4, "f" * 64, NOW))
    db.execute("INSERT INTO confirmation VALUES ('c4',?,?,'tester',?,1,?)", (REPORT, v4, sha(v4), NOW))
    check("沒有錯的最新版本可以確認", db.execute("SELECT count(*) FROM confirmation").fetchone()[0] == 1)

    # 版本號必須連續
    expect_abort(db, "跳號的版本會被擋",
                 "INSERT INTO version VALUES ('v9',?,9,'x',x'00',?,1,0,'tester',?)", (REPORT, "a" * 64, NOW))

    # 不可修改
    expect_abort(db, "版本不能修改", "UPDATE version SET filename='x' WHERE id=?", (v1,))
    expect_abort(db, "資料列不能修改", "UPDATE record SET fields='{}' WHERE id=1")
    expect_abort(db, "檢核結果不能刪除", "DELETE FROM issue WHERE id=?", (iid3,))

    # AI 審核與建議
    db.execute("INSERT INTO ai_review VALUES ('r1',?,'gemini-3.5-flash','ai','加保日期不是有效日期','13 月不存在。','[]',?)", (iid3, NOW))
    db.execute("INSERT INTO suggestion VALUES (1,'r1',1,'改成 12 月',  'passed',NULL)")
    db.execute("INSERT INTO suggestion VALUES (2,'r1',2,'改成 13 月1日','failed','重驗後 L1402 仍失敗')")
    rec = db.execute("SELECT record_id FROM issue_cell WHERE issue_id=?", (iid3,)).fetchone()[0]
    db.execute("INSERT INTO suggestion_change VALUES (1,?, '加保日期','20251399','20251201')", (rec,))
    db.execute("INSERT INTO citation VALUES ('r1','LIFE-RULE-0068','新式個人壽險填報手冊範例&檢核規則_2025','伍、資料欄位檢核','伍-17')")
    expect_abort(db, "通過重驗的建議不能附上拒絕原因",
                 "INSERT INTO suggestion VALUES (3,'r1',3,'x','passed','不該有')")
    expect_abort(db, "跨版本的出錯格子會被擋",
                 "INSERT INTO issue_cell VALUES (?,?, '加保日期')", (iid3, ids1[keys("LIFE_UW", p3_bad)[0]]))
    expect_abort(db, "跨版本的參考資料列會被擋",
                 "INSERT INTO issue_context VALUES (?,?)", (iid3, ids1[keys("LIFE_UW", p2[0])[0]]))
    shown = db.execute(
        "SELECT count(*) FROM suggestion WHERE ai_review_id='r1' AND revalidation='passed'").fetchone()[0]
    check("只有通過重驗的建議會被選出來顯示", shown == 1)

    # 稽核鏈
    prev = ZERO
    for n, event in enumerate(["version_uploaded", "validation_completed", "confirmation_recorded"], start=1):
        payload = json.dumps({"n": n}, sort_keys=True)
        digest = hashlib.sha256((prev + payload).encode()).hexdigest()
        db.execute("INSERT INTO audit_event VALUES (?,?, 'tester', ?, ?, NULL, ?, ?, ?)",
                   (n, NOW, event, v4, payload, prev, digest))
        prev = digest
    expect_abort(db, "稽核鏈不能分岔（同一個 prev_hash 用兩次）",
                 "INSERT INTO audit_event VALUES (9,?, 'x','version_uploaded',NULL,NULL,'{}',?,?)", (NOW, ZERO, "b" * 64))
    expect_abort(db, "稽核事件不能修改", "UPDATE audit_event SET actor='x' WHERE id=1")
    ok = True
    prev = ZERO
    for _id, payload, p, h in db.execute("SELECT id,payload,prev_hash,hash FROM audit_event ORDER BY id"):
        ok &= p == prev and h == hashlib.sha256((prev + payload).encode()).hexdigest()
        prev = h
    check("稽核鏈從頭驗到尾都對得上", ok)

    # 查詢計畫：每個主要查詢都要用到索引
    queries = {
        "Q1 某申報的版本清單": ("SELECT number, filename FROM version WHERE report_id=? ORDER BY number", (REPORT,)),
        "Q2 某版本的檢核結果（依規則篩）": ("SELECT id FROM issue WHERE version_id=? AND rule_id=?", (v3, 2)),
        "Q3 判斷重複錯誤（查歷史）": ("SELECT max(version_number), min(version_number) FROM issue"
                              " WHERE report_id=? AND issue_key=? AND version_number<?", (REPORT, k, 3)),
        "Q4 一個錯的出錯格子": ("SELECT record_id, field_name FROM issue_cell WHERE issue_id=?", (iid3,)),
        "Q5 同一保單在某版本的所有資料列": ("SELECT line_no FROM record WHERE version_id=? AND group_key=?",
                                 (v3, keys("LIFE_UW", p2[0])[1])),
        "Q6 某規則版本、某檔案種類的規則": ("SELECT code FROM rule WHERE rule_set_id=? AND dataset_type=?", (1, "LIFE_UW")),
        "Q7 某個錯最新的 AI 審核": ("SELECT id FROM ai_review WHERE issue_id=? ORDER BY created_at DESC LIMIT 1", (iid3,)),
        "Q8 某版本的稽核事件": ("SELECT event_type FROM audit_event WHERE version_id=? ORDER BY id", (v4,)),
        "Q9 某申報最新的確認": ("SELECT version_id FROM confirmation WHERE report_id=? ORDER BY confirmed_at DESC LIMIT 1", (REPORT,)),
        "Q10 某版本重複的主鍵": ("SELECT record_key FROM record WHERE version_id=? GROUP BY record_key HAVING count(*) > 1", (v1,)),
        "Q11 一個錯的參考資料列": ("SELECT record_id FROM issue_context WHERE issue_id=?", (iid1,)),
    }
    for label, (sql, params) in queries.items():
        plan = " | ".join(r[3] for r in db.execute("EXPLAIN QUERY PLAN " + sql, params))
        uses_index = ("USING INDEX" in plan or "USING COVERING INDEX" in plan
                      or "USING PRIMARY KEY" in plan or "USING INTEGER PRIMARY KEY" in plan)
        check(f"{label}: {plan}", uses_index and "SCAN" not in plan.replace("SCAN CONSTANT ROW", ""))

    fk = db.execute("PRAGMA foreign_key_check").fetchall()
    check("外鍵全部一致（foreign_key_check 無結果）", fk == [])
    print()
    print("RESULT:", "ALL PASS" if not failures else f"{len(failures)} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
