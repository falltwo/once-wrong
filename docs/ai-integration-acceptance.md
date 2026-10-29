# AI API 整合驗收

日期：2026-10-29。整合基準為後端 `main@a12583e` 與宥勳的
`feat/ai-review@ea44b2f`，本機分支為 `feat/ai-api-integration`。
契約見 [backend-api.md](backend-api.md)，安裝見 [後端 README](../backend/README.md)。

發布時保留 AI 分支的原始提交，namespace 改名、provider runtime 設定與後端 API 整合分開提交。最終程式與檢查過的本機版本逐檔雜湊一致；發布檢查亦涵蓋 Git index 與新增提交歷史，排除金鑰、私人連結、手冊原檔、資料庫及本機產出。

命名調整以 [AI 套件交接](ai-package-handoff.md) 為準：後端保留 `once-wrong-backend`／`once_wrong`，AI 保留上游 pip 名稱 `once-wrong`，本機 import 採暫定的 `once_wrong_ai`。只有一份 AI 來源，未修改宥勳的遠端分支。命名調整後已重新安裝兩個套件並執行下列檢查；安裝 metadata 確認每個 import 均只有一個套件擁有者，舊的 `once-wrong-ai` 安裝已移除。

## 已驗證

| 項目 | 結果 |
| --- | --- |
| 同環境安裝兩個 editable packages | `once_wrong` 後端與 `once_wrong_ai` AI 套件可同時 import，`pip check` 通過 |
| 後端測試 | 70 項通過，包含原本 demo 流程、21 項 API 整合測試與 3 項套件擁有者／單一來源檢查 |
| AI／規則測試 | 129 項通過、1 項略過；略過項須先有本機填報手冊知識庫 |
| Ruff | 後端程式與測試通過 |
| SDK 設定 | 安裝的 Gemini SDK 可建立 30,000ms timeout、單次嘗試設定，無呼叫模型 |
| AI 改名交接 | `ai-namespace.patch` 與 `ai-runtime.patch` 已依序在隔離 Git index 重播，結果與預期 tree 完全一致；未修改宥勳遠端分支 |

新增整合測試使用假的 LLM，覆蓋：完整 Suggestion 欄位、有效修法與原始版本不變、
LLM 錯誤／TimeoutError 的完整 200 fallback 與重試、成功快取跨重啟保存、
未知資源 404、偽造保存的 issue 仍須通過伺服器規則查找、
不合法型別／負值／過大金額／修改 ID 的修法攔截、壽險文字值與前置零、
generic issue／參考列／重複問題／摘要、壽險確認重驗、
原子建立報表及首版、評分 JSON 原樣回傳／缺檔 404、health 與非阻塞 AI 查詢。

```powershell
# repo 根目錄、依 README 安裝兩個套件後執行。
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python -m pytest tests -q
.\.venv\Scripts\python -m pytest backend/tests -q
.\.venv\Scripts\python -m ruff check --config backend/pyproject.toml backend/once_wrong backend/tests
```

## 驗收範圍

本次沒有呼叫付費模型，也未重跑 AI 評分；`docs/evaluation/` 的數據沿用 AI 分支
2026-10-28 的實測快照。沒有知識庫時 API 仍可運作，`ai.knowledgeBase=false`。

前端目前的 Suggestion 型別與建立報表請求已符合後端契約；壽險資料表、
任意欄位錯誤詳情及獨立 AI 評分區塊仍需前端配合。此處完成的是 API 與套件整合驗收。
同一 worker 可合併同問題的冷快取查詢，多 worker 可能各呼叫一次模型。
