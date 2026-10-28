# AI 審核端點：原始提案與整合狀態

2026-10-29：下列端點已在本整合實作，執行中的回應契約以 [backend-api.md](backend-api.md) 為準。本文保留宥勳 `feat/ai-review@ea44b2f` 的原始提案、回應範例與設計理由；其中示意程式不是完整的 app 程式碼。回應模型位於 `once_wrong_ai.ai_review.api`，後端直接共用。

| # | 端點 | 改動 | 整合狀態 |
|---|---|---|---|
| 1 | `GET /versions/{versionId}/issues/{issueId}/suggestion` | 完整格式、AI 審核、SQLite 快取與失敗退回 | 已實作 |
| 2 | `POST /reports/{reportId}/versions`、`GET /reports/...` | 支援壽險承保資料（任意欄位） | 已實作；前端任意欄位畫面待接 |
| 3 | `GET /evaluations/latest` | 回傳 AI 評分結果 JSON | 已實作 |
| 4 | `GET /health` | 回報 AI 設定與知識庫狀態 | 已實作 |

## 安裝與套件名稱

原先兩個套件的 Python import 都叫 `once_wrong`。宥勳原文規劃由 AI 這邊改名，並將 `once_wrong_ai` 列為暫定名稱；本機整合已採此名稱，只保留 `src/once_wrong_ai/` 一份 AI 來源，後端維持 `backend/once_wrong/`。本文 imports 與 CLI 已同步，宥勳的遠端分支未由本次工作修改。

pip 安裝名稱與 Python import 是兩個欄位：AI 的 pip 名稱保留上游 `once-wrong`，後端是 `once-wrong-backend`，不另替 AI 決定第二個安裝名稱。AI 改名配套只需採用一次，詳見 [AI 套件交接](ai-package-handoff.md)。

在 repo 根目錄執行 `python -m pip install -e ".[dev]" -e "./backend[dev]"`，同時安裝本機 AI 與後端。完整環境設定見 [backend/README.md](../backend/README.md)；KB、規則備忘與評分檔的相對路徑均以 repo 根目錄解析。

| 環境變數 | 說明 |
|---|---|
| `ONCE_WRONG_PROVIDER` | `openrouter` 或 `gemini`。不設時，有 OpenRouter 金鑰就選 OpenRouter，否則 Gemini |
| `OPENROUTER_API_KEY` | OpenRouter 金鑰。沒設定時端點照常運作，只是一律回固定說明 |
| `OPENROUTER_MODEL` | 模型 id，程式預設 `deepseek/deepseek-v4-flash` |
| `GOOGLE_API_KEY`、`ONCE_WRONG_MODEL` | 改用 Gemini 時才需要 |
| `ONCE_WRONG_KB` | 填報手冊知識庫資料夾，預設 `data/kb`。手冊不進 git，伺服器上要先建好 |
| `ONCE_WRONG_RULE_MEMORY` | 團隊規則備忘，預設 `config/rule_notes.jsonl` |
| `ONCE_WRONG_EVALUATION` | 評分結果 JSON 的路徑，預設 `docs/evaluation/2026-10-28-gemini-3.5-flash.json` |

---

## 1. `GET /versions/{versionId}/issues/{issueId}/suggestion`

使用者點開某個錯誤時，前端會呼叫這個端點，取得白話說明和修法建議。前端已經照這個格式寫好畫面（`SuggestionPanel`）。

### 回應 200：`SuggestionResponse`

`from once_wrong_ai.ai_review.api import SuggestionResponse`。欄位跟前端 `frontend/src/types/index.ts` 的 `Suggestion` 一致（`tests/test_api.py` 有比對）。

