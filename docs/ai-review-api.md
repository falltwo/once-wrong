# AI 審核的 API 回應格式（提案）

給負責後端（`feat/backend-validation-api`）和前端（`codex/frontend-prototype`）的組員。本分支（`feat/ai-review`）新增的壽險欄位規則、AI 說明和評分結果，目前後端 API 都沒有提供，前端也就沒辦法呈現。這份文件寫清楚後端要回什麼格式，以及本分支已經準備好哪些可以直接呼叫的程式。

## 現況差距

| | 後端目前 | 前端目前 | 本分支已有 |
|---|---|---|---|
| 資料列 | 固定 `id, product, previous, opening` | 同左 | 任意欄位（壽險承保 8 欄，中文欄名） |
| 錯誤 | `ruleId` 只有 R-01／R-07，`field` 只有 opening／product | 同左 | `Violation`：任意規則、多個格子、`facts`、參考列 |
| AI 說明 | 固定 `{explanation, verification: "unavailable", source: "demo"}` | **已照 AI 版的 `Suggestion` 型別寫好畫面** | `AIReviewer` 產生完整結果 |
| 評分結果 | 無 | 測試結果頁是示意數字 | `summary.json`（595 筆錯誤的實測結果） |

> 注意：前端的 `Suggestion` 型別要求 `title`、`rejectedSuggestions`、`citations`、`blockedNumbers`、`model`，但後端 demo 回應沒有這些欄位，畫面讀 `rejectedSuggestions.length` 時會出錯。就算還沒接 AI，後端也建議先回完整的格式（`source` 用 `fallback_llm_error`，`suggestion` 給 `null`）。

## 1. AI 說明：`GET /versions/{versionId}/issues/{issueId}/suggestion`

回傳 `SuggestionResponse`，欄位跟前端 `frontend/src/types/index.ts` 的 `Suggestion` 完全一致（本分支 `tests/test_api.py` 有比對）。pydantic 定義在 `once_wrong.ai_review.api`，後端可以直接拿來當 `response_model`。

```jsonc
{
  "title": "保單 A00002 異動序號未依序排列",
  "explanation": "根據填報手冊規定，……",
  "suggestion": {                       // 通過規則重驗的修法；沒有就是 null
    "reason": "異動序號應依序排列",
    "verification": "passed",
    "changes": [{ "rowId": "3", "row": 3, "column": "異動序號", "value": "00002" }]
  },
  "rejectedSuggestions": ["修改後產生新的錯誤：L0302（第 6,7 列）"],  // 被擋下的修法，只放理由
  "citations": [{ "id": "LIFE-RULE-0068", "source": "個人壽險填報說明手冊範例與檢核規則 2025",
                  "section": ["參、欄位檢核", "一、承保資料欄位檢核"], "page": 46 }],
  "blockedNumbers": [],                 // 有值代表說明被數字守門攔下，已改用固定說明
  "model": "gemini-3.5-flash",
  "verification": "passed",             // suggestion 不是 null 時才是 passed
  "source": "ai"                        // ai／fallback_llm_error／fallback_number_guard
}
```

後端的做法（伺服器上要有知識庫 `data/kb/` 和 `GOOGLE_API_KEY`）：

```python
from once_wrong.ai_review.api import suggestion_payload
from once_wrong.ai_review.reviewer import AIReviewer

before = rules.check(report)                    # 用保存的資料列重跑規則，不信任前端傳來的錯誤
violation = ...                                 # 依 issueId 找到對應的那一筆（id 規則見下節）
item = reviewer.review_violation(report, violation, before)
return suggestion_payload(item, reviewer.llm.model_name, row_id)
```

- **AI 失敗不回 5xx。** 呼叫失敗、逾時都回 200，`source=fallback_llm_error`，`explanation` 是規則的固定說明。
- **要快取。** 每次呼叫約 10～16 秒、5,000 token。建議依 `(versionId, issueId)` 存起來；同一版本的資料不會變，結果可以重用。前端是使用者點開錯誤時才呼叫，不要在上傳時對每個錯誤都呼叫。
- **只送出錯的列。** 送給 Gemini 的只有出錯的列、規則指定的參考列、同一列的其他錯誤和手冊段落，不是整份報表。真實保戶資料不可送外部 AI。

## 2. 任意欄位的資料列與錯誤（壽險承保資料）

目前的 `DataRow`／`Issue` 寫死 demo 的 4 個欄位，壽險資料放不進去。建議新增一個 profile（例如 `schemaProfileId: "life_underwriting_v1"`），`Version` 改用通用格式：

