# 申報規則與合成測試案例

更新日期：2026-10-29。依 PR #3 的審查意見，本資料包縮為 **12 項代表性申報規則與 24 筆合成案例**，供後續規則引擎開發及測試。這些檢核依填報手冊的固定規則判定；本 PR 不包含合約比較、條款問答或模型訓練準備。

資料夾沿用原路徑方便審查，名稱中的 `contracts` 不代表保單條款是申報驗證器的輸入。規則解讀與案例標籤均維持 `agent_draft`，尚待人工領域覆核；12 項規則尚未接入後端。

## 內容

| 檔案 | 用途 |
| --- | --- |
| [rule_inventory.json](rule_inventory.json) | 12 項規則的內部 ID、解讀、適用範圍、必要輸入、歧義及手冊證據 |
| [synthetic_rule_cases.jsonl](synthetic_rule_cases.jsonl) | 24 筆原創 `TEST-` 案例、單條規則的預期結果與缺少的依據 |
| [RULES_AND_CASES.md](RULES_AND_CASES.md) | 標籤語義與目前驗證範圍 |
| [external_references.json](external_references.json) | 5 份手冊的本地檔名、非存取識別碼與 SHA-256 |
| [PROJECT_REFERENCES.md](PROJECT_REFERENCES.md) | 私下取得授權手冊副本及離線核對方式 |
| [verify_dataset.py](verify_dataset.py) | 不連網的資料契約與來源 metadata 檢查；可另核對本地手冊雜湊 |
| [tests/](tests/) | pytest 參數化 fixtures 與資料契約測試 |
| [RULE_HANDOFF.md](RULE_HANDOFF.md) | 安裝、執行與後續接入規則引擎的說明 |

預期結果分布為 `PASS` 8、`FAIL` 6、`NOT_EVALUATED` 8、`NOT_APPLICABLE` 2。每筆只描述一條局部規則，通過不表示整筆申報全面合格。

## 執行

以下命令在 repo 根目錄執行，Python 3.11 以上：

```sh
python -m pip install -r datasets/contracts/2026-10-28/requirements.txt
python datasets/contracts/2026-10-28/verify_dataset.py
python -m pytest datasets/contracts/2026-10-28/tests -q
```

這組檢查不需 AI 金鑰、網路、保險公司 PDF 或主辦方手冊。驗證摘要預設寫入不追蹤的 `generated/validation_summary.json`。若沒有本地手冊，只能確認資料契約與引用 metadata 一致，不能宣稱已重新核對手冊原文。

取得授權手冊後，可額外嚴格核對檔案 SHA-256：

```sh
python datasets/contracts/2026-10-28/verify_dataset.py --reference-root C:/team-private/once-wrong --require-reference-evidence
```

`--reference-root` 指向內含 `official-materials/` 的上層目錄；不使用這個目錄中的檔案更新或取代目前保存的雜湊。

## 公開來源紀錄

[source_manifest.json](source_manifest.json) 僅保留先前 11 份保險公司公開來源的 URL、SHA-256 與下載檔名。PDF 不隨 repo 散布，也不是本資料包或規則驗證的必要依賴。

需要本機查閱這些既有來源時，可明確執行 `python datasets/contracts/2026-10-28/fetch_sources.py`。檔案下載到已忽略的 `originals/`，下載器會核對固定雜湊，來源改版或內容不符時拒絕保存；CI 不執行下載。保留來源紀錄不表示重新散布或模型訓練用途已獲授權。

主辦方手冊只公開內部 alias、檔名、雜湊與頁碼／章節，不公開 Drive 連結或可還原連結的檔案 ID。請私下向組長取得授權使用的副本。

## 後續整合

先覆核規則表與案例預期，再將參數化的 `rule_case` fixture 接到正式規則引擎。現有 pytest 測試驗證資料契約與交接介面，沒有實作這 12 條業務規則，也不把標籤本身當作引擎輸出。

若 AI 之後需要以條款資料輔助說明，等規則引擎成形後另行討論用途及資料範圍。本 PR 的範圍調整基於申報檢核的固定規則與輸入需求。