```jsonc
{
  "title": "保單 A00002 異動序號未依序排列",
  "explanation": "根據填報手冊規定，……",
  "suggestion": {                        // 通過規則重驗的修法；沒有就是 null
    "reason": "異動序號應依序排列",
    "verification": "passed",
    "changes": [{ "rowId": "3", "row": 3, "column": "異動序號", "value": "00002" }]
  },
  "rejectedSuggestions": ["修改後產生新的錯誤：L0302（第 6,7 列）"],
  "citations": [{ "id": "LIFE-RULE-0068", "source": "個人壽險填報說明手冊範例與檢核規則 2025",
                  "section": ["參、欄位檢核", "一、承保資料欄位檢核"], "page": 46 }],
  "blockedNumbers": [],
  "model": "gemini-3.5-flash",
  "verification": "passed",              // suggestion 不是 null 時才是 passed，否則 unavailable
  "source": "ai"                         // ai／fallback_llm_error／fallback_number_guard
}
```

**原先問題（本整合已修正）**：後端只回 `{explanation, verification, source: "demo"}`，前端讀 `rejectedSuggestions.length` 會出錯，`"demo"` 也不在前端認得的 source 裡。現在即使 AI 不可用，仍回完整格式：`title` 用規則名稱、suggestion 為 null、陣列為空，source 為 `fallback_llm_error`。

### 錯誤

| HTTP | code | 情況 |
|---|---|---|
| 404 | `VERSION_NOT_FOUND`／`ISSUE_NOT_FOUND` | 版本或錯誤不存在（沿用現有的） |

**AI 呼叫失敗、逾時、沒設定金鑰時，都不回 5xx**，一律回 200，`source=fallback_llm_error`，`explanation` 是規則的固定說明。AI 失敗不能擋住使用者修資料。

### 實作

下面是示意，`store.get_cached_suggestion`、`store.get_version`、`store.save_suggestion` 是要新增的方法，名稱依後端習慣取；`find_violation`、`suggestion_payload`、`review_violation` 是 AI 審核已經有的。

```python
from starlette.concurrency import run_in_threadpool

from once_wrong_ai.ai_review.api import find_violation, suggestion_payload
from once_wrong_ai.ai_review.reviewer import AIReviewer
from once_wrong_ai.report import Report

def get_suggestion(version_id: str, issue_id: str):
    cached = store.get_cached_suggestion(version_id, issue_id)
    if cached:
        return cached

    version = store.get_version(version_id)          # 已保存的資料列，不信任前端送來的錯誤
    report = Report(
        report_id=version["reportId"], version=version["number"],
        columns=columns, rows=rows,
        numeric_columns=numeric_columns,             # 壽險資料傳空集合，日期和代號都當文字
        meta={"險別": "個人壽險"},                    # 用來篩選手冊段落；demo 報表不用填
    )
    before = rules.check(report)                     # 用伺服器上的規則重跑
    row_id = lambda r: rows[r - 1]["id"]             # demo 用資料的 id 欄；壽險用列號 str(r)
    violation = find_violation(before, issue_id, row_id)
    if violation is None:
        raise ApiError(404, "ISSUE_NOT_FOUND", "此修訂找不到指定問題。")

    item = reviewer.review_violation(report, violation, before)   # 同步呼叫，約 10～16 秒
    payload = suggestion_payload(item, reviewer.llm.model_name, row_id).model_dump()
    store.save_suggestion(version_id, issue_id, payload)
    return payload
```

- **用 `run_in_threadpool` 呼叫**。Gemini 是同步呼叫，一次 10～16 秒，不要卡住 event loop。
- **要快取。** 同一版本的資料不會變，依 `(versionId, issueId)` 存起來重用。每次呼叫約 5,000 token。建議新增一張表：

  ```sql
  CREATE TABLE IF NOT EXISTS suggestions (
      version_id TEXT NOT NULL REFERENCES versions(id),
      issue_id TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      model TEXT NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY (version_id, issue_id)
  );
  ```

  `source=fallback_llm_error` 的結果**不要存**，下次再試一次 AI。
