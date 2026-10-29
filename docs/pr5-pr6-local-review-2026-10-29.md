# PR #5／#6 本機處理與最後檢查

2026-10-29，推送前驗收快照。基礎為 feat/ai-api-integration 的 07589fc。完成本文件時變更留在本機，尚未 commit、push、更新 PR、合併或發布留言；之後的提交與 CI 狀態請以 PR #6 為準。

## 本次完成

- 重複判定使用業務鍵，不受換列與新 file UUID 影響；同一保單的主鍵欄位本身出錯時改用群組辨識。
- 已實作 new／repeated／regressed 與首次、前次、修復版號，前端可分別標示、篩選並跳往歷史版本。
- #5 正規化儲存已接入 API：規則 catalog、版本／檔案／資料列、錯誤格子及參考列、候選與引用、不可變證據及 hash 稽核鏈。舊資料先備份再加法遷移，不刪舊表、舊 JSON、bytes 或確認紀錄。
- 同次申報多檔共同形成一個原子版本，按公司／險種／年度分組；逐檔原始 hash 與整組 manifest hash 保存。多檔上傳、下載、跨檔定位與回滾已驗證。
- AI 只改明確出錯格子；保留所有候選排名及 passed／failed／invalid_target。整組重驗不允許新增跨檔錯誤，切換後續候選時也不能繞過數字防護。越界及重複目標不造成 API 失敗。
- fallback 均留審核證據但不快取，舊整列驗證快取不沿用，請求結束後回收鎖。不同公司的同號保單不再合併檢查。
- 模型輸入只帶必要規則欄位，保單識別代碼化，姓名／證件／生日等額外欄位不進 prompt；共享 reviewer 不累積完整 prompt。
- 前端已整合任意欄位、多檔範圍、三態歷史、AI／引用來源與評測模型比對。未完整評估的列不標通過，原因可展開，不能確認。
- 本機核對五份手冊 hash 並建立 1,485 段知識庫；原檔與知識庫均維持 git ignore。
- OpenRouter 來源已核對：功能由宥勳 #4 ea44b2f 先加入，#6 將其設為預設。已移除未經證實的「團隊統一使用」文字，恢復 Gemini／OpenRouter 可選，範例金鑰留空。原始 .pdf.pdf 名稱與來源清單一致。

## 最後驗證

| 檢查 | 結果 |
| --- | --- |
| 後端 API／資料庫全套 | 177 passed |
| AI／規則／真實手冊檢索 | 153 passed，含 OpenRouter 輸出上限設定覆蓋 |
| 前端 contract tests | 7 passed，含完整評測分母 |
| 前端 TypeScript／Node 24 正式打包 | 通過 |
| 新 OpenRouter 金鑰與實際模型直連 | 驗證及模型請求均 HTTP 200；DeepSeek 回覆符合專案 JSON schema，約 2.14 秒；未記錄金鑰 |
| 真實模型系統端到端 | AI 修正、整份重驗、重啟快取、三態歷史、內部確認限制、來源與稽核均通過；另經 Uvicorn HTTP／瀏覽器覆核 |
| 後端 Ruff／修改 AI 檔案的語法、import、升級規則 | 通過；保留既有 Enum 公開字串表示 |
| pip check | 無損壞依賴 |
| wheel 打包 | SQL schema 與新模組均包含，沒有 .env、DB、手冊或知識庫；此額外打包檢查使用 Python 3.13／setuptools 82 |
| 瀏覽器實際操作 | 報表、換列復發、修復版連結、評分來源、多檔範圍／下載／修正版上傳、未評估確認鎖定均通過 |
| 瀏覽器 console | 驗收時未觀察到 error |
| 最後靜態檢查 | diff／相對文件連結／設定與來源模式掃描，另記於本機最終檢查輸出 |

主要測試環境為 Windows Python 3.12.14、Node 24.22.1。後端測試使用合成資料、假模型及隔離 SQLite；受限環境無法建立 Windows socketpair 時改用核准的測試執行環境，沒有因此放寬產品程式。CI 已補前端 Node 24 工作，因未推送尚未執行遠端 CI。

瀏覽器使用隔離 smoke DB、合成 CSV，刻意以無金鑰 OpenRouter 設定展示 Gemini 舊評分與目前模型不同。截圖在工作區 analysis/backend-runtime/final-local-review/；詳細步驟見[瀏覽器驗收](frontend-browser-acceptance.md)。

## 仍不能宣稱已完成的事項

- Demo 模型品質：真實系統審核端到端已通過，見[驗收報告](evaluation/2026-10-29-live-system-e2e.md)。390 案例／595 錯誤的批次依使用者指示停止，保留 83 個完成案例／122 筆完整評分，未發布正式分數；舊 93% 仍屬 Gemini 及當時條件。
- 完整官方申報規則與定長格式：多檔目前只做已核對的規則子集，其他項目列 notEvaluated 並擋確認；不得宣稱可正式對外申報。
- 真實業務容量：每檔目前 1,000 筆／2 MiB、未設保留版本數上限；尚無實際申報量，原估計保留為假設。
- 正式個資 at-rest 加密與權限／保留政策：原始 SQLite 及備份仍是明文來源。本次只完成 AI 出站最小化與 prompt 留存限制，不能等同正式安全政策決議。
- GitHub 回覆、#6 合併與 #4 關閉：均未操作，遵守先留本機最後檢查的指示。

## 交接入口

- [API 契約](backend-api.md)
- [資料庫實作、備份與回復](database-implementation.md)
- [可回覆組長的具體決定與容量說明](database-handoff-decision.md)
- [前端來源與啟動](frontend-local-integration.md)
- [模型供應商沿革](provider-provenance.md)
