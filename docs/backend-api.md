# 後端 API 契約

2026-10-29：依 AI 審核規格統一後端端點。AI 模組引入自 `feat/ai-review` 的 `ea44b2f`；本機整合的 import 採原文件暫定的 `once_wrong_ai`，pip distribution 保留上游的 `once-wrong`。後端保留 import `once_wrong`、distribution `once-wrong-backend`。命名分工與避免重複改名見 [AI 套件交接](ai-package-handoff.md)；宥勳的遠端分支未由本次工作修改。安裝與環境設定見 [後端 README](../backend/README.md)，驗證結果見 [AI API 整合驗收](ai-integration-acceptance.md)。

## 端點

| 方法與路徑 | 回傳 | 行為 |
| --- | --- | --- |
| `GET /health` | 200 | 服務狀態、demo profile／rule version、AI 設定狀態 |
| `GET /reports` | 200 `Report[]` | 報表與所有版本 |
| `POST /reports` | 201 `Report` | multipart `name`、`period`、`file`；同一交易建立報表與第一版 |
| `GET /reports/{reportId}` | 200 `Report` | 版本按 `number` 升冪；未知 ID 回 404 |
| `POST /reports/{reportId}/versions` | 201 `Version` | multipart `file`；同步解析、套用 profile 規則、保存後回傳 |
| `GET /versions/{versionId}/source` | 200 原始 bytes | `X-Source-SHA256` 提供來源雜湊 |
| `GET /versions/{versionId}/issues/{issueId}/suggestion` | 200 `SuggestionResponse` | 使用者點開時才呼叫 AI；伺服器重跑規則、候選副本重驗、保存可重用結果 |
| `GET /evaluations/latest` | 200 JSON | 原樣回傳設定的 AI 審核評分 JSON；檔案不存在回 404 |
| `POST /reports/{reportId}/submissions` | 204 | JSON `{versionId}`；交易內重查最新版並重跑規則，保存內部確認 |

路徑 ID 須 URL encode，包含 issue ID 中的冒號。上傳不接受前端提供的 issues、expected、repeated 或 canSubmit 作為判定依據；確認 body 不接受額外欄位。

`POST /reports` 的 `name` 去除前後空白後須為 1–200 字，`period` 須為 `YYYY-MM`，月份限 01–12。名稱、期間、檔案或 CSV 不合法時不留下空報表或半成品版本。成功回傳包含第一版的完整 `Report`。

```powershell
# 以下指令在 repo 根目錄執行。
curl.exe -F "name=壽險承保報表" -F "period=2025-10" `
  -F "file=@examples/mock_life_policies_2025.csv" http://127.0.0.1:8000/reports

curl.exe -F "file=@backend/tests/fixtures/sample-errors.csv" `
  http://127.0.0.1:8000/reports/reserve-202609/versions
```

## CSV profile 與版本

兩種 CSV 均接受 UTF-8（可含 BOM）、上限 2 MiB、1–1,000 筆非空資料。原始檔 bytes、SHA-256、版本與檢核結果在同一交易保存。結構錯誤回 422；業務規則未通過仍建立版本，供畫面定位與修正。

| profile | 辨識／型別 | 規則 |
| --- | --- | --- |
| `demo_csv_v1` | 包含 `id,product,previous,opening`；ID 非空且唯一，金額是非負安全整數 | `demo_rules_v1`，R-01、R-07 兩條團隊示範規則 |
| `life_underwriting_v1` | 表頭恰為下列 8 欄，次序可不同；所有資料值保留文字 | `life_field_rules_v1`，`life_field_rules()` 的 11 條壽險承保規則 |

壽險欄位：`公司代號,保單編號,保單編號序號,異動序號,加保別,加保日期,退保別,退保日期`。公司代號 `01`、序號 `00001`、日期 `00000000` 均不得轉成數字。壽險的 `rowId` 是從 1 開始的資料列號字串，並非 CSV 檔案實體行號。

所有 `Version` 均有 `id / number / filename / createdAt / rows / issues / schemaProfileId / ruleVersion / validationStatus / validationRunId / sourceSha256 / summary`。`validationStatus=completed` 只表示檢查完成。

demo 的 rows、issues 保留原本形狀，且不新增 columns：

```json
{
  "rows": [{"id": "POL-003", "product": "ML-05", "previous": 12480000, "opening": 12005000}],
  "issues": [{"id": "POL-003:R-07", "ruleId": "R-07", "rowId": "POL-003", "field": "opening", "title": "期初與上期末金額不一致", "actual": 12005000, "expected": 12480000, "repeated": false}]
}
```

壽險版本另提供 `columns`，保留來源表頭順序。rows 為 `{id, row, values}`，issues 使用 `once_wrong_ai.ai_review.api.IssueResponse`：

```json
{
  "id": "6:L0303", "ruleId": "L0303",
  "title": "第 6 列是這張保單的第一筆異動（00001），退保別不可以填 DEA。",
  "rows": [6], "rowIds": ["6"],
  "cells": [
    {"row": 6, "rowId": "6", "column": "異動序號", "value": "00001"},
    {"row": 6, "rowId": "6", "column": "退保別", "value": "DEA"}
  ],
  "facts": {"退保別": "DEA"}, "contextRowIds": ["7"], "repeated": false
}
```