- **只在使用者點開時呼叫**，不要在上傳時對每個錯誤都呼叫。
- **AIReviewer 在 `create_app` 時建一次**：

  ```python
  from once_wrong_ai.ai_review.llm import llm_from_env
  from once_wrong_ai.kb.memory import RuleMemory
  from once_wrong_ai.kb.search import Retriever

  reviewer = AIReviewer(
      llm_from_env(), rules,                          # 依 ONCE_WRONG_PROVIDER 建 OpenRouter 或 Gemini
      knowledge=Retriever.from_dir(kb_dir),           # 知識庫不存在時傳 None，AI 照樣說明，只是沒有手冊依據
      memory=RuleMemory("config/rule_notes.jsonl"),
  )
  ```

  `llm_from_env()` 找不到金鑰或設定錯誤時會丟 `LLMError`。這時改用一個一律丟 `LLMError` 的假 client，端點就會自動回固定說明。

### demo 報表（`demo_csv_v1`）也能接 AI

示範規則可以直接用後端的欄位，issueId 跟後端現在的 `f"{row['id']}:R-07"` 完全一致（`tests/test_api.py::test_demo_rules_on_backend_columns_give_backend_issue_ids`）：

```python
from once_wrong_ai.rules import RuleSet
from once_wrong_ai.rules.examples import OpeningEqualsClosing, RequiredField

demo_rules = RuleSet([
    RequiredField(rule_id="R-01", column="product"),
    OpeningEqualsClosing(rule_id="R-07", closing_column="previous", opening_column="opening"),
])
# numeric_columns={"previous", "opening"}，row_id=lambda r: rows[r - 1]["id"]
```

R-01／R-07 是團隊自訂的規則，手冊裡沒有，所以這兩條的 `citations` 會是空的。

### 測試

`AIReviewer` 接受任何有 `model_name` 屬性和 `explain(system_prompt, user_prompt)` 方法的物件。建議 `create_app` 多一個參數讓測試注入假的 LLM，寫法參考本分支 `tests/conftest.py` 的 `FakeLLM`。至少要測：

- 回應欄位跟前端型別一致
- AI 失敗時回 200 和固定說明
- 第二次呼叫走快取，沒有再呼叫 LLM
- 未知的 issueId 回 404

---

## 2. 壽險承保資料：上傳與讀取版本

`POST /reports/{reportId}/versions` 現在只收 `id, product, previous, opening` 四欄。要讓壽險規則的結果出現在畫面上，需要多一個 profile。

### 新 profile：`life_underwriting_v1`

- **辨識方式**：CSV 表頭剛好是這 8 欄就走壽險：`公司代號, 保單編號, 保單編號序號, 異動序號, 加保別, 加保日期, 退保別, 退保日期`。範例檔是 `examples/mock_life_policies_2025.csv`。
- **所有欄位都當文字**：公司代號 `01`、異動序號 `00001`、日期 `00000000` 都有前置 0，轉成數字就壞了。建 `Report` 時 `numeric_columns=set()`。
- **規則**：`from once_wrong_ai.rules.life import life_field_rules`，共 11 條。`ruleVersion` 建議用 `life_field_rules_v1`。

### `Version` 回應（壽險）

```jsonc
{
  "id": "...", "number": 1, "filename": "...", "createdAt": "...",
  "schemaProfileId": "life_underwriting_v1",
  "ruleVersion": "life_field_rules_v1",
  "columns": ["公司代號", "保單編號", "保單編號序號", "異動序號", "加保別", "加保日期", "退保別", "退保日期"],
  "rows": [{ "id": "1", "row": 1, "values": { "公司代號": "01", "保單編號": "A00001", "異動序號": "00000", "...": "..." } }],
  "issues": [ /* IssueResponse */ ],
  "validationStatus": "completed", "validationRunId": "...", "sourceSha256": "...", "summary": { "...": "..." }
}
```

`issues` 用 `issue_payloads(rows, violations, row_id=str, repeated=...)` 產生（`from once_wrong_ai.ai_review.api import issue_payloads, IssueResponse`）：

