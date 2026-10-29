# 本機瀏覽器驗收

2026-10-29。使用 computer-use 技能與 CUA 的 in-app browser，操作真實 Vite／FastAPI。初次子代理因沒有可用連線未能開始；後續使用者要求繼續時重新盤點，已取得可用 IAB 並完成下列驗收。

測試限定隔離的本機 smoke.sqlite3、合成資料與無金鑰的模型 fallback。前端為 15173、API 為 18106，API 的 provider 刻意指定 OpenRouter，供評分來源差異展示；這不是團隊預設或已連線的證明。

| 操作 | 可見結果 |
| --- | --- |
| 開啟報表列表 | 來自後端的三份合成報表及實際版本數。 |
| 開啟壽險第 3 版 | 中文任意欄位、前置零、修好後復發標籤；連續／復發摘要為 0／1。 |
| 勾選復發篩選及開啟詳情 | 顯示 1／2 列；首次／前次第 1 版、修好第 2 版及歷史連結。 |
| 點選修好的第 2 版連結 | 正確切到第 2 版、零錯誤，因為是歷史版仍不能確認。 |
| 開啟評分頁 | 93.1% 旁明列 Gemini；目前設定 DeepSeek 且未完成連線，提示不能把舊分數當目前模型表現。示意 precision／recall 另有標示。 |
| 多檔範圍選單 | 選承保檔後僅有對應列與欄位，避免不同檔案第 1 列互相混用。 |
| 展開未評估原因 | 列出尚未支援的官方規則，畫面不把這些列標為通過，確認按鈕 disabled。 |
| 點原始 underwriting.csv 下載 | 瀏覽器完成來源下載；API 測試另逐 bytes／SHA-256 核對。 |
| 開啟修正版 dialog、選取三份合成 CSV、送出 | 建立第 2 版，保留第 1 版；檔案清單與新的 fileId 可見，未完整評估仍不能確認。 |

截圖保存於工作區 analysis/backend-runtime/final-local-review/，包括 history-regressed.jpg、evaluation-provenance.jpg 與 filing-multifile.jpg。截圖只含合成資料。

這次沒有輸入私人金鑰，也沒有呼叫付費模型。瀏覽器驗收不代表完整官方規則或真實 LLM 成績已通過。

## 後續真實模型驗收

使用者填入自己的 OpenRouter 設定後，另開隔離資料庫及本機前端 15174／API 18108，使用合成壽險資料完成[真實模型流程](evaluation/2026-10-29-live-system-e2e.md)。瀏覽器顯示 `deepseek/deepseek-v4-flash`、異動序號 `00000`、通過規則重驗與手冊頁碼。此畫面讀取已持久化的真實模型結果，沒有再次呼叫模型。畫面保存在忽略的 `logs/live-evaluation/20261029-192152/e2e-ui-ai.png`。

評測畫面另補全部樣本的端到端分數、模型可用率及呼叫失敗數；排除失敗的條件分數有獨立標示。前端回歸檢查為 7 tests passed，Node 24 TypeScript／Vite build 通過。
