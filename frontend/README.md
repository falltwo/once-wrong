# Once Wrong 前端

React + TypeScript + Vite，使用 React Router、TanStack Query、Lucide 圖示與獨立 CSS。前端透過 `VITE_API_BASE_URL` 呼叫後端，不需要在瀏覽器放 API 金鑰。

```sh
npm ci
npm test
npm run dev
```

`npm run build` 執行 TypeScript 檢查與正式打包。`.nvmrc` 記錄本次驗證使用的 Node 24。

需同時啟動 repo 的 FastAPI 後端，預設位置為 `http://127.0.0.1:8000`。`.env.example` 可複製成 `.env.local` 設定 API 位址。後端預設允許 `localhost:5173` 和 `127.0.0.1:5173`；使用其他 dev server port 時，請在啟動後端前將該前端 origin 加入 `ONCE_WRONG_ALLOWED_ORIGINS`。後端離線會顯示連線錯誤，不會切回瀏覽器 mock 資料。

## 已實作

- 報表列表、檢核工作區、版本報告頁。
- 建立新報表並上傳第一版 CSV，或在既有報表中上傳修正版；均由後端解析、檢核及保存。
- 檢核摘要、錯誤篩選、搜尋與 AI 審查側欄。
- 任意欄位的文字型壽險資料、出錯格子／規則 facts／參考列、多檔範圍與來源下載。
- 顯示後端業務鍵判定的 new／repeated／regressed，含前次出現版與曾修好的版本連結。
- JSON 檢核報告下載，讀取後端建議及驗證狀態，並記錄內部確認。
- 測試結果頁：讀取實際 AI 審核評分快照，分數旁顯示評測模型、目前模型與展示提示；另保留明確標為示意的 precision／recall／accuracy 區塊。
- URL 保存版本、篩選與選取錯誤；報表和版本由後端持久保存。
- 響應式版面、可鍵盤操作的錯誤按鈕與原生 modal dialog。

## 展示

### 工作區互動

- 上方古籍卷宗可切換版本；歷史版本會顯示金邊封條與返回最新版入口。翻頁音效由使用者點擊觸發，可關閉；減少動態效果模式停用翻頁動畫與紙聲。
- 側邊導覽提供滑鼠磁吸及選中掃光。掃光表示目前導覽選項，不代表後端持續執行檢核。
- 左下 Audit Stream 讀取既有請求與操作事件；快取、固定說明、AI 與示範引用分開顯示。它不保存資料，也不是權威稽核紀錄。
- 左下 OW 可切換展示報表場景；窄螢幕入口位於頂部。壽險實驗室使用合成樣本，首次開啟會透過既有 API 建立報表，之後重用。兩個場景共用本機沙盒，不是租戶隔離或正式申報環境。
- 點「上傳修正版」時，粒子由按鈕飛向側欄邊緣等待；送出後只在後端成功回覆時注入 OW，失敗時消散。取消尚未送出的上傳會清除準備動畫。
- 錯誤格紅框固定在儲存格內；比對連線使用列內相對座標，避免翻頁、縮放與列位移造成定位漂移。

後端預設建立第 1、2 版供展示。上傳 `public/sample-errors.csv` 可展示錯誤與重複錯誤；再上傳 `public/sample-fixed.csv` 可展示 12 項通過，並記錄內部確認。確認只寫入後端，不會送到外部申報系統。

Demo CSV 欄位為 `id,product,previous,opening`；另支援後端的八欄壽險承保與 `life_filing_v1` 多檔版本。檔案均為 CSV UTF-8，每檔上限依後端契約檢查。多檔修訂每次上傳完整檔案組，未評估的必要檢查會明確顯示，不能當作通過。Excel 請另存 CSV UTF-8；尚未支援直接解析 xlsx。

## 與其他組員串接

| 範圍 | 串接方式 |
| --- | --- |
| 後端 | `src/api/reports.ts` 使用本專案 FastAPI 的 HTTP API；資料、版本與檢核結果由後端保存 |
| 規則 | `src/types/index.ts` 對應 Issue/Version 與後端 schema/rule metadata |
| AI | `reportsApi.suggestion` 只查被選取的錯誤；顯示 AI/fallback 來源、重驗通過的多欄修法、退回原因與手冊引用 |

使用 `GET /reports`、`GET /reports/:id`、`POST /reports`（multipart：name、period、file 或重複 files）、`POST /reports/:id/versions`（multipart）、`GET /versions/:versionId/issues/:issueId/suggestion`、`POST /reports/:id/submissions`、`GET /evaluations/latest` 及各檔來源下載。新增報表會在後端同一交易中建立報表與第一版；CSV 無效時不會留下空報表。完整契約見 [API 文件](../docs/backend-api.md)，本次來源與本機驗證見 [前端整合說明](../docs/frontend-local-integration.md)。

前端顯示的規則結果、摘要、重複錯誤、送出資格及 AI 審查均以後端回應為準。候選修法必須通過後端規則重驗才會顯示；AI 不可用時回傳固定說明，不會假裝已有 AI 修法。數字防護／連線 fallback 可由使用者手動重試。

## 範圍與限制

後端預設附一份合成示範報表，也可自行新增報表與版本；沒有帳號／權限或外部申報。實際支援規則以後端 profile 與 ruleVersion 為準，不能把目前的局部壽險規則當作完整官方申報驗收。
舊 Gemini 的 93% 是既有評測模型與資料的結果，不能代表目前 OpenRouter 模型或新的格子限制政策已實測。測試結果頁的示意 precision／recall／accuracy 也不是實測成績。
UI 目前使用獨立 CSS；Tailwind、shadcn/ui、TanStack Table 尚未加入，避免第一版多餘抽象。資料量增加後再評估表格分頁／虛擬化。
