# 規則資料交接

本次交付是 12 項待覆核規則解讀、24 筆合成案例及 pytest fixtures。目標是支援固定規則引擎，不提供合約比較、條款問答或模型訓練流程。來源條款若日後用於 AI 說明，待規則引擎成形後另行討論。

## 1. 安裝測試依賴

需要 Python 3.11 以上，以下命令在 repo 根目錄執行：

```sh
python -m pip install -r datasets/contracts/2026-10-28/requirements.txt
```

僅需 pytest。資料契約檢查使用 Python 標準函式庫，不需模型 SDK 或金鑰。

## 2. 不連網檢查

```sh
python datasets/contracts/2026-10-28/verify_dataset.py
python -m pytest datasets/contracts/2026-10-28/tests -q
```

這些命令不下載檔案、不呼叫 AI，也不要求本機存在 `originals/` 或主辦方手冊。摘要預設輸出至已忽略的 `generated/validation_summary.json`，可用 `--output-summary` 指定其他本地路徑。

通過代表資料契約、引用 metadata 與公開內容檢查通過，不表示這 12 條業務規則已由引擎執行。標籤全部仍為草稿，須人工覆核。

## 3. 有授權手冊時核對原檔

依 [PROJECT_REFERENCES.md](PROJECT_REFERENCES.md) 私下取得正確版本，另執行：

```sh
python datasets/contracts/2026-10-28/verify_dataset.py --reference-root C:/team-private/once-wrong --require-reference-evidence
```

嚴格模式要求本地外部參照齊全且雜湊一致；頁碼／章節是否正確支持規則解讀，仍須人工查閱。

## 4. 接入正式規則引擎

1. 覆核 `rule_inventory.json` 的適用條件、必要輸入、來源版本與歧義。來源衝突或必要依據不足時，維持無法判定。
2. 在規則引擎實作經確認的規則，依內部 `rule_id` 配對案例；以 `source_evidence[].source_codes` 連接手冊檢核代碼，並同時核對來源版本及頁碼，不能假設代碼全域唯一。壽險給付種類對應 `D0102`。年金保證類型衝突的來源頁只標示重複的 `L`，因此代碼留空並以頁碼／列次定位；在官方釐清前不建立代碼對應，保留 `NOT_EVALUATED`。
3. 使用 `tests/conftest.py` 的參數化 `rule_case` fixture 將 `records` 交給引擎，以 `expected_status` 與必要 Finding 作斷言。fixture 的測試 ID 對應 `case_id`，方便定位。
4. 在實際引擎測試接通前，不將目前的資料契約測試宣稱為業務規則驗收。案例中的預期結果不能當成引擎輸入或直接回傳值。

本資料包的 normalized JSON 不是可直接上傳的 demo CSV，也不是官方定長 TXT；轉接層需在正式資料格式確定後另行實作。
