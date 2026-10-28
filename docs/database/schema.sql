-- Once Wrong 資料表設計（SQLite 3.37+，STRICT tables）
-- 對應文件：資料表設計.md
-- 每個連線都要先執行：
--   PRAGMA foreign_keys = ON;
--   PRAGMA journal_mode = WAL;
-- 時間一律存 UTC ISO 8601 文字，例如 2026-10-28T15:28:43Z（由程式寫入）。

---------------------------------------------------------------------------
-- 1. 參照資料：申報檔案種類、規則版本、檢核規則
---------------------------------------------------------------------------

-- 申報檔案種類：一個險種有多種檔案（例如個人壽險的承保檔、給付檔）
CREATE TABLE dataset_type (
    code          TEXT PRIMARY KEY CHECK (code GLOB '[A-Z]*' AND length(code) <= 32),
    product       TEXT NOT NULL CHECK (product IN ('life', 'annuity', 'cancer', 'accident')),
    file_kind     TEXT NOT NULL CHECK (file_kind IN ('underwriting', 'claim', 'subject')),
    name          TEXT NOT NULL,                    -- 例如「個人壽險承保資料」
    UNIQUE (product, file_kind)
) STRICT;

-- 規則版本：一本填報手冊的一個版本；用手冊雜湊值確認依據沒被換掉
CREATE TABLE rule_set (
    id              INTEGER PRIMARY KEY,
    product         TEXT NOT NULL CHECK (product IN ('life', 'annuity', 'cancer', 'accident')),
    version_label   TEXT NOT NULL,                  -- 例如 life-2025
    manual_title    TEXT NOT NULL,
    manual_sha256   TEXT NOT NULL CHECK (length(manual_sha256) = 64 AND manual_sha256 NOT GLOB '*[^0-9a-f]*'),
    filing_year     INTEGER NOT NULL CHECK (filing_year BETWEEN 2000 AND 2100),
    created_at      TEXT NOT NULL CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*Z'),
    UNIQUE (product, version_label)
) STRICT;

-- 檢核規則（規則表）：手冊上的每一個檢核代碼一列。
-- 判斷邏輯由 handler 指向程式裡的實作，參數放 params，讓同一個實作能服務多條規則
-- （例如 ValidDate 同時服務 L1402「加保日期」與 L1602「退保日期」）。
CREATE TABLE rule (
    id              INTEGER PRIMARY KEY,
    rule_set_id     INTEGER NOT NULL REFERENCES rule_set (id) ON DELETE RESTRICT,
    code            TEXT NOT NULL,                  -- 手冊檢核代碼，例如 L1305
    dataset_type    TEXT NOT NULL REFERENCES dataset_type (code) ON DELETE RESTRICT,
    title           TEXT NOT NULL,
    scope           TEXT NOT NULL CHECK (scope IN ('single_record', 'multi_record', 'cross_file', 'cross_period')),
    severity        TEXT NOT NULL DEFAULT 'error' CHECK (severity IN ('error', 'warning')),
    handler         TEXT NOT NULL,                  -- 程式中的實作名稱，例如 EntryContinuesPreviousExit
    params          TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(params) AND json_type(params) = 'object'),
    manual_page     TEXT NOT NULL,                  -- 手冊頁碼或章節，讓每條規則都查得到出處
    UNIQUE (rule_set_id, code)
) STRICT;
CREATE INDEX idx_rule_set_dataset ON rule (rule_set_id, dataset_type);
CREATE INDEX idx_rule_dataset ON rule (dataset_type);

---------------------------------------------------------------------------
-- 2. 申報與版本
---------------------------------------------------------------------------

-- 一份申報：哪家公司、哪種檔案、哪個填報年度
CREATE TABLE report (
    id              TEXT PRIMARY KEY,               -- 對外 API 用的 ID（沿用 PR #2 的文字 ID）
    company_code    TEXT NOT NULL CHECK (length(company_code) = 2 AND company_code NOT GLOB '*[^0-9]*'),
    dataset_type    TEXT NOT NULL REFERENCES dataset_type (code) ON DELETE RESTRICT,
    filing_year     INTEGER NOT NULL CHECK (filing_year BETWEEN 2000 AND 2100),
    name            TEXT NOT NULL,
    created_at      TEXT NOT NULL CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*Z'),
    UNIQUE (company_code, dataset_type, filing_year)
) STRICT;
CREATE INDEX idx_report_dataset ON report (dataset_type);

