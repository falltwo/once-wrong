# 前端本機整合

前端來源為 PR #1 的固定版本 `e287b1b04c9d8ffc9f3a224da509157cc516f2d4`，只取入 `frontend/`，沒有取用該分支舊版 backend。此檔案記錄接續 #5／#6 的本機整合，尚未推送。

## 啟動與驗證

在 `frontend/` 使用已驗證的 Node 24（本次為 24.22.1）：

```powershell
npm ci
npm test
npm run build
npm run dev -- --port 5173 --strictPort
```

API 預設連到 `http://127.0.0.1:8000`。其他位址可在 `.env.local` 設 `VITE_API_BASE_URL` 並重啟 Vite。前端不保存模型金鑰，也不在後端無法連線時退回 mock。

本次環境預設 Node 25.2.1 在 Vite 的 transform 後無訊息退出；同一份程式與依賴改用 Node 24.22.1，完整壓縮打包成功。`.nvmrc` 記錄 24，套件依賴與 lockfile 沿用來源。

## 已完成的呈現與操作

- 四欄 Demo、文字型壽險與多檔 `life_filing_v1` 都使用後端資料。任意中文欄位按 `columns` 呈現，前置零及空白不轉成數字。
- 多列錯誤在所有相關列顯示；多檔 rowId／fileId 分開定位，避免兩個檔案的「第 1 列」互相污染。檔案選單可限定範圍，原始檔可依 fileId 下載。
- 支援 `new`、`repeated`、`regressed` 標籤與篩選；詳情顯示首次／前次出現版及復發前曾修好的版本，並連到對應歷史版本。
- 錯誤詳情呈現 cells、facts、contextRowIds、重驗通過的建議及手冊頁碼。模型名稱取自回應，移除寫死 Gemini 的標籤。fallback 可由使用者手動重試。
- 評分頁實際呼叫 `/evaluations/latest`；實測分數旁顯示評測模型及目前執行模型，並呈現 `evaluationContext.displayNotice`。原偵錯 precision／recall layout 保留，持續標示為示意數字。
- 單檔仍用 multipart `file`；選多檔或勾選同次申報時使用重複的 `files` 欄位。每次送出完整的檔案組，不能用缺檔的版本取代完整申報後假裝檢核通過。
- summary 的未評估數量會顯示並阻止誤呈現為全部通過；確認按鈕仍以後端 `canSubmit` 為準。

## 契約與驗收

新增測試覆蓋多檔同列號隔離、多列錯誤、舊 repeated 相容與 regressed、文字保留、multipart 欄位、評分 no-store、來源下載與錯誤訊息。

後端需提供 `repeatStatus / firstSeenNumber / prevSeenNumber`，以及多檔版本的 `files`、每列 `fileId`、每格 `fileId / rowId`。前端兼容沒有上述新欄位的舊 Demo 回應。完整端對端驗收應同時涵蓋後端新規則與瀏覽器，不能只把 TypeScript 打包成功當作整套系統驗收。
