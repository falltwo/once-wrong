# 後端 API 契約

本版為`demo_csv_v1`，R-01/R-07是團隊示範規則。API回傳後端實際保存及計算的結果；不是官方完整規則或AI實驗成績。

## 端點

| 方法與路徑 | 回傳 | 行為 |
| --- | --- | --- |
| `GET /health` | 200 | 服務狀態、profile與rule version |
| `GET /reports` | 200 `Report[]` | 報表及版本，供目前原型使用 |
| `GET /reports/{reportId}` | 200 `Report` | 版本按number升冪；未知ID為404 |
| `POST /reports` | 201 `Report` | multipart欄位`name`、`period`（YYYY-MM）、`file`；建立報表及第1版，同一交易寫入 |
| `POST /reports/{reportId}/versions` | 201 `Version` | multipart欄位file；同步解析、檢核、保存 |
| `GET /versions/{versionId}/source` | 200 原始bytes | SHA-256在`X-Source-SHA256`；不將檔名當伺服器檔案路徑 |
| `GET /versions/{versionId}/issues/{issueId}/suggestion` | 200 `Suggestion` | 只審查指定錯誤；Gemini 可用時回傳 AI 說明、引用及經規則重驗的修法，否則回傳固定說明 |
| `POST /reports/{reportId}/submissions` | 204 | JSON `{versionId}`；僅內部確認，交易內重查最新版並重跑規則 |

路徑ID須URL encode，包含Issue中的冒號。伺服器不使用客戶端的issues、expected、repeated或canSubmit來判定；確認body不接受額外欄位。

上傳範例（curl）：

```sh
curl -F 'name=準備金月報' -F 'period=2026-10' \
  -F 'file=@backend/tests/fixtures/sample-errors.csv' \
  http://127.0.0.1:8000/reports

curl -F 'file=@backend/tests/fixtures/sample-errors.csv' \
  http://127.0.0.1:8000/reports/reserve-202609/versions
```

PowerShell可在根目錄使用`curl.exe -F "file=@backend/tests/fixtures/sample-errors.csv" http://127.0.0.1:8000/reports/reserve-202609/versions`。

## 回傳形狀

既有DataRow/Issue欄位對齊前端PR #1。Version加上：

```text
schemaProfileId: demo_csv_v1
ruleVersion: demo_rules_v1
validationStatus: completed
validationRunId: 本次保存的檢核識別碼
sourceSha256: 原始CSV bytes的SHA-256
summary: {totalChecks, passedChecks, failedChecks, notEvaluatedChecks}
```

這裡的檢查數是「規則對資料列的一次評估」。本版每列套兩條規則，`totalChecks`是實際評估數，並非已實作規則定義數。任務completed不表示資料通過。

Report提供後端計算的`canSubmit`，以及可選`submittedVersionId`。前端仍須確認使用者所選版本是最新，不能將歷史版本顯示成可確認。內部確認會再次檢核，不信任瀏覽器按鈕狀態。

Suggestion提供`title / explanation / source / verification / suggestion / rejectedSuggestions / citations / blockedNumbers / model`。修法只會在副本重跑整組示範規則、原錯消失且沒有新增錯誤時回`verification=passed`。AI 或數字守門失敗時使用固定說明；沒有設定 Gemini 金鑰不會宣稱 AI 建議成功。引用只有在本機知識庫存在且模型確實引用已檢索段落時回傳。

## 錯誤

統一頂層格式：`{code, message, details?}`。

| HTTP | 類型 |
| --- | --- |
| 404 | report、version或issue不存在 |
| 413 | 原始檔超過2 MiB |
| 422 | 檔種、UTF-8、CSV結構、欄位、ID、數字、筆數或請求body不合法 |
| 409 | 確認不是最新版本、版本不符合完成條件或儲存資料檢核不一致 |

非法上傳不產生可見成功報表或版本。建立報表與第一版在同一SQLite交易中提交，CSV檢核失敗會一併回滾。UI將message顯示給使用者，可用details定位輸入問題；系統錯誤不得偽裝為通過。

## 持久化與確認

SQLite交易同時儲存原檔BLOB、SHA-256、版本、規則版本、資料列與Findings；`(report_id, number)`唯一，並發上傳依交易序列化產生版本號。舊版不可透過API改寫。

同一已確認最新版本再次確認回204，不重複新增確認紀錄。新上傳會清除當前submittedVersionId，但獨立的確認歷史仍保留。原始版本與確認歷史不是同一種資料。

本版不提供正式身份驗證或對外申報。官方TXT profile、NOT_EVALUATED等完整領域狀態仍待後續實作；AI 目前只使用 R-01/R-07 示範規則做候選副本重驗。資料庫payload與profile metadata保留擴充邊界。
