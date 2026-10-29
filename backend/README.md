# Once Wrong 檢核與 AI 審核 API

FastAPI + SQLite：保存原始 CSV、不可變版本、規則結果與內部確認；依使用者查詢才呼叫 AI，修法通過副本重驗後提供。支援 `demo_csv_v1` 與 8 欄壽險 `life_underwriting_v1`，完整契約見 [API 文件](../docs/backend-api.md)。

## 安裝與啟動

需要 Python 3.11 以上。**所有指令在 repo 根目錄執行**，同時安裝本機 AI 與後端套件，避免只安裝 backend 時去 PyPI 尋找本機 `once-wrong`。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]" -e "./backend[dev]"
Copy-Item .env.example .env
# 編輯 .env，設定模型金鑰或保持空白使用規則固定說明。
.\.venv\Scripts\python -m uvicorn once_wrong.main:app --env-file .env --host 127.0.0.1 --port 8000
```

macOS / Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]' -e './backend[dev]'
cp .env.example .env
.venv/bin/python -m uvicorn once_wrong.main:app --env-file .env --host 127.0.0.1 --port 8000
```

AI 保留上游 distribution 名稱 `once-wrong`，本機整合的 import 採文件暫定名稱 `once_wrong_ai`；後端為 `once-wrong-backend`、import 為 `once_wrong`，可以裝在同一環境。AI 上游來源為 `feat/ai-review@ea44b2f`，包含 Gemini 與 OpenRouter。這是本機整合採用的名稱，不代表宥勳已在遠端分支完成改名；分工與一次性配套見 [AI 套件交接](../docs/ai-package-handoff.md)。

上述安裝指令針對包含 AI 配套的本機整合分支。若只交付後端變更，必須先確保宥勳的 AI 配套可取得並使用相同 import 名稱；目前不假定 PyPI 已發布符合此契約的套件。

