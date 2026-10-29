# 交接：AI 審核（feat/ai-review）

上游紀錄：2026-10-28，來源 `feat/ai-review@ea44b2f`。本文件於 2026-10-29 更新本機整合狀態與套件名稱；不表示宥勳的遠端分支已採用改名。下方評分數字屬上游實測，本次 API 整合沒有重新呼叫付費模型。執行契約以 [backend-api.md](backend-api.md) 為準，命名分工見 [AI 套件交接](ai-package-handoff.md)。

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
| 報表與規則介面 | `src/once_wrong_ai/report.py`、`src/once_wrong_ai/rules/` | `Rule.check(report) -> list[Violation]`，組員的規則照這個介面接 |
| AI 審核流程 | `src/once_wrong_ai/ai_review/reviewer.py` | 每筆錯誤：找手冊段落 → 問 Gemini → 修法重驗 → 數字守門 → 稽核紀錄 |
| 修法重驗 | `ai_review/validation.py` | 修法套到副本重跑全部規則；沒修好、產生新錯、改到別列都擋下 |
| 數字守門 | `ai_review/guard.py` | 說明裡的數字要出現在資料、程式算好的數字或 AI 引用的段落，否則整段改用固定說明 |
| Gemini 呼叫 | `ai_review/llm.py` | google-genai SDK，JSON 結構化輸出；失敗時退回固定說明 |
| 填報手冊知識庫 | `src/once_wrong_ai/kb/` | 五本手冊切成 1,485 段（依章節、欄位、代號表），依檢核編號／欄位／表號檢索 |
| 團隊規則備忘 | `kb/memory.py`、`config/rule_notes.jsonl` | 團隊確認過的規則解讀，跟手冊段落一起送給 AI |
| 真實規則範例 | `rules/examples.py` | `life_example_rules()`：個人壽險 L0302、L0303（異動序號），搭配 `examples/mock_life_policies_2025.csv` |
| 個人壽險規則 | `rules/life.py` | `life_field_rules()`：用 8 個承保欄位能檢的 11 條手冊規則（L0302、L0303、L1303、L1304、L1305、L1402、L1502、L1504、L1602、L1607、LU1504） |
| 相關列與同列錯誤 | `Violation.context_rows`、`reviewer.related_violations` | 多筆規則把同一保單其他筆送給 AI（只能看不能改）；同一列的其他錯誤也一起送，讓 AI 給一次修好的建議 |
| 評分 | `src/once_wrong_ai/evaluation/` | 產生規則全過的模擬資料，每個案例弄壞一處，跑 Gemini 後跟原值比對。見下方「評分結果」 |
| API 回應格式 | `ai_review/api.py`、[docs/ai-review-api.md](ai-review-api.md) | 把 AI 審核結果轉成前端 `Suggestion` 的 JSON、任意欄位的錯誤格式；評分輸出 `summary.json`。給後端、前端組員的提案 |
| 測試 | `tests/` | 117 項，用假的 LLM，不需要金鑰 |
| 說明文件 | `docs/ai-review.md` | 架構、介面、設定方式的完整說明 |

## 換電腦後的設定

1. 取得包含本次整合的分支，並在 repo 根目錄確認目前狀態：

   ```bash
   git fetch origin
   git status --short
   ```

2. 建環境並安裝：

   ```bash
   python -m venv .venv
   .venv/Scripts/python -m pip install -e ".[dev]" -e "./backend[dev]"
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
   .venv/Scripts/python -m once_wrong_ai.kb.build config/manuals.json
   ```

5. 複製 `.env.example` 成 `.env`，填 `OPENROUTER_API_KEY`（或 Gemini 的 `GOOGLE_API_KEY`）。
   2026-10-28 的評分用掉了 Gemini 的全部抵免額（gemini-3.5-flash 每次呼叫約 NT$0.44），之後改用 OpenRouter 上較便宜的模型，模型在 `OPENROUTER_MODEL` 換。
   Gemini 的金鑰開頭是 `AQ.` 的新格式會綁一個服務帳戶；出現 `The bound service account is deleted or disabled` 就是那個帳戶被停用，到 AI Studio 重新產生一把即可。

6. 確認：

   ```bash
   .venv/Scripts/python -m pytest
   .venv/Scripts/python -m once_wrong_ai.ai_review.cli examples/mock_life_policies_2025.csv --rules life --product 個人壽險
   # 評分（39 個案例約 4 分鐘；--dry-run 只產生案例不呼叫 AI）
   .venv/Scripts/python -m once_wrong_ai.evaluation.run --cases 39
   ```

## 評分結果（2026-10-28，gemini-3.5-flash）

3 組 seed（1、2、3）各 130 個案例，共 595 筆錯誤，沒有呼叫失敗。三組整體處理正確分別 92%、93%、94%。

