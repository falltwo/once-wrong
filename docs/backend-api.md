# 後端 API 契約

2026-10-29：依 AI 審核規格統一後端端點。AI 模組引入自 `feat/ai-review` 的 `ea44b2f`；本機整合的 import 採原文件暫定的 `once_wrong_ai`，pip distribution 保留上游的 `once-wrong`。後端保留 import `once_wrong`、distribution `once-wrong-backend`。命名分工與避免重複改名見 [AI 套件交接](ai-package-handoff.md)；宥勳的遠端分支未由本次工作修改。安裝與環境設定見 [後端 README](../backend/README.md)，驗證結果見 [AI API 整合驗收](ai-integration-acceptance.md)。

## 端點

| 方法與路徑 | 回傳 | 行為 |
| --- | --- | --- |
| `GET /health` | 200 | 服務狀態、demo profile／rule version、AI 設定狀態 |
| `GET /reports` | 200 `Report[]` | 報表與所有版本 |
| `POST /reports` | 201 `Report` | multipart `name`、`period`，及 `file` 或重複的 `files`；同一交易建立報表與第一版 |
| `GET /reports/{reportId}` | 200 `Report` | 版本按 `number` 升冪；未知 ID 回 404 |
| `POST /reports/{reportId}/versions` | 201 `Version` | multipart `file` 或重複 `files`；整批同步解析及保存 |
| `GET /versions/{versionId}/source` | 200 原始 bytes | `X-Source-SHA256` 提供來源雜湊 |
| `GET /versions/{versionId}/files/{fileId}/source` | 200 原始 bytes | 多檔版本指定來源，檔案須屬於該版本 |
| `GET /versions/{versionId}/issues/{issueId}/suggestion` | 200 `SuggestionResponse` | 使用者點開時才呼叫 AI；伺服器重跑規則、候選副本重驗、保存可重用結果 |
| `GET /evaluations/latest` | 200 JSON | 保留評分內容，另附評測模型與目前模型的 `evaluationContext`；檔案不存在回 404 |
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
| `life_filing_v1` | `files` 提供同次申報的承保／給付／填報對象 CSV，最多每種一份 | `life_filing_rules_v1`；11 條承保、D1001 與已核對的 LD 匹配，其他規則明列未評估 |

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

`repeated=true` 表示緊鄰前一版相同 profile 也有同一錯誤。demo 沿用資料自己的 ID；壽險改以 `issueKey` 比較，`id`／`rowId` 仍只負責版本內定位。`issueKey` 對檔種、規則及排序去重的「業務鍵＋欄位」配對做正規化 JSON 與 SHA-256，不包含列號。一般規則使用 `公司代號＋保單編號＋保單編號序號＋異動序號＋加保日期`；若出錯格子涉及主鍵欄位，改用前三欄的保單群組鍵，避免修改仍然非法的序號或日期後躲過重複判定。同一保單群組的數個錯誤位置可以共享 `issueKey`，版本內 `id` 仍各自不同。

舊版未提供 `issueKey` 時，啟動遷移用當時保存的 issues 與 rows 回算，正規化後保留舊 JSON 與 bytes，不重跑今天的規則來定義歷史。每個 issue 另有 `repeatStatus=new/repeated/regressed`、`firstSeenNumber`，非首次時有 `prevSeenNumber`，復發時有 `fixedInNumber=prevSeenNumber+1`。`repeated` 布林僅在連續重複時為 true；復發另外標示。完整歷史在相同 profile 的連續區段內比對，跨 profile 會重置區段，避免把未評估的中間版當作已修好。資料庫 trigger 再驗證此狀態與歷史一致。`Report.canSubmit` 由後端以最新版、規則版本、未評估數及實際重驗結果推導。[實作及遷移](database-implementation.md)

## 同次申報的多檔版本

使用重複的 multipart `files` 欄位，不能同時提供 `file`。每檔仍限 2 MiB／1,000 筆，最多三種檔種各一份；單檔 `file` 保持原 Demo／八欄壽險相容。多檔年度以 report.period 的年份核對，不能混公司或年度。同一公司、險種及年度只能有一份分組 report，重複建立回 409 `REPORT_ALREADY_EXISTS`，details.reportId 指向應新增修訂的報表。

多檔 Version 提供 `files=[{id,datasetType,filename,sourceSha256,columns,rows,prototype,eventDateColumn?}]`，top rows 為所有檔案資料。row.id／issue.rowIds／contextRowIds 使用 `fileId:列號`；cells 與建議 changes 另帶 `fileId`、`datasetType`。業務 issueKey 不含隨上傳改變的 fileId。原始檔逐檔保存，`manifestSha256` 與 version.sourceSha256 是排序後 `[[datasetType,sourceSha256],...]` 的精簡 UTF-8 JSON 雜湊，不含 UUID 或檔名。多檔呼叫舊 source 路徑回 409 `FILE_ID_REQUIRED`，請指定 fileId。

CSV 是本原型的交換格式，未實作完整官方定長檔案及所有規則。`evidence` 提供 `executedRuleIds`、`notEvaluated` 原因與來源；`summary.notEvaluatedChecks` 計入缺檔與未支援的規則家庭。即使目前已檢規則沒有錯誤，也不能把此多檔原型確認為官方完整申報通過。空的給付／對象 CSV（有合法表頭）與缺少檔案是不同狀態。

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

