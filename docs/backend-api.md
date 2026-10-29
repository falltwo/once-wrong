# 前端使用的後端 API 契約

本文件依據後端整合 PR #6 的 `docs/backend-api.md`，記錄前端目前使用的 request 和 response 格式。後端是資料與檢核結果的唯一來源；前端不自行重算 issue 或 `canSubmit`。

## 使用端點

| 方法與路徑 | 前端用途 |
| --- | --- |
| `GET /health` | 顯示目前 profile、規則版本與 AI 設定 |
| `GET /reports` | 報表列表、測試結果頁的最新版本檢核摘要 |
| `GET /reports/{reportId}` | 讀取報表全部版本及其檢核資料 |
| `POST /reports` | multipart `name`、`period`（`YYYY-MM`）與單一 `file` 或重複的 `files`；建立報表與第一版 |
| `POST /reports/{reportId}/versions` | multipart 單一 `file` 或重複的 `files`；新增版本，多檔版本需提供完整檔案組 |
| `GET /versions/{versionId}/source` | 下載單檔版本來源 |
| `GET /versions/{versionId}/files/{fileId}/source` | 下載多檔版本中的指定來源檔 |
| `GET /versions/{versionId}/issues/{issueId}/suggestion` | 使用者開啟錯誤時載入 AI 建議；path ID 需 URL encode |
| `GET /evaluations/latest` | 顯示後端保存的 AI 審核評測 JSON 快照 |
| `POST /reports/{reportId}/submissions` | JSON `{ "versionId": "..." }`，保存內部確認，成功回 204 |

## CSV profile

後端依 CSV 表頭判斷 profile。UTF-8（可含 BOM），檔案上限 2 MiB，最多 1,000 筆。

### `demo_csv_v1`

表頭包含 `id,product,previous,opening`，rows 使用欄位 `id/product/previous/opening`；issues 使用 `rowId/field/actual/expected`。

### `life_underwriting_v1`

表頭須為以下 8 欄，順序可不同：

`公司代號, 保單編號, 保單編號序號, 異動序號, 加保別, 加保日期, 退保別, 退保日期`

欄位值保留文字，以保留代號、序號與日期的前置 0。Version 提供來源順序的 `columns`；每列為 `{id, row, values}`。Issue 使用：

```json
{
  "id": "6:L0303",
  "ruleId": "L0303",
  "title": "錯誤說明",
  "rows": [6],
  "rowIds": ["6"],
  "cells": [
    { "row": 6, "rowId": "6", "column": "異動序號", "value": "00001" },
    { "row": 6, "rowId": "6", "column": "退保別", "value": "DEA" }
  ],
  "facts": { "退保別": "DEA" },
  "contextRowIds": ["7"],
  "repeated": false
}
```

前端使用 `rowIds` / `rows` 找出受影響資料列、使用 `cells` 標示錯誤儲存格，使用 `facts` 顯示規則依據。較新的多檔版本在檔案、列與儲存格帶有 `fileId`、`datasetType`；列 ID 與 issue 的列 ID 會包含檔案識別，前端需依檔案分組呈現，不能只用列號定位。多檔版本回傳 `files`，其中每個檔案含 `id / datasetType / filename / sourceSha256 / columns / rows`。

同一版本最多包含承保、給付、填報對象各一份 CSV。上傳時只能使用單一 `file` 或重複 `files` 欄位，不能混用。多檔新版本代表完整快照，應重新上傳該次申報需要的完整檔案組。

Issue 新增 `repeatStatus`（`new`、`repeated`、`regressed`）、`firstSeenNumber`、`prevSeenNumber`、`fixedInNumber` 與 `issueKey`。前端優先顯示 `repeatStatus`；`repeated` 布林值只表示連續版本都存在的錯誤，修正後再出現要顯示為 `regressed`。

## 共通回應

`Version` 提供 `id / number / filename / createdAt / rows / issues / files? / schemaProfileId / ruleVersion / validationStatus / validationRunId / sourceSha256 / manifestSha256 / summary / evidence`。`summary` 欄位為 `totalChecks / passedChecks / failedChecks / notEvaluatedChecks`。`evidence` 會列出 `executedRuleIds` 及未執行檢核原因。未評估的檢核不能顯示成通過；即使目前沒有 issue，也要提示部分規則未執行。`Report.canSubmit` 由後端決定，確認前後端會再由後端重驗。

Suggestion 回傳完整欄位：`title / explanation / suggestion / rejectedSuggestions / citations / blockedNumbers / model / verification / source`。只有 `verification=passed` 且建議本身重驗通過時，前端才展示候選修法。AI 失敗時 API 仍可能回傳固定說明，因此介面需呈現實際 `source` 與 `model`。

錯誤格式為 `{code, message, details?}`；前端以 `message` 呈現。常見狀態碼：404 資源不存在、413 檔案過大、422 輸入不合法、409 確認版本過期或檢核條件不符。

## 評測資料解讀

`GET /evaluations/latest` 回傳 AI 審核評測快照及 `evaluationContext`，包含 `evaluatedModel`、`runtimeModel`、`runtimeConfigured`、`modelMatchesRuntime`、`displayNotice`。回應使用 `Cache-Control: no-store`。前端需分別標示評測模型與執行模型，並呈現後端提供的提示。現有快照測試虛構壽險資料中，規則已抓出違規後 AI 是否正確說明、提出修法或在資訊不足時不猜。它不是規則偵測的標準答案，因此不能以它計算規則偵測 Precision、Recall 或 Accuracy。

建議修法的變更可帶 `fileId`、`datasetType`，前端顯示時要保留檔案位置；後端只接受明確違規儲存格的候選修改。

後端契約來源：[falltwo/once-wrong PR #6](https://github.com/falltwo/once-wrong/pull/6) 中的 `docs/backend-api.md`。