- 健康檢查：[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- OpenAPI 操作頁：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- SQLite 預設保存於 `backend/data/once_wrong.sqlite3`。

首次啟動會建立合成報表 `reserve-202609` 的 v1／v2；seed 冪等，重啟不重設資料。用 `ONCE_WRONG_SEED_DEMO=false` 可停用，再由 `POST /reports` 建立報表。

## 設定

範例在根 [.env.example](../.env.example) 與 [backend/.env.example](.env.example)。API 設定以啟動前環境變數為準；以上指令透過 Uvicorn 的 `--env-file .env` 載入，未使用此選項時不應假定 API 設定會從檔案自動載入。

AI 支援 Gemini／OpenRouter，未指定 `ONCE_WRONG_PROVIDER` 時，有 `OPENROUTER_API_KEY` 就選 OpenRouter，否則選 Gemini。也可明確指定供應商；明確指定後缺少該供應商金鑰時回固定說明，不會自動切換。依選擇填入 `OPENROUTER_API_KEY`／`OPENROUTER_MODEL` 或 `GOOGLE_API_KEY`／`ONCE_WRONG_MODEL`，金鑰只放後端環境，不放前端或 Git。設定來源見[沿革核對](../docs/provider-provenance.md)。

| 變數 | 預設／用途 |
| --- | --- |
| `ONCE_WRONG_DB` | 省略時使用 `backend/data/once_wrong.sqlite3`；自訂時建議給絕對路徑 |
| `ONCE_WRONG_SEED_DEMO` | `true` |
| `ONCE_WRONG_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173`，以逗號列出精確 origin |
| `ONCE_WRONG_PROVIDER` | `gemini`／`openrouter`；省略時若有 OpenRouter 金鑰便用 OpenRouter，否則 Gemini |
| `GOOGLE_API_KEY` | Gemini 金鑰；亦接受 `GEMINI_API_KEY` |
| `GOOGLE_GENAI_USE_VERTEXAI` | AI Studio 金鑰用 `false` |
| `ONCE_WRONG_MODEL` | Gemini 預設 `gemini-3.5-flash` |
| `OPENROUTER_API_KEY` | OpenRouter 金鑰 |
| `OPENROUTER_MODEL` | 預設 `deepseek/deepseek-v4-flash`；依模型供應情況自行設定 |
| `OPENROUTER_REASONING` | 選填 `low / medium / high` |
| `OPENROUTER_TEMPERATURE` | 選填；省略時不送此參數 |
| `OPENROUTER_MAX_TOKENS` | 選填正整數輸出上限；本次 Demo 評測使用 2048 |
| `ONCE_WRONG_KB` | `data/kb` |
| `ONCE_WRONG_RULE_MEMORY` | `config/rule_notes.jsonl` |
| `ONCE_WRONG_EVALUATION` | `docs/evaluation/2026-10-28-gemini-3.5-flash.json` |

KB、規則備忘與評分路徑若為相對路徑，一律以 repo 根目錄解析。手冊須自行準備，建立知識庫方式見 [manuals/README.md](../manuals/README.md)：

```powershell
.\.venv\Scripts\python -m once_wrong_ai.kb.build config/manuals.json
```

沒金鑰、AI 逾時或呼叫失敗時，建議端點仍回 200 與完整格式的固定說明，`source=fallback_llm_error`；此結果不快取，下次可以重試。沒有知識庫時仍可審核，引用可為空。`/health` 的 configured 是設定狀態，不保證供應商此刻可用。

## 資料與端點

demo 使用 `id,product,previous,opening`，保留原本 rows／issues 格式。R-01 檢查險種非空，R-07 比較同列期初與上期末，兩條皆為團隊示範規則。金額為非負十進位安全整數，ID 非空且唯一。

壽險 CSV 表頭恰為 `公司代號,保單編號,保單編號序號,異動序號,加保別,加保日期,退保別,退保日期`，欄位次序可不同；資料值皆保留文字。`rows=[{id:"1",row:1,values:{...}}]`，`columns` 保留來源順序，issues 含 cells、facts 與 contextRowIds，套用 11 條 `life_field_rules_v1` 規則。範例見 [mock_life_policies_2025.csv](../examples/mock_life_policies_2025.csv)。

單檔格式均限 UTF-8、2 MiB、1–1,000 列。summary 的 totalChecks 為列數乘規則數，failedChecks 按失敗的規則與列計算。壽險以業務 `issueKey` 比較歷史，不以列號判定；API 提供 new／repeated／regressed、首次／前次／修復版號，舊 repeated 布林保留。啟動會先備份並正規化舊資料，不改寫歷史 JSON／bytes；版本、錯誤、參考列及雜湊稽核鏈由資料庫約束。詳見[資料庫實作與回復](../docs/database-implementation.md)。

多檔版本以重複的 multipart `files` 共同上傳承保、給付及填報對象 CSV，各種類最多一份、每檔仍限 2 MiB／1,000 列。每次修訂提供完整快照，整批原子保存；同公司／險種／年度只保留一個 report。`files` 與 cells 帶檔案定位，逐檔 source 下載並用 manifest hash 綁定整組。範例為 [examples/filing](../examples/filing/README.md)。目前僅執行已覆核的規則子集，未支援或缺檔的檢查列為未評估，不能確認為官方完整申報通過。

```powershell
# 建立報表並上傳第一版：name 1–200 字，period 為 YYYY-MM。
curl.exe -F "name=壽險承保報表" -F "period=2025-10" `
  -F "file=@examples/mock_life_policies_2025.csv" http://127.0.0.1:8000/reports

# 對現有 demo 報表新增版本。
curl.exe -F "file=@backend/tests/fixtures/sample-errors.csv" `
  http://127.0.0.1:8000/reports/reserve-202609/versions
```

`POST /reports` 在同一交易建立報表與第一版，回 201 `Report`。新增版本回 201 `Version`，檔案格式錯誤不留下成功版本。`GET /reports`／`GET /reports/{reportId}` 回傳同樣格式。

`GET /versions/{versionId}/issues/{issueId}/suggestion` 使用 `SuggestionResponse` 完整欄位。AI 只在查詢時呼叫；同步呼叫進 threadpool，SDK／HTTP 網路 timeout 為 30 秒。修法只能改 `violation.cells` 明確指定的格子，並在副本重跑全部規則及檢查 profile 型別；原始版本不被改寫。`source=ai` 結果以 `(versionId,issueId)` 存 SQLite，LLM 失敗與數字守門 fallback 均不快取，可於下次查詢重試。啟動自動補上快取政策版本欄位，避開舊版整列驗證快取；原檔、版本與確認歷史保留。同問題的鎖在使用結束後釋放。

`GET /evaluations/latest` 預設回上游 2026-10-28 的 Gemini 評分快照，可設定成其他 JSON 路徑，另附 `evaluationContext` 比對評測與執行模型。前端把評測模型與分母放在分數旁，舊 93% 不可作為 OpenRouter 模型或目前格子限制政策的成績。2026-10-29 已完成[真實模型端到端驗收](../docs/evaluation/2026-10-29-live-system-e2e.md)；模型評分量的是抓錯後的 AI 說明／修法，不是抓錯 precision／recall。詳細契約見 [API 文件](../docs/backend-api.md)。

`POST /reports/{reportId}/submissions` 僅內部確認，後端重查最新版與規則結果，未向外申報。舊版原檔、版本與確認歷史重啟後仍保留。

## 測試與前端交接

根目錄執行，AI 與 API 測試分開呼叫，避免兩份 conftest 混用：

```powershell
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python -m pytest tests -q
.\.venv\Scripts\python -m pytest backend/tests -q
.\.venv\Scripts\python -m ruff check --config backend/pyproject.toml backend/once_wrong backend/tests
```

測試使用 fake LLM 與隔離資料庫，不需金鑰。GitHub Actions 在 Linux Python 3.11／3.12 與 Windows Python 3.12 執行兩組測試。

最新完整檢查見 [PR #5／#6 本機驗收](../docs/pr5-pr6-local-review-2026-10-29.md)。本機 `frontend/` 已整合任意欄位、三態歷史、多檔定位與評分模型來源，使用 Node 24 啟動及打包；[瀏覽器驗收](../docs/frontend-browser-acceptance.md)記錄實際操作。原 [AI API 整合驗收](../docs/ai-integration-acceptance.md)與 [早期 Demo 驗收](../docs/backend-acceptance.md)保留為歷史資料。