建議依伺服器保存的版本重新建立 Report 與 violations，不信任客戶端錯誤。候選只能修改該 violation 的 `cells` 明確指定的格子；同列其他欄位及純參考列均不可改，未提供 cells 時拒絕可執行修法。候選仍須在副本上重跑全部規則，不得留下原錯誤或產生新錯誤。只在建議端點被查詢時呼叫 AI；每個 app 共用 LLM／知識庫，並為每個 profile 建立 reviewer。同步 AI 呼叫以 `run_in_threadpool` 執行；Gemini SDK 與 OpenRouter HTTP client 設定 30 秒網路 timeout，Gemini 不自動重試。

SQLite `suggestions` 以 `(version_id, issue_id)` 為主鍵保存 `source=ai` 的結果，重啟可重用。`fallback_llm_error` 與 `fallback_number_guard` 均不快取，下次查詢可重試；重試仍由使用者查詢觸發，不自動循環呼叫模型。新增 `cache_revision` 辨識格子驗證政策，舊快取保留但不會被回傳，新審核完成後可替換該快取。同一 worker 中，同一問題的並發查詢會序列化以重用快取，請求結束後釋放鎖；多 worker 不保證只呼叫一次模型。AI 不會直接改寫版本資料。

版本或問題不存在分別回 404 `VERSION_NOT_FOUND / ISSUE_NOT_FOUND`。AI 呼叫失敗、逾時、缺少金鑰或選用資料載入失敗時回固定說明，不將 AI 失敗變成 5xx。

## 健康檢查與評分

```json
{
  "status": "ok", "schemaProfileId": "demo_csv_v1", "ruleVersion": "demo_rules_v1",
  "ai": {"configured": true, "model": "gemini-3.5-flash", "knowledgeBase": false}
}
```

`ai.configured` 表示 client 已設定並成功建立，不是即時模型服務探測；`knowledgeBase` 表示已載入可用手冊段落。沒有知識庫仍可說明，引用可能為空。demo 的 R-01／R-07 在手冊中沒有對應規則。

`GET /evaluations/latest` 保留 `ONCE_WRONG_EVALUATION` 指定的 JSON 內容，不重算指標，另附 `evaluationContext={evaluatedModel,runtimeModel,runtimeConfigured,modelMatchesRuntime,displayNotice}`，並設定 `Cache-Control: no-store`。預設為 [2026-10-28 的 Gemini 結果](evaluation/2026-10-28-gemini-3.5-flash.json)，是宥勳 AI 分支已有的實測快照，並非本次 API 整合產生的新實測。前端須在分數旁標示 `evaluatedModel`，並顯示 `displayNotice`。模型不同時不可把舊評分說成目前模型的表現；即使模型名稱相同，也不代表目前程式及格子驗證政策已重測。它評估「規則抓到錯誤後，AI 說明和修法是否正確」，不能當作抓錯 precision／recall。詳細呈現要求見 [評測來源說明](evaluation/README.md)。

評分檔不存在回 404 `EVALUATION_NOT_FOUND`，檔案無法讀取、JSON 不合法或缺少有效模型名稱回 500 `EVALUATION_INVALID`。`ONCE_WRONG_KB`、`ONCE_WRONG_RULE_MEMORY`、`ONCE_WRONG_EVALUATION` 若為相對路徑，均以 repo 根目錄解析，從 backend 或根目錄啟動結果相同。

## 錯誤、持久化與前端交接

錯誤格式為頂層 `{code, message, details?}`：404 為資源不存在，413 為檔案過大，422 為輸入格式不合法，409 為過期版本或未通過確認條件。

SQLite 版本號有 `(report_id, number)` 唯一約束，原始版本不可由 API 改寫。確認會重跑規則，只接受最新版；同版重試回 204，之後上傳會清除目前確認指標並保留確認歷史。`submissions` 只保存內部確認，不向外申報。

本機已整合 PR #1 的前端並完成任意欄位、三態歷史、多檔範圍與來源下載、模型評分來源顯示。使用 `rows[].values`、`columns`、`issues[].cells`／`facts`，以 qualified rowId 對應各檔資料。未評估原因與 disabled 確認會明確呈現；不把未完整檢核的列標示為通過。見[前端整合](frontend-local-integration.md)與[瀏覽器驗收](frontend-browser-acceptance.md)。

後端啟動會在首次正規化前備份既有 SQLite，再增建資料表與回填證據；舊四表、JSON、bytes 和確認紀錄保留。版本、records、issues 與 audit 由資料庫禁止修改／刪除，規則從資料表白名單 handler 載入。AI 僅送出必要欄位與保單代碼化識別；完整 prompt 不保留在共用 reviewer 記憶體。所有候選的 rank、passed／failed／invalid_target、原始嘗試、引用快照與 fallback 審核會保存，fallback 仍不進快取。多檔候選另重驗整組資料，改選後續候選時重做數字防護。[資料庫實作](database-implementation.md)
