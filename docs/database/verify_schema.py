"""實際驗證 schema.sql：建表、塞模擬資料、跑重複錯誤情境、測觸發器、看查詢計畫。

執行：python -X utf8 verify_schema.py
只用 Python 內建 sqlite3，不連網、不寫檔（資料庫在記憶體）。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOW = "2026-10-28T16:00:00Z"
ZERO = "0" * 64
failures: list[str] = []


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


def issue_key(rule_code: str, cells: list[tuple[tuple[str, ...], str]]) -> str:
    """規則代碼＋排序後的（業務主鍵, 欄位）→ sha256。不用列號。"""
    canonical = json.dumps([rule_code, sorted([list(k), f] for k, f in cells)], ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    print("sqlite", sqlite3.sqlite_version)
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript((HERE / "schema.sql").read_text(encoding="utf-8"))
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")]
    print("tables:", ", ".join(tables))

    # --- 參照資料 ---
    db.execute("INSERT INTO dataset_type VALUES ('LIFE_UW','life','underwriting','個人壽險承保資料')")
    db.execute("INSERT INTO dataset_type VALUES ('LIFE_CLAIM','life','claim','個人壽險給付資料')")
    db.execute(
        "INSERT INTO rule_set VALUES (1,'life','life-2025','新式個人壽險填報手冊範例&檢核規則_2025',?,2025,?)",
        ("3003e7cf521fb6cc0f69f888ba769a7394f490bd274a9a38dc687e3ae13ca660", NOW),
    )
    rules = [
        (1, "L1305", "multi_record", "EntryContinuesPreviousExit", "{}"),
        (2, "L1402", "single_record", "ValidDate", '{"column":"加保日期"}'),
        (3, "L1602", "single_record", "ValidDate", '{"column":"退保日期"}'),
    ]
    for rid, code, scope, handler, params in rules:
        db.execute(
            "INSERT INTO rule (id,rule_set_id,code,dataset_type,title,scope,handler,params,manual_page)"
            " VALUES (?,1,?,'LIFE_UW',?,?,?,?,'肆、檢核程式項目及代碼表')",
            (rid, code, f"規則 {code}", scope, handler, params),
        )
    db.execute("INSERT INTO report VALUES ('life-01-2025','01','LIFE_UW',2025,'個人壽險承保 2025',?)", (NOW,))

    rows = [  # 取自 feat/ai-review 的 examples/mock_life_policies_2025.csv（模擬資料）
        ("01", "A00002", "0001", "00001", {"加保別": "NEW", "加保日期": "20250301", "退保別": "XED", "退保日期": "00000000"}),
        ("01", "A00002", "0001", "00003", {"加保別": "RNN", "加保日期": "20250801", "退保別": "INN", "退保日期": "20250801"}),
        ("01", "A00003", "0001", "00001", {"加保別": "NEW", "加保日期": "20251340", "退保別": "XED", "退保日期": "00000000"}),
    ]

    def add_version(number: int, record_rows: list) -> tuple[str, dict]:
        vid = f"v{number}"
        raw = json.dumps(record_rows, ensure_ascii=False).encode("utf-8")
        db.execute(
            "INSERT INTO version VALUES (?,?,?,?,?,?,1,?,'tester',?)",
            (vid, "life-01-2025", number, f"life_v{number}.txt", raw, hashlib.sha256(raw).hexdigest(), len(record_rows), NOW),
        )
        ids = {}
        for line_no, (c, p, s, t, fields) in enumerate(record_rows, start=1):
            cur = db.execute(
                "INSERT INTO record (version_id,line_no,company_code,policy_no,policy_seq,txn_seq,raw_line,fields)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (vid, line_no, c, p, s, t, f"{c}{p}{s}{t}", json.dumps(fields, ensure_ascii=False)),
            )
            ids[(c, p, s, t)] = cur.lastrowid
        return vid, ids

    def add_issue(vid: str, number: int, rule_id: int, code: str, cells, status: str, first: int, ids: dict) -> str:
        key = issue_key(code, cells)
        iid = f"{vid}:{code}:{key[:8]}"
        db.execute(
            "INSERT INTO issue VALUES (?,?,'life-01-2025',?,?,?,?,'{}',?,?,?)",
            (iid, vid, number, rule_id, key, f"{code} 違規", status, first, NOW),
        )
        for bkey, field in cells:
            db.execute("INSERT INTO issue_cell VALUES (?,?,?,'error')", (iid, ids[bkey], field))
        return iid

    l1305 = [(("01", "A00002", "0001", "00003"), "加保別")]
    l1402 = [(("01", "A00003", "0001", "00001"), "加保日期")]

    # v1：L1305 與 L1402 都錯
    v1, ids1 = add_version(1, rows)
    add_issue(v1, 1, 1, "L1305", l1305, "new", 1, ids1)
    add_issue(v1, 1, 2, "L1402", l1402, "new", 1, ids1)
    # v2：L1402 修好，L1305 還是錯 → repeated
    rows2 = [r if r[1] != "A00003" else (*r[:4], {**r[4], "加保日期": "20251201"}) for r in rows]
    v2, ids2 = add_version(2, rows2)
    add_issue(v2, 2, 1, "L1305", l1305, "repeated", 1, ids2)
    # v3：L1305 修好（資料順序也換了），L1402 又壞掉 → regressed
    rows3 = list(reversed(rows))
    v3, ids3 = add_version(3, rows3)
    iid3 = add_issue(v3, 3, 2, "L1402", l1402, "regressed", 1, ids3)
    history = db.execute(
        "SELECT version_number, repeat_status, first_seen_number FROM issue WHERE issue_key=? ORDER BY version_number",
        (issue_key("L1402", l1402),)).fetchall()
    check("L1402：v1 new → v2 修好 → v3 regressed（v3 列順序已打亂，issue_key 不依賴列號）",
          history == [(1, "new", 1), (3, "regressed", 1)])
    history = db.execute(
        "SELECT version_number, repeat_status FROM issue WHERE issue_key=? ORDER BY version_number",
        (issue_key("L1305", l1305),)).fetchall()
    check("L1305：v1 new → v2 repeated → v3 修好", history == [(1, "new"), (2, "repeated")])

    # 觸發器：判定寫錯會被擋
    k = issue_key("L1402", l1402)
    expect_abort(db, "把 regressed 謊報成 new 會被擋",
                 "INSERT INTO issue VALUES ('bad','v3','life-01-2025',3,2,?,'x','{}','new',3,?)", (k, NOW))
    expect_abort(db, "first_seen_number 寫錯會被擋",
                 "INSERT INTO issue VALUES ('bad2','v3','life-01-2025',3,1,?,'x','{}','regressed',2,?)",
                 (issue_key("L1305", l1305), NOW))

    # 確認：v3 還有錯 → 擋；v2 不是最新 → 擋
    sha3 = db.execute("SELECT source_sha256 FROM version WHERE id='v3'").fetchone()[0]
    expect_abort(db, "有 error 等級的錯不能確認",
                 "INSERT INTO confirmation VALUES ('c1','life-01-2025','v3','tester',?,1,?)", (sha3, NOW))
    sha2 = db.execute("SELECT source_sha256 FROM version WHERE id='v2'").fetchone()[0]
    expect_abort(db, "舊版本不能確認",
                 "INSERT INTO confirmation VALUES ('c2','life-01-2025','v2','tester',?,1,?)", (sha2, NOW))
    # v4：全部修好 → 可以確認
    rows4 = [r if r[1] != "A00003" else (*r[:4], {**r[4], "加保日期": "20251201"}) for r in rows3]
    add_version(4, rows4)
    sha4 = db.execute("SELECT source_sha256 FROM version WHERE id='v4'").fetchone()[0]
    expect_abort(db, "確認時雜湊值對不上會被擋",
                 "INSERT INTO confirmation VALUES ('c3','life-01-2025','v4','tester',?,1,?)", ("f" * 64, NOW))
    db.execute("INSERT INTO confirmation VALUES ('c4','life-01-2025','v4','tester',?,1,?)", (sha4, NOW))
    check("沒有錯的最新版本可以確認", db.execute("SELECT count(*) FROM confirmation").fetchone()[0] == 1)

    # 版本號必須連續
    expect_abort(db, "跳號的版本會被擋",
                 "INSERT INTO version VALUES ('v9','life-01-2025',9,'x',x'00',?,1,0,'tester',?)", ("a" * 64, NOW))

    # 不可修改
    expect_abort(db, "版本不能修改", "UPDATE version SET filename='x' WHERE id='v1'")
    expect_abort(db, "資料列不能修改", "UPDATE record SET fields='{}' WHERE id=1")
    expect_abort(db, "檢核結果不能刪除", "DELETE FROM issue WHERE id=?", (iid3,))

    # AI 審核與建議
    db.execute("INSERT INTO ai_review VALUES ('r1',?,'gemini-3.5-flash','ai','加保日期不是有效日期','13 月不存在。','[]',?)", (iid3, NOW))
    db.execute("INSERT INTO suggestion VALUES (1,'r1',1,'改成 12 月',  'passed',NULL)")
    db.execute("INSERT INTO suggestion VALUES (2,'r1',2,'改成 13 月1日','failed','重驗後 L1402 仍失敗')")
    rec = db.execute("SELECT record_id FROM issue_cell WHERE issue_id=?", (iid3,)).fetchone()[0]
    db.execute("INSERT INTO suggestion_change VALUES (1,?, '加保日期','20251340','20251201')", (rec,))
    db.execute("INSERT INTO citation VALUES ('r1','K3')")
    expect_abort(db, "通過重驗的建議不能附上拒絕原因",
                 "INSERT INTO suggestion VALUES (3,'r1',3,'x','passed','不該有')")
    expect_abort(db, "跨版本的格子會被擋",
                 "INSERT INTO issue_cell VALUES (?,?, '加保日期','error')", (iid3, ids1[("01", "A00003", "0001", "00001")]))
    shown = db.execute(
        "SELECT count(*) FROM suggestion WHERE ai_review_id='r1' AND revalidation='passed'").fetchone()[0]
    check("只有通過重驗的建議會被選出來顯示", shown == 1)

    # 稽核鏈
    prev = ZERO
    for n, event in enumerate(["version_uploaded", "validation_completed", "confirmation_recorded"], start=1):
        payload = json.dumps({"n": n}, sort_keys=True)
        digest = hashlib.sha256((prev + payload).encode()).hexdigest()
        db.execute("INSERT INTO audit_event VALUES (?,?, 'tester', ?, 'v4', NULL, ?, ?, ?)",
                   (n, NOW, event, payload, prev, digest))
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
        "Q1 某申報的版本清單": ("SELECT number, filename FROM version WHERE report_id=? ORDER BY number", ("life-01-2025",)),
        "Q2 某版本的檢核結果（依規則篩）": ("SELECT id FROM issue WHERE version_id=? AND rule_id=?", ("v3", 2)),
        "Q3 判斷重複錯誤（查歷史）": ("SELECT version_number FROM issue WHERE report_id=? AND issue_key=? AND version_number<?",
                              ("life-01-2025", k, 3)),
        "Q4 一個錯牽涉的格子": ("SELECT record_id, field_name FROM issue_cell WHERE issue_id=?", (iid3,)),
        "Q5 同一保單在某版本的所有資料列": ("SELECT line_no FROM record WHERE version_id=? AND company_code=? AND policy_no=? AND policy_seq=? ORDER BY txn_seq",
                                 ("v3", "01", "A00002", "0001")),
        "Q6 某規則版本、某檔案種類的規則": ("SELECT code FROM rule WHERE rule_set_id=? AND dataset_type=?", (1, "LIFE_UW")),
        "Q7 某個錯最新的 AI 審核": ("SELECT id FROM ai_review WHERE issue_id=? ORDER BY created_at DESC LIMIT 1", (iid3,)),
        "Q8 某版本的稽核事件": ("SELECT event_type FROM audit_event WHERE version_id=? ORDER BY id", ("v4",)),
        "Q9 某申報最新的確認": ("SELECT version_id FROM confirmation WHERE report_id=? ORDER BY confirmed_at DESC LIMIT 1", ("life-01-2025",)),
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
