# 評測來源與展示

此目錄的 JSON 與報告保留當次評測的模型、案例與分數。`2026-10-28-gemini-3.5-flash` 的 554/595（約 93%）屬於 Gemini 既有評測；它不能作為 OpenRouter 上 DeepSeek 模型的成績。若要宣稱目前 Demo 模型的成績，須在確定模型與程式版本後重新執行評測，保留該次來源資訊。

`GET /evaluations/latest` 保留原有 `model`、`metrics` 等欄位，另加入 `evaluationContext`：

| 欄位 | 意義 |
|---|---|
| `evaluatedModel` | 評測檔記錄的模型，等同原有頂層 `model` |
| `runtimeModel` | 本次後端實際選用的模型，與 `/health.ai.model` 一致 |
| `runtimeConfigured` | 目前 AI 服務是否成功建立客戶端；不表示已完成真實呼叫測試 |
| `modelMatchesRuntime` | 兩個模型名稱是否完全相同；不表示目前程式、參數、資料與既有評測完全一致 |
| `displayNotice` | 可直接放在分數旁的來源提示 |

前端顯示每份快照的評測模型、目前模型與 `displayNotice`。兩個模型不同時，應清楚顯示「此分數不代表目前模型表現」；模型名稱相同，也需保留評測的日期與限制。

本機已整合前端，優先顯示 `endToEndHandledCorrectly`（全部錯誤，包含模型呼叫失敗）、`modelResponseAvailable`、`llmErrors`。原有 `handledCorrectly` 明列為取得模型回覆後的條件分數；舊快照缺少端到端指標時不自行推算。端點會拒絕缺少有效 `model` 的評測檔，並使用 `Cache-Control: no-store` 避免顯示過期的執行模型資訊。

[2026-10-29 真實系統端到端驗收](2026-10-29-live-system-e2e.md)已完成。批次模型評測透過上傳／建議 API 執行，原始回應、合成案例與資料庫證據保留在忽略的 `logs/live-evaluation/`；只有完整執行並檢查資料庫後才產生正式摘要。執行工具為 `tools/evaluate_demo_api.py`，需要本機金鑰及已建立的知識庫，會產生模型費用。

本次批次依使用者指示停止：完成 83 案例／122 筆完整評分，未完成原訂 390／595，沒有新的正式模型品質分數。後續工具目前需要重新執行完整批次，尚不支援從這次日誌續跑；不要把重跑結果與本次部分結果混合計分。