| 指標 | 結果 |
|---|---|
| 整體處理正確（推得出就修回原值，推不出就不給修法） | 554/595（93%） |
| 推得出原值時，修回原值 | 420/441（95%） |
| 推不出原值或要動別列時，不亂給修法 | 134/154（87%） |
| 引用到正確規則的手冊段落 | 595/595（100%） |
| AI 說明採用率 | 589/595（99%），其餘被數字守門攔下 |

改進過程（同一組 seed 0、60 筆錯誤）：補上同一列的其他錯誤、日期規則把年月日放進 `facts` 後，整體處理正確從 88% 到 93%，數字守門誤擋從 2 筆到 0 筆。

目前的失誤都不是模型能力問題，而是送給 AI 的資料或提示詞，所以**還不需要訓練模型**。

## 還沒做 / 未驗證

1. **AI 為了讓規則通過而改掉事實或自己編日期。** 評分中約 20 次：退保日漏填時把退保別從身故／解約改成 XED（有效），或把不存在的日期改成月底。規則重驗擋不住這類修法（規則過了但資料是錯的）。計畫：提示詞加一條「不可為了通過檢核改掉代表事實的代號、不可自己編日期，缺資料就請人補」，數字守門接受資料中 8 碼日期拆出的年月日；改完用 seed 1、2、3 重跑對照。
2. **省 token（已討論、尚未實作）。** 實測每筆錯誤約 4,000 token，其中約 75% 是手冊段落；同一條規則錯很多筆時會重複送同一段手冊。計畫：
   - 同一條規則的錯誤合併成一次呼叫（手冊只送一次）
   - 把每條規則的白話說明存起來重用（真正的長期記憶），之後每筆只送出錯的列
   - 手冊段落只送檢核編號附近幾行，不送整頁
   - 使用者點開錯誤才呼叫 AI 與同版本同問題的快取，已由本整合實作；批次合併與提示詞縮減仍未實作。
3. **前端任意欄位。** 後端已支援壽險 rows／cells／facts，前端資料表與錯誤詳情仍須配合；AI 評分需另開區塊呈現，不能與抓錯 precision／recall 混用。另見下一節。
4. **PDF 抽字的限制。** PDF 表格轉文字換行很亂，AI 看得懂但不漂亮；傷害險 docx 有少數格子的內容抽不出來（文字方塊）。
5. **待跟組員確認：** 同一條規則第二次失敗時，是「鎖住送出」（簡報第 7、8 頁）還是「提醒」（README）。

## 2026-10-29 後端整合狀態

本整合將上游 AI 原始碼與後端接在同一環境：

- `feat/backend-validation-api`：FastAPI 後端，套件放在 `backend/once_wrong/`。
  - 建議端點已回完整 Suggestion，依使用者查詢呼叫 AI 並保存快取；LLM 失敗回固定說明且不快取。
  - demo 使用 `id, product, previous, opening` 與 R-01／R-07；壽險用 8 欄文字與 11 條規則。
  - 已補 `POST /reports`、`GET /evaluations/latest`，health 提供 AI 設定狀態。
- `codex/frontend-prototype`：React 前端已有 SuggestionPanel 與建立報表 API 呼叫；壽險畫面與 AI 評分呈現待前端配合。

套件與規則邊界：

- **本機 import 名稱已分開。** 後端為 `once_wrong`，AI 採文件暫定的 `once_wrong_ai`；distribution 分別是 `once-wrong-backend` 與上游原名 `once-wrong`。安裝時同時指定兩個本機路徑。
- **改名由 AI 端維護一次。** 宥勳維護 AI 的 namespace、內部 imports 與 CLI；後端只配合呼叫同一個 AI 套件。現有 `ai-namespace.patch` 可直接沿用，已完成改名時不再次套用，也不建立第二份 AI 目錄。本次未修改或傳訊至宥勳的遠端分支。
- **根目錄檔案已整合。** `.gitignore`、`README.md`、`.env.example` 與 CI 已合併兩邊需求。
- **規則介面要統一。** 後端的規則要能產生本分支的 `Violation`（`rule_id`、`message`、`cells`、`facts`、選填的 `context_rows`），而且 `rule_id` 要用手冊上的檢核編號，知識庫才找得到段落。多筆規則請把同一保單的其他列放進 `context_rows`。
- **`rules/life.py` 是讓 AI 審核和評分先跑起來的實作**，正式版本以組員的規則引擎為準；整合時對一下判斷是否一致。

## 本分支的決定

- **檢索不用向量資料庫。** 檢核編號、欄位名稱、表號都是精確字串，直接比對最準，免金鑰、免費。之後要語意搜尋再在 `Retriever` 加 embedding。
- **CSV 有前置 0 的欄位保留成文字**（公司代號「01」、異動序號「00001」）。
- **只送出錯的列給 AI**，不送整份報表。
- **手冊、知識庫（`data/kb/`）、稽核紀錄（`logs/`）、`.env` 都不進 git。**
