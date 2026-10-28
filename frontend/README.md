# Once Wrong 前端

React + TypeScript + Vite，使用 React Router、TanStack Query、Lucide 圖示與獨立 CSS。前端透過 `VITE_API_BASE_URL` 呼叫後端，不需要在瀏覽器放 API 金鑰。

```sh
npm install
npm run dev
```

`npm run build` 執行 TypeScript 檢查與正式打包。

需同時啟動 repo 的 FastAPI 後端，預設位置為 `http://127.0.0.1:8000`。`.env.example` 可複製成 `.env.local` 設定 API 位址。後端預設允許 `localhost:5173` 和 `127.0.0.1:5173`；使用其他 dev server port 時，請在啟動後端前將該前端 origin 加入 `ONCE_WRONG_ALLOWED_ORIGINS`。後端離線會顯示連線錯誤，不會切回瀏覽器 mock 資料。

## 已實作

- 報表列表、檢核工作區、版本報告頁。
- 建立新報表並上傳第一版 CSV，或在既有報表中上傳修正版；均由後端解析、檢核及保存。
- 檢核摘要、錯誤篩選、搜尋與 AI 審查側欄。
- 顯示後端依相同資料 ID + 規則 ID 判定的重複錯誤。
- JSON 檢核報告下載，讀取後端建議及驗證狀態，並記錄內部確認。
- 測試結果頁：比較示意 precision、recall、accuracy 與混淆矩陣；標明示意值，未經真實實驗驗證。
- URL 保存版本、篩選與選取錯誤；報表和版本由後端持久保存。
- 響應式版面、可鍵盤操作的錯誤按鈕與原生 modal dialog。

## 展示

後端預設建立第 1、2 版供展示。上傳 `public/sample-errors.csv` 可展示錯誤與重複錯誤；再上傳 `public/sample-fixed.csv` 可展示 12 項通過，並記錄內部確認。確認只寫入後端，不會送到外部申報系統。

CSV 欄位：`id,product,previous,opening`。最大 2 MB、1,000 筆，金額使用非負安全整數且不含千分位逗號。Excel 請另存 CSV UTF-8；尚未支援直接解析 xlsx。

## 與其他組員串接

| 範圍 | 串接方式 |
| --- | --- |
| 後端 | `src/api/reports.ts` 使用本專案 FastAPI 的 HTTP API；資料、版本與檢核結果由後端保存 |
| 規則 | `src/types/index.ts` 對應 Issue/Version 與後端 schema/rule metadata |
| AI | `reportsApi.suggestion` 只查被選取的錯誤；顯示 AI/fallback 來源、重驗通過的多欄修法、退回原因與手冊引用 |

使用 `GET /reports`、`GET /reports/:id`、`POST /reports`（multipart：name、period、file）、`POST /reports/:id/versions`（multipart）、`GET /versions/:versionId/issues/:issueId/suggestion`、`POST /reports/:id/submissions`。新增報表會在後端同一交易中建立報表與第一版；CSV無效時不會留下空報表。完整契約見 repo 的 `docs/backend-api.md`，adapter 來源與驗收流程見 `backend/integration/README.md`。

前端顯示的規則結果、摘要、重複錯誤、送出資格及 AI 審查均以後端回應為準。目前檢核與單一錯誤 AI 審查同步完成；候選修法必須通過後端規則重驗才會顯示。沒有 Gemini 金鑰時回傳固定說明，且不會假裝已有 AI 修法。

## 範圍與限制

後端預設附一份合成示範報表，也可自行新增報表與版本；尚無帳號、正式官方規則、AI 實測結果、權限與外部申報。Gemini 實際回覆品質仍待設定金鑰後驗證。
後端僅有兩條自訂示範規則：R-01 險種不可空白、R-07 同列期初等於同檔上期末。沒有依官方18位金額精度驗證，也沒有跨期可信來源勾稽。
測試結果頁的 precision/recall/accuracy 使用明確標示的假設值來示範版面，並非實測成績。資料儲存在本機 SQLite，不代表正式稽核保存能力。
UI 目前使用獨立 CSS；Tailwind、shadcn/ui、TanStack Table 尚未加入，避免第一版多餘抽象。資料量增加後再評估表格分頁／虛擬化。