`summary` 固定為 `{totalChecks, passedChecks, failedChecks, notEvaluatedChecks}`。檢查數按「每條規則對每列的一次評估」計算：demo 為列數 × 2，壽險為列數 × 11；壽險多列問題按不同 `(ruleId, row)` 計失敗，重複的同規則同列不重算。因此問題筆數可能少於 failedChecks。

`repeated=true` 表示緊鄰前一版相同 profile 也有同一 issue ID。跨 profile 不沿用 repeated。`Report.canSubmit` 由後端以最新版、目前支援的規則版本及實際重驗結果推導。

## AI 建議

直接使用 `once_wrong_ai.ai_review.api.SuggestionResponse`，每次均回傳全部欄位。無金鑰或呼叫失敗時仍回 200，例如：

```json
{
  "title": "R-01 未通過",
  "explanation": "第 4 列的「product」是空白，必須填寫。",
  "suggestion": null,
  "rejectedSuggestions": [],
  "citations": [],
  "blockedNumbers": [],
  "model": "gemini-3.5-flash",
  "verification": "unavailable",
  "source": "fallback_llm_error"
}
```

`source` 僅為 `ai / fallback_llm_error / fallback_number_guard`。有通過規則重驗與 profile 型別檢查的候選時，`suggestion={reason, verification:"passed", changes:[{rowId,row,column,value}]}` 且頂層 `verification=passed`；否則 suggestion 為 null、verification 為 unavailable。規則通過仍不代表候選一定符合來源事實，資料由使用者確認後修改。

建議依伺服器保存的版本重新建立 Report 與 violations，不信任客戶端錯誤。只在建議端點被查詢時呼叫 AI；每個 app 共用 LLM／知識庫，並為每個 profile 建立 reviewer。同步 AI 呼叫以 `run_in_threadpool` 執行；Gemini SDK 與 OpenRouter HTTP client 設定 30 秒網路 timeout，Gemini 不自動重試。

SQLite `suggestions` 以 `(version_id, issue_id)` 為主鍵保存結果，重啟可重用。`fallback_llm_error` 不保存，下次查詢可重試。`fallback_number_guard` 可保存。同一 worker 中，同一問題的並發查詢會序列化以重用快取；多 worker 不保證只呼叫一次模型。AI 不會直接改寫版本資料。

版本或問題不存在分別回 404 `VERSION_NOT_FOUND / ISSUE_NOT_FOUND`。AI 呼叫失敗、逾時、缺少金鑰或選用資料載入失敗時回固定說明，不將 AI 失敗變成 5xx。

## 健康檢查與評分

```json
{
  "status": "ok", "schemaProfileId": "demo_csv_v1", "ruleVersion": "demo_rules_v1",
  "ai": {"configured": true, "model": "gemini-3.5-flash", "knowledgeBase": false}
}
```

`ai.configured` 表示 client 已設定並成功建立，不是即時模型服務探測；`knowledgeBase` 表示已載入可用手冊段落。沒有知識庫仍可說明，引用可能為空。demo 的 R-01／R-07 在手冊中沒有對應規則。

`GET /evaluations/latest` 直接回傳 `ONCE_WRONG_EVALUATION` 指定的 JSON，不重算指標。預設為 [2026-10-28 的 Gemini 結果](evaluation/2026-10-28-gemini-3.5-flash.json)，是宥勳 AI 分支已有的實測快照，並非本次 API 整合產生的新實測。它評估「規則抓到錯誤後，AI 說明和修法是否正確」，不能當作抓錯 precision／recall。

評分檔不存在回 404 `EVALUATION_NOT_FOUND`，檔案無法讀取或 JSON 不合法回 500 `EVALUATION_INVALID`。`ONCE_WRONG_KB`、`ONCE_WRONG_RULE_MEMORY`、`ONCE_WRONG_EVALUATION` 若為相對路徑，均以 repo 根目錄解析，從 backend 或根目錄啟動結果相同。

## 錯誤、持久化與前端交接

錯誤格式為頂層 `{code, message, details?}`：404 為資源不存在，413 為檔案過大，422 為輸入格式不合法，409 為過期版本或未通過確認條件。

SQLite 版本號有 `(report_id, number)` 唯一約束，原始版本不可由 API 改寫。確認會重跑規則，只接受最新版；同版重試回 204，之後上傳會清除目前確認指標並保留確認歷史。`submissions` 只保存內部確認，不向外申報。

前端 `Suggestion` 已與本回應格式一致，`reportsApi.create()` 的 multipart 需求也已補齊。前端分支的資料表與錯誤詳情仍使用 demo 欄位；要顯示壽險，須改讀 `rows[].values`、`columns`、`issues[].cells`／`facts`，用 rowIds／contextRowIds 對應列，並獨立呈現「AI 審核評分」。本次不宣稱已完成壽險前端畫面。
