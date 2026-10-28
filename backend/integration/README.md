# 前後端串接紀錄

目前前端、API adapter 與 FastAPI 示範服務都在同一個 repo。前端透過 `VITE_API_BASE_URL` 呼叫後端，不使用 localStorage/mock 作為後端失效時的替代來源。

`frontend-pr1.patch`、`reports.ts` 與 `smoke.mjs` 是分支整合期間留下的交接與驗收工具。原始 PR 分開時的重現步驟及限制仍可參考，但不需要再把 adapter 或 patch 複製到前端。

前端從 `frontend/` 啟動，後端安裝及啟動方式見 [`backend/README.md`](../README.md)。HTTP 路徑、表單欄位、錯誤格式與第一版上傳流程見 [`docs/backend-api.md`](../../docs/backend-api.md)。

`smoke.mjs` 會上傳合成 CSV、建立新版本並留下內部確認紀錄；只有在隔離資料庫上手動執行。它不會清空資料庫。
