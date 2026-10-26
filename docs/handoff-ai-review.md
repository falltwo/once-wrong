# 交接：AI 審核（feat/ai-review）

最後更新：2026-10-27。分支 `feat/ai-review`，從 `main`（7dc863f）切出，尚未合併。

## 背景（換電腦後看這段就夠）

- 比賽：Cardif InsurHack 2026 題目 6-2「資料品質與檢核助手」。初賽交 20 頁企劃書＋3 分鐘原型影片，**截止 2026-11-06 17:00**。
- 評分：實作完整度與體驗 40%、AI 整合 20%、落地與商業 20%、創意 10%、影片 10%。
- 流程六步：上傳 → 規則檢查 → **AI 說明** → **AI 修法先被規則重驗** → 擋重複錯 → 人送出。
- **我負責的只有第 3、4 步（AI 審核）。** 上傳、規則引擎、擋重複錯、送出由組員負責。
- 原則：規則是唯一裁判，AI 只解釋和建議；AI 講的數字必須對得上資料；全程留稽核紀錄。
- 不可沿用舊作 Talent Risk Radar 的程式（一稿多投＋授權不清），只沿用「AI 不准亂講數字」的想法。
- 只能用模擬資料，真實保戶資料不可送外部 AI。
- LLM 用 Gemini，金鑰是 Google Cloud 的 API key。

## 已完成

| 部分 | 位置 | 說明 |
|---|---|---|
| 報表與規則介面 | `src/once_wrong/report.py`、`src/once_wrong/rules/` | `Rule.check(report) -> list[Violation]`，組員的規則照這個介面接 |
| AI 審核流程 | `src/once_wrong/ai_review/reviewer.py` | 每筆錯誤：找手冊段落 → 問 Gemini → 修法重驗 → 數字守門 → 稽核紀錄 |
| 修法重驗 | `ai_review/validation.py` | 修法套到副本重跑全部規則；沒修好、產生新錯、改到別列都擋下 |
| 數字守門 | `ai_review/guard.py` | 說明裡的數字要出現在資料、程式算好的數字或 AI 引用的段落，否則整段改用固定說明 |
| Gemini 呼叫 | `ai_review/llm.py` | google-genai SDK，JSON 結構化輸出；失敗時退回固定說明 |
| 填報手冊知識庫 | `src/once_wrong/kb/` | 五本手冊切成 1,485 段（依章節、欄位、代號表），依檢核編號／欄位／表號檢索 |
| 團隊規則備忘 | `kb/memory.py`、`config/rule_notes.jsonl` | 團隊確認過的規則解讀，跟手冊段落一起送給 AI |
| 真實規則範例 | `rules/examples.py` | 個人壽險 L0302、L0303（異動序號），搭配 `examples/mock_life_policies_2025.csv` |
| 測試 | `tests/` | 34 項，用假的 LLM，不需要金鑰 |
| 說明文件 | `docs/ai-review.md` | 架構、介面、設定方式的完整說明 |

## 換電腦後的設定

1. 拉分支：

   ```bash
   git fetch origin
   git switch feat/ai-review
   ```

2. 建環境並安裝：

   ```bash
   python -m venv .venv
   .venv/Scripts/python -m pip install -e ".[dev]"
   ```

3. **手冊要另外帶過去**（repo 是公開的，手冊不進 git）。把這五個檔案放進 `manuals/`：
   - 新式個人壽險填報說明手冊範例&檢核規則_2025.pdf.pdf
   - 附件二_人壽保險業個人壽險填報手冊_2025填報年度.pdf
   - 個人年金保險填報手冊.pdf
   - 新式傷害保險填報手冊.docx
   - 新式癌症保險填報手冊_2024.pdf

   原本的電腦上，這些在桌面和 `C:\oncewrong\manuals\`。

4. 建知識庫（約 1 分鐘）：

   ```bash
   .venv/Scripts/python -m once_wrong.kb.build config/manuals.json
   ```

5. 複製 `.env.example` 成 `.env`，填 `GOOGLE_API_KEY`。用 Google Cloud 專案金鑰時 `GOOGLE_GENAI_USE_VERTEXAI=true`。

6. 確認：

   ```bash
   .venv/Scripts/python -m pytest
   .venv/Scripts/python -m once_wrong.ai_review.cli examples/mock_life_policies_2025.csv --rules life --product 個人壽險
   ```

## 還沒做 / 未驗證

1. **還沒用真的金鑰呼叫過 Gemini。** 用假金鑰確認過請求格式被接受、錯誤會正確退回；但實際回覆品質、模型名稱 `gemini-3.5-flash` 是否可用都還沒驗證（可用 `ONCE_WRONG_MODEL` 換）。這是換電腦後的第一件事。
2. **省 token（已討論、尚未實作）。** 實測每筆錯誤約 4,000 token，其中約 75% 是手冊段落；同一條規則錯很多筆時會重複送同一段手冊。計畫：
   - 同一條規則的錯誤合併成一次呼叫（手冊只送一次）
   - 把每條規則的白話說明存起來重用（真正的長期記憶），之後每筆只送出錯的列
   - 手冊段落只送檢核編號附近幾行，不送整頁
   - 跟前端約定：使用者點開錯誤時才呼叫 AI
3. **跟後端整合。** 見下一節。
4. **PDF 抽字的限制。** PDF 表格轉文字換行很亂，AI 看得懂但不漂亮；傷害險 docx 有少數格子的內容抽不出來（文字方塊）。
5. **待跟組員確認：** 同一條規則第二次失敗時，是「鎖住送出」（簡報第 7、8 頁）還是「提醒」（README）。

## 跟組員的分支整合時要注意

遠端目前還有兩個分支：

- `feat/backend-validation-api`：FastAPI 後端，套件放在 `backend/once_wrong/`。
  - 它有 `GET /versions/{versionId}/issues/{issueId}/suggestion`，目前固定回 `source=demo`、`verification=unavailable`、不呼叫 LLM。**這就是 AI 審核要接上的地方。**
  - 它的規則是示範用 R-01／R-07，CSV 欄位是 `id, product, previous, opening`，跟本分支的示範欄位（中文欄名）不同。
- `codex/frontend-prototype`：React 前端，有 `SuggestionPanel`。

衝突點：

- **套件名稱撞名。** 後端是 `backend/once_wrong/`，本分支是 `src/once_wrong/`，裝在同一個環境會互相蓋掉。整合時建議把本分支的 `ai_review/`、`kb/` 搬進 `backend/once_wrong/` 底下，或把本分支改名（例如 `once_wrong_ai`）。
- **根目錄檔案。** `.gitignore`、`README.md` 兩邊都有改，合併時要手動整理。
- **規則介面要統一。** 後端的規則要能產生本分支的 `Violation`（`rule_id`、`message`、`cells`、`facts`），而且 `rule_id` 要用手冊上的檢核編號，知識庫才找得到段落。

## 本分支的決定

- **檢索不用向量資料庫。** 檢核編號、欄位名稱、表號都是精確字串，直接比對最準，免金鑰、免費。之後要語意搜尋再在 `Retriever` 加 embedding。
- **CSV 有前置 0 的欄位保留成文字**（公司代號「01」、異動序號「00001」）。
- **只送出錯的列給 AI**，不送整份報表。
- **手冊、知識庫（`data/kb/`）、稽核紀錄（`logs/`）、`.env` 都不進 git。**
