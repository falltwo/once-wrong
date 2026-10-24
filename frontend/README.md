# Once Wrong 前端原型

React + TypeScript + Vite，使用 React Router、TanStack Query、Lucide 圖示與獨立 CSS。無需 API 金鑰。

```sh
npm install
npm run dev
```

`npm run build` 執行 TypeScript 檢查與正式打包。

## 已實作

- 報表列表、檢核工作區、版本報告頁。
- CSV 讀取、格式與資料識別碼驗證、版本保存。
- 檢核摘要、錯誤篩選、搜尋、錯誤側欄與示範建議。
- 相同資料 ID + 規則 ID 對比前一版，標記重複錯誤。
- JSON 檢核報告下載、可複製建議值、通過後模擬送出。
- 測試結果頁：比較示意 precision、recall、accuracy 與混淆矩陣；標明示意值，未經真實實驗驗證。
- URL 保存版本、篩選與選取錯誤；localStorage 保存報表。
- 響應式版面、可鍵盤操作的錯誤按鈕與原生 modal dialog。

## 展示

預設第 2 版有兩個錯誤：POL-003 的期初金額不符，POL-004 險種空白。
下載 `public/sample-errors.csv` 可展示錯誤再次出現；上傳 `public/sample-fixed.csv` 可展示全數通過並進行模擬送出。

CSV 欄位：`id,product,previous,opening`。最大 2 MB、1,000 筆，金額使用非負安全整數且不含千分位逗號。Excel 請另存 CSV UTF-8；尚未支援直接解析 xlsx。

## 與其他組員串接

| 成員   | 交接點                                                                                           |
| ------ | ------------------------------------------------------------------------------------------------ |
| B 後端 | `src/api/reports.ts`：將 list/get/upload/submit 替換為 HTTP 請求，接收伺服器的檢核狀態與送出資格 |
| C 規則 | `src/types/index.ts` 的 Issue/Version；目前示範規則位於 `src/features/validation/rules.ts`       |
| D AI   | `reportsApi.suggestion`，回傳解釋、建議值與後端重驗狀態                                          |

API 建議：GET /reports、GET /reports/:id、POST /reports/:id/versions（multipart）、GET /versions/:id/issues/:issueId/suggestion、POST /reports/:id/submissions。

上線串接時由後端負責規則判定、建議重驗、版本與操作紀錄、送出資格；前端只呈現結果。不要在前端放 AI 金鑰。目前所有檢核為同步本機示範，未實作背景任務查詢。

## 範圍與限制

只有一份示範報表，可新增其版本；尚無新增報表、帳號、正式後端、真實 AI、權限與正式申報。
前端僅有兩條自訂示範規則：R-01 險種不可空白、R-07 期初等於上期末。不是主辦官方完整規則。
AI 說明使用固定範本。顯示的示範重驗通過，是根據等式的預期值產生，不代表完成正式 AI 建議重驗管線。
資料留在目前瀏覽器，清除網站資料就會重設；不具正式稽核保存能力。
UI 目前使用獨立 CSS；Tailwind、shadcn/ui、TanStack Table 尚未加入，避免第一版多餘抽象。資料量增加後再評估表格分頁／虛擬化。