```jsonc
{
  "id": "6:L0303",                       // {第一列的 rowId}:{ruleId}
  "ruleId": "L0303",                     // 手冊上的檢核編號
  "title": "第 6 列是這張保單的第一筆異動（00001），退保別不可以填 DEA。",
  "rows": [6], "rowIds": ["6"],
  "cells": [{ "row": 6, "rowId": "6", "column": "異動序號", "value": "00001" },
            { "row": 6, "rowId": "6", "column": "退保別", "value": "DEA" }],
  "facts": { "退保別": "DEA" },          // 程式算好的值
  "contextRowIds": ["7"],                // 同一保單的其他筆
  "repeated": false
}
```

- **rowId 用列號字串**。壽險資料沒有唯一的 id 欄（異動序號可能填重複）。
- **`repeated`**：上一版有同樣 `id` 的錯誤就是 `true`，跟 demo 的做法一樣。
- **`summary`**：沿用「規則對資料列的一次評估」的算法，11 條規則各算一次。
- **前端要配合**：錯誤詳情的欄位名稱不能寫死成 opening／product，改用 `cells[].column`。「目前資料」用 `cells[].value`，「規則預期值」用 `facts`。這部分請前端組員改。

`GET /reports`、`GET /reports/{reportId}` 回傳的版本用同一個格式。demo 報表維持原本的格式不變。

---

## 3. `GET /evaluations/latest`（新增）

給前端測試結果頁顯示 AI 評分的實測結果。

- **回應 200**：直接回傳 `ONCE_WRONG_EVALUATION` 指向的 JSON 檔內容，不需要另外轉換。目前的檔案是 [docs/evaluation/2026-10-28-gemini-3.5-flash.json](evaluation/2026-10-28-gemini-3.5-flash.json)，由 `python -m once_wrong_ai.evaluation.run` 產生。
- **回應 404** `EVALUATION_NOT_FOUND`：檔案不存在時。

主要欄位：

| 欄位 | 意思 |
|---|---|
| `schemaVersion` | 目前是 `1`，格式改了會加 1 |
| `model`、`generatedAt` | 用哪個模型、什麼時候產生 |
| `dataset` | 案例數、錯誤數、險別、規則組 |
| `runs[]` | 每次評分的 seed、案例數、耗時、該次的處理正確率 |
| `metrics.handledCorrectly` | 處理正確：推得出原值就修回、推不出就不給修法（554/595，93%） |
| `metrics.restoredWhenInferable` | 資料裡有線索時修回原值的比例（95%） |
| `metrics.heldBackWhenNotInferable` | 資料裡沒答案，或要改別列時，不亂給修法的比例（87%） |
| `metrics.citedRule` | 引用的手冊段落裡有這條檢核編號的比例（100%） |
| `metrics.aiExplanationUsed`／`numberGuardBlocked`／`llmErrors` | AI 說明採用、被數字守門攔下、呼叫失敗的比例 |
| `outcomes` | 三類（推得出／推不出／要動別列）各自的結果筆數，以及重驗擋下的修法數 |
| `byRule[]` | 每條規則的同一組指標 |

每個比例都是 `{count, total, rate}`，`total` 為 0 時 `rate` 是 `null`。

給前端的提醒：測試結果頁現在比較的是「只有規則／只有 AI／Once Wrong」抓錯的 precision／recall。這份評分量的是**錯誤被規則抓到之後，AI 的說明和修法對不對**，兩件事不一樣，請另開一個「AI 審核評分」區塊來呈現。

---

## 4. `GET /health`（選做）

多回報 AI 是否可用，前端可以提前提示「AI 暫不可用，只顯示固定說明」：

```jsonc
{
  "status": "ok", "schemaProfileId": "demo_csv_v1", "ruleVersion": "demo_rules_v1",
  "ai": { "configured": true, "model": "gemini-3.5-flash", "knowledgeBase": true }
}
```

---

## 附帶發現

前端 `reportsApi.create()` 需要 `POST /reports`（建立報表並上傳第一版）。本整合已補齊：multipart `name / period / file`，成功回 201 `Report`，報表與第一版原子保存。名稱與期間限制見 [backend-api.md](backend-api.md)。