-- 每次上傳是一個版本；原始檔與雜湊值一起保存，上傳後不可修改
CREATE TABLE version (
    id              TEXT PRIMARY KEY,
    report_id       TEXT NOT NULL REFERENCES report (id) ON DELETE RESTRICT,
    number          INTEGER NOT NULL CHECK (number >= 1),
    filename        TEXT NOT NULL,
    source_bytes    BLOB NOT NULL,
    source_sha256   TEXT NOT NULL CHECK (length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'),
    rule_set_id     INTEGER NOT NULL REFERENCES rule_set (id) ON DELETE RESTRICT,
    record_count    INTEGER NOT NULL CHECK (record_count >= 0),
    uploaded_by     TEXT NOT NULL,
    uploaded_at     TEXT NOT NULL CHECK (uploaded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*Z'),
    UNIQUE (report_id, number),
    UNIQUE (id, report_id)                          -- 給 issue、confirmation 的複合外鍵使用
) STRICT;
CREATE INDEX idx_version_rule_set ON version (rule_set_id);

-- 資料列：檔案裡的每一行。
-- 業務主鍵（公司代號＋保單編號＋保單編號序號＋異動序號）拆成欄位，因為規則與重複錯誤都靠它定位；
-- 其餘 50 多個欄位放在 fields（JSON），只有被查詢的欄位才拆出來。
CREATE TABLE record (
    id              INTEGER PRIMARY KEY,
    version_id      TEXT NOT NULL REFERENCES version (id) ON DELETE RESTRICT,
    line_no         INTEGER NOT NULL CHECK (line_no >= 1),
    company_code    TEXT NOT NULL,
    policy_no       TEXT NOT NULL,
    policy_seq      TEXT NOT NULL,
    txn_seq         TEXT NOT NULL,
    raw_line        TEXT NOT NULL,                  -- 原始定長文字，方便追查與重現
    fields          TEXT NOT NULL CHECK (json_valid(fields) AND json_type(fields) = 'object'),
    UNIQUE (version_id, line_no)
) STRICT;
-- 不設 UNIQUE：錯誤資料可能出現重複主鍵，那正是規則要抓的錯
CREATE INDEX idx_record_policy ON record (version_id, company_code, policy_no, policy_seq, txn_seq);

---------------------------------------------------------------------------
-- 3. 檢核結果
---------------------------------------------------------------------------

-- 一個檢核結果 = 一條規則在某版本抓到的一個錯。
-- issue_key 由「規則代碼＋每個出錯格子的（業務主鍵, 欄位）」排序後雜湊而成，
-- 不用列號，所以資料列順序改變時仍能比對出同一個錯。
-- repeat_status 在寫入時決定、之後不變（歷史不可修改，所以不會過期）：
--   new       之前所有版本都沒出現過
--   repeated  上一版也有
--   regressed 曾經出現、上一版已修好、這一版又出現
CREATE TABLE issue (
    id                    TEXT PRIMARY KEY,
    version_id            TEXT NOT NULL,
    report_id             TEXT NOT NULL,
    version_number        INTEGER NOT NULL,
    rule_id               INTEGER NOT NULL REFERENCES rule (id) ON DELETE RESTRICT,
    issue_key             TEXT NOT NULL CHECK (length(issue_key) = 64),
    message               TEXT NOT NULL,          -- 規則產生的固定說明（AI 失敗時顯示這段）
    facts                 TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(facts) AND json_type(facts) = 'object'),
    repeat_status         TEXT NOT NULL CHECK (repeat_status IN ('new', 'repeated', 'regressed')),
    first_seen_number     INTEGER NOT NULL CHECK (first_seen_number BETWEEN 1 AND version_number),
    created_at            TEXT NOT NULL CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*Z'),
    FOREIGN KEY (version_id, report_id) REFERENCES version (id, report_id) ON DELETE RESTRICT,
    UNIQUE (version_id, issue_key),
    CHECK ((repeat_status = 'new') = (first_seen_number = version_number))
) STRICT;
CREATE INDEX idx_issue_version_rule ON issue (version_id, rule_id);
CREATE INDEX idx_issue_history ON issue (report_id, issue_key, version_number);
CREATE INDEX idx_issue_rule ON issue (rule_id);

-- 一個錯可能牽涉好幾筆資料、好幾個欄位（例如 L1305 要比對同一保單的前後兩筆）
-- role = error：出錯的格子，修法只能改這些；role = context：只給 AI 參考，不能改
CREATE TABLE issue_cell (
    issue_id        TEXT NOT NULL REFERENCES issue (id) ON DELETE RESTRICT,
    record_id       INTEGER NOT NULL REFERENCES record (id) ON DELETE RESTRICT,
    field_name      TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('error', 'context')),
    PRIMARY KEY (issue_id, record_id, field_name)
) STRICT, WITHOUT ROWID;
CREATE INDEX idx_issue_cell_record ON issue_cell (record_id);

