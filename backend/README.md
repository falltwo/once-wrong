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

團隊目前使用 OpenRouter，兩份範例已明確設定 `ONCE_WRONG_PROVIDER=openrouter`。在後端的 `.env` 或部署環境填入 `OPENROUTER_API_KEY`，並確認 `OPENROUTER_MODEL`；不需設定 Gemini 金鑰。金鑰不放進前端或 Git。缺少 OpenRouter 金鑰時會回固定說明，不會改呼叫 Gemini。

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

兩種格式均限 UTF-8、2 MiB、1–1,000 列。summary 的 totalChecks 為列數乘規則數，failedChecks 按失敗的規則與列計算。repeated 僅對同 profile 的緊鄰前一版比較同一 issue ID。

```powershell
# 建立報表並上傳第一版：name 1–200 字，period 為 YYYY-MM。
curl.exe -F "name=壽險承保報表" -F "period=2025-10" `
  -F "file=@examples/mock_life_policies_2025.csv" http://127.0.0.1:8000/reports

# 對現有 demo 報表新增版本。
curl.exe -F "file=@backend/tests/fixtures/sample-errors.csv" `
  http://127.0.0.1:8000/reports/reserve-202609/versions
```

`POST /reports` 在同一交易建立報表與第一版，回 201 `Report`。新增版本回 201 `Version`，檔案格式錯誤不留下成功版本。`GET /reports`／`GET /reports/{reportId}` 回傳同樣格式。

`GET /versions/{versionId}/issues/{issueId}/suggestion` 使用 `SuggestionResponse` 完整欄位。AI 只在查詢時呼叫；同步呼叫進 threadpool，SDK／HTTP 網路 timeout 為 30 秒。修法套到副本重跑全部規則並檢查 profile 型別，原始版本不被改寫。成功與數字守門結果以 `(versionId,issueId)` 存 SQLite；LLM 失敗不存。

`GET /evaluations/latest` 回上游 2026-10-28 已有的 Gemini 評分快照，可設定成其他 JSON 路徑。本次整合未產生新的付費 AI 實測；這份評分量的是抓錯後的 AI 說明／修法，不是抓錯 precision／recall。

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

本次 API 與套件驗證結果見 [AI API 整合驗收](../docs/ai-integration-acceptance.md)。前端分支的 Suggestion 型別與 `reportsApi.create()` 已有對應契約；壽險資料表與詳情仍須改為任意欄位與 cells／facts，評分頁須新增 AI 審核評分區塊。本次不包含壽險前端畫面驗收。早期 demo 流程的歷史驗收見 [backend-acceptance.md](../docs/backend-acceptance.md)。
