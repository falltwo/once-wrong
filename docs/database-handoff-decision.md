# PR #5 後端決定與回覆草稿

2026-10-29。本機已採用並實作「同次申報、同一不可變版本」；本文件供最後審閱與之後回覆，尚未向 GitHub 發送。

承保、給付及適用的填報對象檔共同構成一個版本，report 依公司＋險種＋填報年度唯一分組。每檔有 version_file，record 連回所屬檔案，跨檔 cells／context 仍只能引用同一版本。每次修訂提供完整快照，保存各原檔 hash，整組以 manifest hash 綁定。上傳／修訂、逐檔下載、三態錯誤歷史、資料庫約束與前端呈現均已接入；舊單檔 API 保持相容。

主鍵依 dataset_type.key_fields 取自各檔自己的資料。涉及主鍵本身的規則用保單群組判定，列號與新上傳 fileId 不影響重複／復發。AI 沿用 #6 的 once_wrong_ai 單一來源，候選及引用寫入正規化審核證據，沒有重建第二套 AI。

現行每檔 1–1,000 筆／2 MiB、未設保留版本數上限。尚未取得真實申報量，#5 的數千至數萬筆、數十版本只保留為容量假設；不能把輸入限制或模擬測試冒稱實際業務規模。擴大前須一併檢查分頁、列表與版本載入。

可回覆組長的文字：

> 後端已在本機接續 #6，採同次申報的檔案共同構成一個不可變版本。report 以公司／險種／年度分組，增加 version_file，record 與 issue cells/context 帶檔案歸屬，保留同版本限制及 manifest 確認。穩定業務鍵與 new／repeated／regressed 已實作並接前端，舊資料會先備份再加法遷移。每檔目前 1,000 筆／2 MiB、沒有保留版本上限；仍缺真實申報量，容量數字先列假設。多檔已有已覆核的規則子集，但未涵蓋完整官方規則的項目會列未評估並擋確認。程式與最後檢查目前留在本機，尚未推送。

原始明文 fields／原檔／備份的正式個資政策仍需團隊決議。本機已先限制 AI 出站欄位、代碼化保單識別，並停止保留完整 prompt；這不等同完成 at-rest 加密與權限管理。

實作與回復方式見[資料庫說明](database-implementation.md)，證據與剩餘限制見[本機驗收](pr5-pr6-local-review-2026-10-29.md)。

- [組長 PR #5 留言](https://github.com/falltwo/once-wrong/pull/5#issuecomment-6475677823)
- [固定版本設計](https://github.com/falltwo/once-wrong/blob/9cf6df4ba169df371b3f68d38ad7a2ccdf3c913a/docs/database/schema-design.md)
- [組長 PR #6 審閱](https://github.com/falltwo/once-wrong/pull/6#issuecomment-6491468213)