---------------------------------------------------------------------------
-- 4. AI 說明與修法建議
---------------------------------------------------------------------------

-- 一次 AI 審核：對一個錯產生的說明。可重跑，取最新一次顯示。
CREATE TABLE ai_review (
    id                  TEXT PRIMARY KEY,
    issue_id            TEXT NOT NULL REFERENCES issue (id) ON DELETE RESTRICT,
    model               TEXT NOT NULL,              -- 例如 gemini-3.5-flash；沒呼叫 AI 時寫 none
    source              TEXT NOT NULL CHECK (source IN ('ai', 'fallback_llm_error', 'fallback_number_guard')),
    title               TEXT NOT NULL,
    explanation         TEXT NOT NULL,
    blocked_numbers     TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(blocked_numbers) AND json_type(blocked_numbers) = 'array'),
    created_at          TEXT NOT NULL CHECK (created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*Z'),
    CHECK ((source = 'ai') OR (model <> ''))
) STRICT;
CREATE INDEX idx_ai_review_issue ON ai_review (issue_id, created_at);

-- AI 提出的每個修法候選，以及規則重驗的結果。
-- 只有 revalidation = 'passed' 的建議會顯示給使用者；其餘留在這裡供稽核。
CREATE TABLE suggestion (
    id                  INTEGER PRIMARY KEY,
    ai_review_id        TEXT NOT NULL REFERENCES ai_review (id) ON DELETE RESTRICT,
    rank                INTEGER NOT NULL CHECK (rank >= 1),
    reason              TEXT NOT NULL,
    revalidation        TEXT NOT NULL CHECK (revalidation IN ('passed', 'failed', 'invalid_target')),
    rejection_reason    TEXT,
    UNIQUE (ai_review_id, rank),
    CHECK ((revalidation = 'passed') = (rejection_reason IS NULL))
) STRICT;

-- 修法的每一處修改
CREATE TABLE suggestion_change (
    suggestion_id   INTEGER NOT NULL REFERENCES suggestion (id) ON DELETE RESTRICT,
    record_id       INTEGER NOT NULL REFERENCES record (id) ON DELETE RESTRICT,
    field_name      TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    PRIMARY KEY (suggestion_id, record_id, field_name)
) STRICT, WITHOUT ROWID;
CREATE INDEX idx_suggestion_change_record ON suggestion_change (record_id);

-- AI 說明引用的手冊段落（段落本身存在知識庫 JSONL，以手冊雜湊值綁定版本）
CREATE TABLE citation (
    ai_review_id    TEXT NOT NULL REFERENCES ai_review (id) ON DELETE RESTRICT,
    passage_id      TEXT NOT NULL,                  -- 知識庫段落編號，例如 K3
    PRIMARY KEY (ai_review_id, passage_id)
) STRICT, WITHOUT ROWID;

---------------------------------------------------------------------------
-- 5. 確認與稽核
---------------------------------------------------------------------------

