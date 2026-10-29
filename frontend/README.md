# Once Wrong 前端

React + TypeScript + Vite，使用 React Router、TanStack Query、Lucide 圖示與獨立 CSS。前端透過 `VITE_API_BASE_URL` 呼叫後端，不需要在瀏覽器放 API 金鑰。

```sh
npm install
npm run dev
```

`npm run build` 執行 TypeScript 檢查與正式打包。

需同時啟動 repo 的 FastAPI 後端，預設位置為 `http://127.0.0.1:8000`。複製 `.env.example` 為 `.env.local`；開發時前端會透過 Vite `/api` proxy 呼叫後端，因此 Vite 使用 5173 以外的連接埠也不需要額外設定 CORS。若後端位置不同，更新 `VITE_API_PROXY_TARGET`。後端離線會顯示連線錯誤，不會切回瀏覽器 mock 資料。

## 已實作

- 報表列表、檢核工作區、版本報告頁。
- 建立新報表並上傳第一版 CSV，或在既有報表中上傳修正版；均由後端解析、檢核及保存。
- 檢核摘要、錯誤篩選、搜尋與 AI 審查側欄。
- 依 `schemaProfileId` 顯示 demo 欄位或壽險 `columns` / `rows[].values`；錯誤定位讀取 demo `rowId/field` 或壽險 `rowIds/cells/facts`。
- JSON 檢核報告下載，讀取後端建議及驗證狀態，並記錄內部確認。
- 測試結果頁：讀取 `/evaluations/latest` 顯示 AI 審核評測快照，並另列各報表最新版檢核概況。評測快照不是規則抓錯 Precision/Recall/Accuracy。
- URL 保存版本、篩選與選取錯誤；報表和版本由後端持久保存。
- 響應式版面、可鍵盤操作的錯誤按鈕與原生 modal dialog。

## 展示

後端預設建立第 1、2 版供展示。上傳 `public/sample-errors.csv` 可展示錯誤與重複錯誤；再上傳 `public/sample-fixed.csv` 可展示 12 項通過，並記錄內部確認。確認只寫入後端，不會送到外部申報系統。

支援兩種 CSV profile，後端依表頭辨識：

- `demo_csv_v1`：`id,product,previous,opening`；金額為非負安全整數且不含千分位逗號。
- `life_underwriting_v1`：`公司代號,保單編號,保單編號序號,異動序號,加保別,加保日期,退保別,退保日期`；表頭順序可不同，欄位值保留文字以保留前置 0。

兩種格式都接受 UTF-8 CSV、最大 2 MiB、最多 1,000 筆；尚未支援直接解析 xlsx。

## 與其他組員串接

| 範圍 | 串接方式 |
| --- | --- |
| 後端 | `src/api/reports.ts` 使用本專案 FastAPI 的 HTTP API；資料、版本與檢核結果由後端保存 |
| 規則 | `src/types/index.ts` 對應 Issue/Version 與後端 schema/rule metadata |
| AI | `reportsApi.suggestion` 只查被選取的錯誤；顯示 AI/fallback 來源、重驗通過的多欄修法、退回原因與手冊引用 |

使用 `GET /health`、`GET /reports`、`GET /reports/:id`、`POST /reports`（multipart：name、period、file）、`POST /reports/:id/versions`（multipart）、`GET /versions/:versionId/issues/:issueId/suggestion`、`GET /evaluations/latest`、`POST /reports/:id/submissions`。新增報表會在後端同一交易中建立報表與第一版；CSV 無效時不會留下空報表。完整契約見 repo 的 `docs/backend-api.md`。

前端顯示的規則結果、摘要、重複錯誤、送出資格及 AI 審查均以後端回應為準。目前檢核與單一錯誤 AI 審查同步完成；候選修法必須通過後端規則重驗才會顯示。壽險錯誤若跨版本改變列位置，後端目前以列號比對 `repeated`，因此該狀態可能不代表相同保單的錯誤是否再次發生。

## 範圍與限制

後端預設附 demo 報表，也可自行新增報表與版本；尚無帳號、正式官方規則、權限與外部申報。AI 評測快照是以程式產生的虛構壽險資料、Gemini 模型評估 AI 如何處理規則已抓出的違規，不是正式資料結果，也不是規則抓錯的 Precision/Recall。
後端僅有兩條自訂示範規則：R-01 險種不可空白、R-07 同列期初等於同檔上期末。沒有依官方18位金額精度驗證，也沒有跨期可信來源勾稽。
資料儲存在本機 SQLite，不代表正式稽核保存能力。
UI 目前使用獨立 CSS；Tailwind、shadcn/ui、TanStack Table 尚未加入，避免第一版多餘抽象。資料量增加後再評估表格分頁／虛擬化。
