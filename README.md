# Once Wrong

Cardif InsurHack 2026 題目 6-2「資料品質與檢核助手」原型。上傳 CSV 後由規則指出錯誤，AI 說明與修法需通過規則重驗，再由使用者修正資料；版本與重複錯誤可持續追蹤。

目前支援 demo、8 欄個人壽險承保資料及多檔申報 CSV 子集；具備不可變版本、SQLite 正規化證據、點開問題才呼叫 AI、建議快取及內部確認。AI 可選 Gemini 或 OpenRouter；未設定金鑰時仍提供規則固定說明。本機已整合 [前端 PR](https://github.com/falltwo/once-wrong/pull/1) 的畫面，支援任意欄位、多檔及三態歷史，啟動見[前端整合說明](docs/frontend-local-integration.md)。

AI 支援 Gemini 與 OpenRouter，可用 `ONCE_WRONG_PROVIDER` 明確選擇。未指定時，有 `OPENROUTER_API_KEY` 就使用 OpenRouter，否則使用 Gemini；設定你選用供應商的金鑰即可。兩份範例的金鑰皆留空。供應商支援不代表團隊已共用金鑰，來源見[設定沿革](docs/provider-provenance.md)。

## 啟動

Python 3.11 以上，在 repo 根目錄同時安裝本機 AI 與後端：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]" -e "./backend[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python -m uvicorn once_wrong.main:app --env-file .env --host 127.0.0.1 --port 8000
```

macOS／Linux 使用 `.venv/bin/python`。完整設定、CSV 限制與測試指令見 [後端 README](backend/README.md)，端點與 JSON 契約見 [backend-api.md](docs/backend-api.md)，本次驗證結果見 [AI API 整合驗收](docs/ai-integration-acceptance.md)。

## 程式與文件

- `backend/once_wrong/`：FastAPI、profile adapter、SQLite 與 AI 服務橋接。
- `frontend/`：React／Vite，連接實際報表、AI 建議與評測 API。
- `src/once_wrong_ai/`：AI 審核、手冊檢索、規則介面及評分工具；來源為 `feat/ai-review@ea44b2f`。
- `backend/tests/`、`tests/`：API／持久化與 AI／規則測試，使用 fake LLM。
- `examples/`：可提交的合成 CSV；`config/`：規則備忘與手冊來源設定。
- [AI 模組說明](docs/ai-review.md)、[原始端點提案與整合狀態](docs/ai-review-api.md)、[AI 交接紀錄](docs/handoff-ai-review.md)。

套件分工與避免重複改名的方式見 [AI 套件交接](docs/ai-package-handoff.md)。後端的 pip 名稱為 `once-wrong-backend`、import 為 `once_wrong`；AI 保留宥勳原本的 pip 名稱 `once-wrong`，本機整合的 import 採文件暫定的 `once_wrong_ai`。AI 來源只保留一份，宥勳的遠端分支尚未由本次工作修改。

`docs/evaluation/` 保留各次實測來源；Gemini 舊快照不能作為 DeepSeek 成績。2026-10-29 已完成[真實模型端到端驗收](docs/evaluation/2026-10-29-live-system-e2e.md)。模型評分衡量規則抓到錯誤後的 AI 說明與修法，並非抓錯 precision／recall。

資料庫、手冊原檔、產出的知識庫、稽核紀錄與 `.env` 不納入 Git。範例與測試皆使用合成資料；內部確認端點沒有向外申報。
