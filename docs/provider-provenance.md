# Gemini／OpenRouter 設定沿革

2026-10-29，依 Git 提交及分支內容核對。

| 來源 | 可確認的事實 |
| --- | --- |
| 宥勳的 PR #4、`ea44b2f`（作者 ewiwi） | 首先加入 OpenRouter client、測試及 `.env.example` 的空白 `OPENROUTER_API_KEY`、DeepSeek 模型設定。供應商可選；未明確設定時，有 OpenRouter key 才選 OpenRouter，否則 Gemini。 |
| 後端整合 PR #6、`07589fc`（作者 weck06） | 沿用上游 OpenRouter 功能，另外將範例固定成 `ONCE_WRONG_PROVIDER=openrouter`，並寫入「團隊使用」的文字。這不是共用金鑰的證據。 |
| 前端 PR #1、`e287b1b` | 該分支的後端設定範例只有 Gemini，金鑰留空。 |
| 已提交評測 JSON | 模型為 `gemini-3.5-flash`；沒有從這份成績證明 OpenRouter 模型的表現。 |
| 初次本機驗收環境 | 當時沒有偵測到供應商金鑰環境變數，根目錄與 backend 也沒有 `.env`，該階段未呼叫真實模型。 |

因此，OpenRouter 功能由 AI 分支先加入；把它固定為預設是後端整合時的選擇。無法由空白範例或公開程式碼得知別人的私人環境是否已填入真實金鑰。

後續使用者已在本機根目錄 `.env` 填入自己的 OpenRouter 金鑰，並成功完成驗證與 `deepseek/deepseek-v4-flash` 的小型請求，均為 HTTP 200，回覆符合專案 JSON schema。金鑰沒有寫入本文件或測試紀錄；此結果不代表其他團員有使用同一金鑰，也不是完整模型評測。

同日後續已通過[真實系統端到端驗收](evaluation/2026-10-29-live-system-e2e.md)，包括真實 AI 修法、整份重驗、版本歷史、重啟快取與資料庫稽核。模型品質評測另行記錄；不能由一筆流程成功推論所有建議都正確。

本次已恢復原 AI 分支的可選／自動選擇方式，移除「團隊已統一使用 OpenRouter」的推定。模型名稱與評測來源仍在 API 及畫面清楚顯示；切換模型不會沿用舊成績作新模型宣稱。

- [AI 分支加入 OpenRouter 的提交](https://github.com/falltwo/once-wrong/commit/ea44b2f7744357396bd369bcae54ec3f1d119890)
- [後端整合提交](https://github.com/falltwo/once-wrong/commit/07589fc001efd66d9a9fd6005b494fed8e02fb70)
- [前端分支設定範例](https://github.com/falltwo/once-wrong/blob/e287b1b04c9d8ffc9f3a224da509157cc516f2d4/backend/.env.example)
