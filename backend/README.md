# Once Wrong 示範檢核 API

FastAPI + SQLite，完成原始 CSV 上傳、不可變版本、後端檢核、歷史查詢及內部確認。資料在重新整理頁面及重啟服務後仍可查詢。

這一版是 `demo_csv_v1` 與 `demo_rules_v1` 的串接底座。只有兩條自訂示範規則，尚未實作官方癌症 CRL/CRD、真實 AI、候選副本重驗或對外申報。沒有帳號權限，請限本機合成資料開發使用。

## 啟動

需求：Python 3.11 或以上。以下指令在 `backend/` 執行。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m uvicorn once_wrong.main:app --host 127.0.0.1 --port 8000
```

macOS / Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m uvicorn once_wrong.main:app --host 127.0.0.1 --port 8000
```

- 健康檢查：<http://127.0.0.1:8000/health>
- OpenAPI操作頁：<http://127.0.0.1:8000/docs>
- 預設SQLite：`backend/data/once_wrong.sqlite3`，不受啟動工作目錄影響。

首次啟動會建立合成報表 `reserve-202609` 的 v1/v2，對應前端 PR #1 的展示資料。Seed 是冪等操作：重啟不會重設已有報表、版本或確認紀錄。正式資料庫遷移、任意新增報表不在本版範圍。

## 設定

支援 `ONCE_WRONG_DB`、`ONCE_WRONG_SEED_DEMO`、`ONCE_WRONG_ALLOWED_ORIGINS`；格式見 [.env.example](.env.example)。設定透過環境變數讀取，程式不會自動載入 `.env`。

預設僅允許 `http://localhost:5173` 與 `http://127.0.0.1:5173` 跨來源存取。若前端另用其他port，請設對應origin後重啟。這不是身分驗證機制。

原始CSV直接以BLOB保存在SQLite，與版本、檢核及SHA-256同一交易提交。資料庫、上傳原值、虛擬環境與本機設定不納入Git。

## CSV與規則

```csv
id,product,previous,opening
POL-001,CR-01,9812400,9812400
POL-003,ML-05,12480000,12005000
POL-004,,1020300,1020300
```

- UTF-8，可含BOM；必要欄為 `id,product,previous,opening`。
- 不超過2 MiB，1至1,000筆非空資料。ID經trim後必須非空且唯一。
- 金額為不含逗號、小數點或指數的非負十進位整數，至多9,007,199,254,740,991；這是相容當前前端number的demo限制，不能用來處理官方18位金額。
- 空白product會成為R-01 Finding，仍建立可供定位的版本；結構或數字無法解析則回422且不建立成功版本。
- R-01：product不可空白；R-07：同列opening必須等於previous。previous也來自同一份CSV，並未核對可信的前期來源。
- repeated僅表示相同rowId + ruleId也出現在緊鄰前一版，不代表完整復發追蹤。

範例：[含錯資料](tests/fixtures/sample-errors.csv)、[修正資料](tests/fixtures/sample-fixed.csv)。

## API與前端串接

完整端點、回傳與錯誤格式見 [API契約](../docs/backend-api.md)。上傳是multipart欄位`file`，同步完成後回201及完整Version，與目前前端上傳成功流程相容。

前端PR #1尚為獨立提交。本PR不複製或合併其程式；提供 [HTTP adapter與最小前端patch](integration/README.md)，可在指定前端commit上進行整合。HTTP模式不讀localStorage，也不會在後端失敗時無聲切回mock。

AI說明端點只回規則固定說明，`verification=unavailable`，沒有候選值或假重驗成功。`submissions`端點僅保存內部確認紀錄：後端重查最新版與規則結果，沒有呼叫外部申報系統。

## 測試

Windows：

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check once_wrong tests
```

POSIX使用`.venv/bin/python`執行相同模組。測試各自使用暫存資料庫，不修改預設展示資料。GitHub Actions會在Linux Python 3.11/3.12及Windows Python 3.12執行。

驗收包含範例錯誤與修正上傳、SHA-256及原始bytes、舊版不可覆寫、重啟持久化、非法輸入、並發版本編號、伺服器確認資格、過期版本拒絕及確認冪等。

瀏覽器整合驗收記錄與重現步驟見 [流程驗收](../docs/backend-acceptance.md)。
