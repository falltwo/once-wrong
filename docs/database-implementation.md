# 資料庫與多檔版本實作

2026-10-29。以 #6 的套件整合為基礎，將 #5 的儲存設計接入現有 API。所有變更保留本機，未推送或修改 PR。

## 已接入的資料

原 `reports / versions / confirmations / suggestions` 保留，相容舊端點與快取。另建 `dataset_type / rule_set / rule / version_state / version_file / record / issue / issue_cell / issue_context / ai_review / suggestion / suggestion_change / citation / audit_event`。`version_state` 封存前核對檔案、列、錯誤數及 manifest；封存後禁止追加或改寫版本證據。

規則 handler 與 params 由 catalog 載入，僅接受程式白名單，不執行資料庫中的任意 Python。Demo 2 條、八欄壽險 11 條維持同一規則來源；多檔另登錄已覆核的 D1001、30301_LD012、30307_LD013。規則頁碼未精確定位時保留章節與規則代碼，不捏造頁碼。

多檔 report 按公司＋險種＋填報年度唯一分組。險種是 life 等領域，不是商業商品代碼。每次新增版本保存完整檔案組，record 主鍵由自己的 version_file.dataset_type 決定：承保五欄、給付四欄、填報對象五欄依手冊順序取值；所有 fields 值保留原始文字。原檔 bytes 與各自 SHA-256 保留，整組再算排序後的 manifest hash。

## 歷史與確認

issueKey 使用規則、檔種與業務鍵／欄位配對，不含列號或 file UUID。涉及主鍵本身的錯誤改以保單群組辨識。API 的 id／rowId 供版本內定位；同一群組的多處錯誤可共享業務 key。

狀態為 new、repeated、regressed；保留 firstSeenNumber、prevSeenNumber，復發時提供 fixedInNumber。完整歷史以相同 profile 的連續區段比對，換成另一 profile 的版本不當作已修復。資料庫會拒絕不符合歷史的版號與狀態、跨版本 cells／context、非連續版本、錯誤主鍵及封存後修改。

確認只接受最新版、無 error、沒有未評估項目、目前規則版本及來源／manifest hash 一致的版本。每次確認仍在後端重驗，僅記錄內部確認。多檔原型因未覆蓋完整官方規則，會明確拒絕確認，不冒稱可對外申報。

## AI 證據與資料最小化

出站報表只帶必要規則欄位，保單識別改為一致代碼；姓名、身分證、生日等多餘欄位不進模型 prompt。原始檔與原 fields 保留在本機資料庫以重現來源。共享 reviewer 不再累積完整 prompt／模型原始物件；持久化只寫結構化審核證據。

每個候選按原 rank 保存 passed／failed／invalid_target、raw 嘗試、拒絕理由與修改；第二個以後通過的候選也保留。無效目標與重複格子不能使 API 失敗。多檔候選會重跑整組檢查，若修法造成新的跨檔錯誤則拒絕，改選後續候選時再次檢查理由數字。引用保存 Passage.id 及手冊名稱／章節／頁碼快照。所有 fallback 審核留痕，但不進成功快取。

每筆 audit_event 延伸前一筆 hash，prev_hash 唯一且鏈不可分岔；資料庫會拒絕錯誤雜湊或修改／刪除。

原始 SQLite 與備份目前仍保存明文來源，這不等於完成正式環境的個資加密政策。正式資料投入前，須由團隊確定 at-rest 加密、備份權限與保留期限；原型驗證只用合成資料。

## 舊資料遷移與回復

第一次正規化前，使用 SQLite backup 在資料庫同層 backups/ 建立 `<stem>.pre-normalized-<timestamp>.sqlite3`。接著加法建表，於 BEGIN IMMEDIATE 中依原版本順序回填正規化證據，不重跑今天的規則改寫舊 findings，也不刪舊 JSON、bytes、確認紀錄或原表。API 讀取時用 normalized 歷史補上三態欄位。

遷移失敗時回填交易回滾，備份保留。回復時先停止所有使用該 DB 的服務，再把完整備份還原到新的資料庫路徑，以 ONCE_WRONG_DB 指向該路徑；不要在服務仍開啟時只替換 SQLite 主檔而遺漏 WAL。這次沒有自動刪除舊表，也沒有操作使用者既有資料庫的還原。

## 原型覆蓋

多檔 CSV 接受已核對的必要欄位子集及保留的其他文字欄位，尚不是官方完整定長格式。跨檔關聯依公司／保單／序號與事故日期核對，發生日期、事故日期、死亡完全失能日期使用明確別名且不能同時混用。缺檔、其他事件種類與未實作官方規則均列在 evidence.notEvaluated，畫面提供原因。

目前每檔 1,000 筆／2 MiB、最多三檔，未設版本數保留上限；真實申報量仍未知。提高限制前應連同列表分頁、歷史讀取與負載一起驗證，不能把設計假設當成已證實需求。
