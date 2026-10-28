# 手冊離線參照

這些填報手冊由專案使用，未隨本 repo 公開散布。請私下向組長取得授權使用的副本；本文件與 JSON 不包含主辦方 Drive 連結或可還原連結的檔案 ID。

完整 SHA-256 以 [external_references.json](external_references.json) 為準。以下 alias 只供資料包內交叉引用，不是下載或存取識別碼：

| 內部 alias | 本地相對檔名 |
| --- | --- |
| `MANUAL-CANCER-2024` | `official-materials/cancer-manual-2024.pdf` |
| `MANUAL-ACCIDENT` | `official-materials/accident-manual.docx` |
| `MANUAL-ANNUITY` | `official-materials/annuity-manual.pdf` |
| `MANUAL-LIFE-2025` | `official-materials/life-manual-2025.pdf` |
| `RULES-LIFE-2025` | `official-materials/life-rules-2025.pdf` |

規則與案例保存各手冊的雜湊、頁碼／章節及來源規則代碼，以便持有相同版本的團隊成員核對。未取得手冊時，可執行不連網的資料契約檢查，但不能宣稱已核對原文證據。

將手冊放在 repo 之外，例如 `C:/team-private/once-wrong/official-materials/`，再從 repo 根目錄執行：

```sh
python datasets/contracts/2026-10-28/verify_dataset.py --reference-root C:/team-private/once-wrong --require-reference-evidence
```

`--reference-root` 是內含 `official-materials/` 的上層目錄，不是手冊資料夾本身。檔案缺少或雜湊不符時，嚴格模式失敗；不要為了讓檢查通過而直接更新既有雜湊，應先確認是否取得正確版本。
