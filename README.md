# Once Wrong

> 後端串接底座已加入：啟動與範圍見 [後端 README](backend/README.md)，介面見 [API 契約](docs/backend-api.md)，已執行的流程見 [驗收紀錄](docs/backend-acceptance.md)。下方保留初始立項說明；可執行功能與限制以上述文件為準。前端原型仍由 [PR #1](https://github.com/falltwo/once-wrong/pull/1) 獨立交付。

Cardif InsurHack 2026 題目 6-2「資料品質與檢核助手」的參賽專案。我們想讓報表在送出前說清楚哪裡錯、怎麼改，也能追蹤同一條規則在不同版本的檢核結果。

## 預計怎麼做

- 用規則檢查報表，標出錯誤與版本間的差異。
- 讓 AI 用白話解釋錯誤、提出修正建議；建議要先通過規則重驗，資料仍由人修改。
- 提醒重複未通過的規則，留下每次檢核紀錄，最後由人確認送出。

目前仍在建立原型；後端串接底座已由 [PR #2](https://github.com/falltwo/once-wrong/pull/2) 合併至 main。本分支提供規則資料與測試交接，未將下列 12 項代表性規則接入產品。

## 資料夾

- `docs/`：規則、設計與實驗紀錄。
- `src/`：原型程式。
- `tests/`：規則與流程測試。
- `datasets/contracts/2026-10-28/`：12 項代表性申報規則、24 筆合成案例與 pytest fixtures；從 [規則資料交接](datasets/contracts/2026-10-28/RULE_HANDOFF.md) 開始。

此資料包提供不連網的資料契約檢查；規則與預期標籤仍待人工覆核。原始 PDF、主辦方下載連結、條款語料及模型訓練準備不包含在本次交付。保險公司公開來源僅保留 URL 與 SHA-256，可選擇下載至不追蹤的本機目錄。請勿提交真實保戶資料或金鑰。