```jsonc
{
  "schemaProfileId": "life_underwriting_v1",
  "columns": ["公司代號", "保單編號", "保單編號序號", "異動序號", "加保別", "加保日期", "退保別", "退保日期"],
  "rows": [{ "id": "1", "row": 1, "values": { "保單編號": "A00001", "異動序號": "00000", ... } }],
  "issues": [ /* IssueResponse，見下 */ ]
}
```

`IssueResponse`（`once_wrong.ai_review.api.issue_payloads` 產生）：

```jsonc
{
  "id": "6:L0303",                      // {第一列的 rowId}:{ruleId}，跟 demo 的格式一致
  "ruleId": "L0303",                    // 手冊上的檢核編號，知識庫靠它找段落
  "title": "第 6 列是這張保單的第一筆異動（00001），退保別不可以填 DEA。",
  "rows": [6], "rowIds": ["6"],
  "cells": [{ "row": 6, "rowId": "6", "column": "異動序號", "value": "00001" },
            { "row": 6, "rowId": "6", "column": "退保別", "value": "DEA" }],
  "facts": { "退保別": "DEA" },         // 程式算好的值，可以放在「規則預期值」那格
  "contextRowIds": ["7"],               // 同一保單的其他筆，畫面可以一起列出來
  "repeated": false                     // 由第 5 步「擋重複錯」決定
}
```

- **rowId**：壽險資料沒有唯一的 id 欄（異動序號可能填重複），預設用列號字串。`issue_payloads` 和 `suggestion_payload` 都可以傳入自訂的 `row_id`。
- **值的型別**：整數用 number，小數和超過 2^53 的整數用字串，以免 JavaScript 失真。日期、代號（例如 `00001`）一律是字串。
- **前端要配合的地方**：錯誤詳情的欄位名稱不能寫死 opening／product，改用 `cells[].column`；「目前資料」用 `cells[].value`，「規則預期值」用 `facts`。

## 3. 評分結果：建議新增 `GET /evaluations/latest`

直接回傳 `python -m once_wrong.evaluation.run` 產生的 `summary.json`。最新一份已經放在 [docs/evaluation/2026-10-28-gemini-3.5-flash.json](evaluation/2026-10-28-gemini-3.5-flash.json)。

| 欄位 | 意思 |
|---|---|
| `dataset` | 案例數、錯誤數、險別、規則組 |
| `runs[]` | 每次評分的 seed、案例數、耗時、該次的處理正確率 |
| `metrics.handledCorrectly` | **處理正確**：推得出原值就修回、推不出就不給修法。595 筆中 554 筆（93%） |
| `metrics.restoredWhenInferable` | 資料裡有線索時，修回原值的比例（95%） |
| `metrics.heldBackWhenNotInferable` | 資料裡沒有答案，或要改別列才修得好時，不亂給修法的比例（87%） |
| `metrics.citedRule` | 引用的手冊段落裡有這條檢核編號的比例（100%） |
| `metrics.aiExplanationUsed`／`numberGuardBlocked`／`llmErrors` | AI 說明採用、被數字守門攔下、呼叫失敗的比例 |
| `outcomes` | 三類（推得出／推不出／要動別列）各自的結果筆數，以及重驗擋下的修法數 |
| `byRule[]` | 每條規則的同一組指標 |

每個比例都是 `{count, total, rate}`。`total` 為 0 時，`rate` 是 `null`。

**前端測試結果頁要注意**：現在的頁面比較的是「只有規則／只有 AI／Once Wrong」抓錯的 precision／recall，但這份評分量的是**錯誤被規則抓到之後，AI 的說明和修法對不對**，兩件事不一樣。建議另外開一個「AI 審核評分」區塊來呈現，不要把數字填進原本的 precision／recall 卡片。三種方式的抓錯比較目前還沒有實驗數據。

## 4. 整合時的其他事項

- **套件名稱撞名。** 後端是 `backend/once_wrong/`，本分支是 `src/once_wrong/`，裝在同一個環境會互相蓋掉。詳見 [handoff-ai-review.md](handoff-ai-review.md)「跟組員的分支整合時要注意」。
- **規則以誰為準。** `once_wrong.rules.life` 的 11 條是為了讓 AI 審核和評分先跑起來寫的。正式規則引擎接上後，要確認 `rule_id` 用手冊的檢核編號，並且產生 `Violation`（多筆規則要填 `context_rows`）。