-- 人工確認：只能確認某申報的最新版本，而且該版本不能有 error 等級的錯（由觸發器把關）
CREATE TABLE confirmation (
    id              TEXT PRIMARY KEY,
    report_id       TEXT NOT NULL,
    version_id      TEXT NOT NULL,
    confirmed_by    TEXT NOT NULL,
    source_sha256   TEXT NOT NULL CHECK (length(source_sha256) = 64),
    rule_set_id     INTEGER NOT NULL REFERENCES rule_set (id) ON DELETE RESTRICT,
    confirmed_at    TEXT NOT NULL CHECK (confirmed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*Z'),
    FOREIGN KEY (version_id, report_id) REFERENCES version (id, report_id) ON DELETE RESTRICT,
    UNIQUE (version_id)
) STRICT;
CREATE INDEX idx_confirmation_report ON confirmation (report_id, confirmed_at);

-- 稽核事件：只能新增。每筆存上一筆的雜湊（prev_hash），形成鏈；
-- 任何一筆被改，後面的雜湊就對不上。雜湊由程式計算：sha256(prev_hash ‖ 事件內容的正規化 JSON)。
CREATE TABLE audit_event (
    id              INTEGER PRIMARY KEY,
    occurred_at     TEXT NOT NULL CHECK (occurred_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*Z'),
    actor           TEXT NOT NULL,                  -- 使用者或 system
    event_type      TEXT NOT NULL CHECK (event_type IN (
                        'version_uploaded', 'validation_completed', 'ai_review_completed',
                        'suggestion_rejected', 'confirmation_recorded', 'rule_set_loaded')),
    version_id      TEXT REFERENCES version (id) ON DELETE RESTRICT,
    issue_id        TEXT REFERENCES issue (id) ON DELETE RESTRICT,
    payload         TEXT NOT NULL CHECK (json_valid(payload) AND json_type(payload) = 'object'),
    prev_hash       TEXT NOT NULL UNIQUE CHECK (length(prev_hash) = 64),   -- 第一筆用 64 個 0
    hash            TEXT NOT NULL UNIQUE CHECK (length(hash) = 64)
) STRICT;
CREATE INDEX idx_audit_version ON audit_event (version_id, id);
CREATE INDEX idx_audit_issue ON audit_event (issue_id);

---------------------------------------------------------------------------
-- 6. 觸發器：把「不可修改」和「確認條件」放進資料庫，不只靠程式
---------------------------------------------------------------------------

-- 歷史不可修改：版本、資料列、檢核結果、AI 審核、建議、確認、稽核事件都不能改或刪
CREATE TRIGGER trg_version_no_update BEFORE UPDATE ON version
BEGIN SELECT RAISE(ABORT, 'version is immutable'); END;
CREATE TRIGGER trg_version_no_delete BEFORE DELETE ON version
BEGIN SELECT RAISE(ABORT, 'version is immutable'); END;
CREATE TRIGGER trg_record_no_update BEFORE UPDATE ON record
BEGIN SELECT RAISE(ABORT, 'record is immutable'); END;
CREATE TRIGGER trg_record_no_delete BEFORE DELETE ON record
BEGIN SELECT RAISE(ABORT, 'record is immutable'); END;
CREATE TRIGGER trg_issue_no_update BEFORE UPDATE ON issue
BEGIN SELECT RAISE(ABORT, 'issue is immutable'); END;
CREATE TRIGGER trg_issue_no_delete BEFORE DELETE ON issue
BEGIN SELECT RAISE(ABORT, 'issue is immutable'); END;
CREATE TRIGGER trg_ai_review_no_update BEFORE UPDATE ON ai_review
BEGIN SELECT RAISE(ABORT, 'ai_review is immutable'); END;
CREATE TRIGGER trg_suggestion_no_update BEFORE UPDATE ON suggestion
BEGIN SELECT RAISE(ABORT, 'suggestion is immutable'); END;
CREATE TRIGGER trg_confirmation_no_update BEFORE UPDATE ON confirmation
BEGIN SELECT RAISE(ABORT, 'confirmation is immutable'); END;
CREATE TRIGGER trg_confirmation_no_delete BEFORE DELETE ON confirmation
BEGIN SELECT RAISE(ABORT, 'confirmation is immutable'); END;
CREATE TRIGGER trg_audit_no_update BEFORE UPDATE ON audit_event
BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END;
CREATE TRIGGER trg_audit_no_delete BEFORE DELETE ON audit_event
BEGIN SELECT RAISE(ABORT, 'audit_event is append-only'); END;

-- 版本號必須連續（下一版 = 目前最大版號 + 1）
CREATE TRIGGER trg_version_number_sequence BEFORE INSERT ON version
WHEN NEW.number <> COALESCE((SELECT max(number) FROM version WHERE report_id = NEW.report_id), 0) + 1
BEGIN SELECT RAISE(ABORT, 'version number must be previous max + 1'); END;

-- 檢核結果的版號必須等於所屬版本的版號，規則必須屬於該版本使用的規則版本
CREATE TRIGGER trg_issue_consistency BEFORE INSERT ON issue
WHEN NEW.version_number <> (SELECT number FROM version WHERE id = NEW.version_id)
  OR (SELECT rule_set_id FROM rule WHERE id = NEW.rule_id)
     <> (SELECT rule_set_id FROM version WHERE id = NEW.version_id)
BEGIN SELECT RAISE(ABORT, 'issue does not match its version or rule set'); END;

-- 重複錯誤的判定必須跟歷史一致：
--   repeated  ⇔ 上一版有同一個 issue_key
--   regressed ⇔ 上一版沒有、但更早的版本有
--   new       ⇔ 更早的版本都沒有
-- first_seen_number 必須是這個 issue_key 最早出現的版號
CREATE TRIGGER trg_issue_repeat_status BEFORE INSERT ON issue
WHEN NEW.repeat_status <> CASE
        WHEN EXISTS (SELECT 1 FROM issue p WHERE p.report_id = NEW.report_id
                     AND p.issue_key = NEW.issue_key AND p.version_number = NEW.version_number - 1)
            THEN 'repeated'
        WHEN EXISTS (SELECT 1 FROM issue p WHERE p.report_id = NEW.report_id
                     AND p.issue_key = NEW.issue_key AND p.version_number < NEW.version_number - 1)
            THEN 'regressed'
        ELSE 'new' END
  OR NEW.first_seen_number <> COALESCE(
        (SELECT min(p.version_number) FROM issue p WHERE p.report_id = NEW.report_id
         AND p.issue_key = NEW.issue_key AND p.version_number < NEW.version_number),
        NEW.version_number)
BEGIN SELECT RAISE(ABORT, 'repeat_status or first_seen_number does not match history'); END;

-- 檢核結果牽涉的資料列必須屬於同一個版本
CREATE TRIGGER trg_issue_cell_same_version BEFORE INSERT ON issue_cell
WHEN (SELECT version_id FROM record WHERE id = NEW.record_id)
     <> (SELECT version_id FROM issue WHERE id = NEW.issue_id)
BEGIN SELECT RAISE(ABORT, 'issue_cell record belongs to another version'); END;

-- 確認：必須是最新版本、沒有 error 等級的錯、雜湊值與規則版本要跟版本一致
CREATE TRIGGER trg_confirmation_rules BEFORE INSERT ON confirmation
BEGIN
    SELECT RAISE(ABORT, 'only the latest version can be confirmed')
    WHERE (SELECT number FROM version WHERE id = NEW.version_id)
          <> (SELECT max(number) FROM version WHERE report_id = NEW.report_id);
    SELECT RAISE(ABORT, 'version still has error-level issues')
    WHERE EXISTS (
        SELECT 1 FROM issue i JOIN rule r ON r.id = i.rule_id
        WHERE i.version_id = NEW.version_id AND r.severity = 'error');
    SELECT RAISE(ABORT, 'confirmation does not match the version source or rule set')
    WHERE NEW.source_sha256 <> (SELECT source_sha256 FROM version WHERE id = NEW.version_id)
       OR NEW.rule_set_id <> (SELECT rule_set_id FROM version WHERE id = NEW.version_id);
END;
