# AI 審核模組

負責六步驟裡的第 3、4 步：規則判出錯誤之後，AI 依填報手冊用白話說明，並提出修法；修法先被規則重驗，過了才給人看。

上傳報表（第 1 步）、規則引擎本身、擋重複錯（第 5 步）、送出（第 6 步）不在這個模組。

## 流程

```
報表 ──► RuleSet.check ──► 每一筆 Violation
                               │
             ┌─────────────────┼──────────────────┐
             ▼                 ▼                  ▼
     知識庫：這條規則、    團隊規則備忘       出錯的列＋程式
     欄位說明、代號表     (config/rule_       算好的數字
     (data/kb)            notes.jsonl)
             └─────────────────┼──────────────────┘
                               ▼
         Gemini 回傳：標題、白話說明、最多 3 個修法、引用的段落編號
                               │
          ┌────────────────────┴────────────────────┐
          ▼                                         ▼
 每個修法套到副本重跑全部規則              說明裡的數字逐一比對
 ・同一條規則還沒過 → 擋下                 （資料＋引用的段落＋備忘）
 ・產生新錯誤 → 擋下                       ・有對不上的 → 整段攔下，
 ・改到出錯列以外 → 擋下                     改顯示規則的固定說明
          │                                         │
          └────────────────────┬────────────────────┘
                               ▼
              ReviewItem（含手冊出處）＋ 稽核紀錄（logs/audit.jsonl）
```

Gemini 呼叫失敗時流程不中斷，改顯示規則的固定說明（`source = fallback_llm_error`）。

## 填報手冊知識庫（`once_wrong.kb`）

五本手冊加起來約 100 萬字，不可能每次整本送給 AI。做法是先切段存起來（長期保存，只建一次），審核時每筆錯誤只挑相關的幾段（預設 6,000 字以內）。

**切段**（`kb/ingest.py`）

- 依章節標題記錄每段所在位置，例如「個人壽險填報說明手冊範例與檢核規則 2025 p.46 › 參、欄位檢核 › 一、承保資料欄位檢核」，AI 引用時就能標出處。
- 欄位說明一個欄位一段（PDF 認「4. 異動序號」這類小標，docx 認「欄位+標號」樣式），並標上欄位名稱。
- 代號表（「表3．1．1 公司簡稱與代號表」）單獨成段，標上表號。
- docx 的檢核規則表逐列轉成文字，大致一列一條規則。
- 依章節名稱分類：檢核規則、代號表、欄位說明、範例、其他；目錄不參與檢索。

**檢索**（`kb/search.py`），每筆錯誤依序找：

1. 含這個檢核編號的檢核規則段落（精確比對，`L0302` 不會配到 `L03021`，但會配到 `30201_L0302`）
2. 這條規則附近提到的代號表
3. 出錯欄位的欄位說明
4. 都找不到時，用規則說明全文搜尋（BM25，中文取相鄰兩字）

全部依報表的險別（`report.meta["險別"]`）篩選，不同險別的同名代碼不會混在一起。

沒用向量資料庫：檢核編號、欄位名稱、表號都是精確字串，直接比對最準，而且不用金鑰、不用花錢。之後若要語意搜尋，可以在 `Retriever` 加一層 embedding。

**團隊規則備忘**（`kb/memory.py`，`config/rule_notes.jsonl`）

手冊沒寫清楚、或團隊已經確認過的解讀，記一次就一直用，跟手冊段落一起送給 AI，衝突時以備忘為準。一行一筆，可以直接編輯：

```json
{"rule_id": "L0302", "note": "只有一筆時填 00000，不是 00001。", "product": "個人壽險"}
```

## 給寫規則的人：介面

官方規則寄來之後，每條規則實作 `once_wrong.rules.Rule`，放進 `RuleSet` 就能接上，AI 這層不用改。

```python
class Rule(Protocol):
    rule_id: str          # 用手冊上的檢核編號，例如 "L0302"，知識庫靠它找段落
    description: str      # 規則內容，會送給 AI
    def check(self, report: Report) -> list[Violation]: ...
```

`Violation` 的欄位：

| 欄位 | 用途 |
|---|---|
| `rule_id` | 檢核編號。「同一條規則＋同一批格子」視為同一個錯（`Violation.key`），第 5 步擋重複錯可以直接用 |
| `message` | 固定說明。AI 失敗或被攔下時顯示這段，所以要寫成人看得懂的句子 |
| `cells` | 出錯的格子（列號從 1 開始＋欄名）。AI 的修法只能改這些格子所在的列；欄名也用來找欄位說明 |
| `facts` | **程式算好的數字**，例如差額、筆數、應填的值。AI 只能引用這裡、出錯列、相關列上和手冊段落裡的數字 |
| `context_rows` | 選填。給 AI 參考的相關列，例如多筆檢核時同一保單的其他筆。AI 看得到但不能改，不算進 `key`。單筆檢核不用填 |

多筆檢核（同一保單號碼的前後筆比較，例如 L0303、LU 開頭的規則）如果 `cells` 沒涵蓋同一保單的每一列，請把其他列放進 `context_rows`，不然 AI 只看得到出錯那列，會用猜的。

報表要在 `meta["險別"]` 填上險別（個人壽險／個人年金／傷害保險／癌症保險），跟 `config/manuals.json` 一致。

範例見 [`src/once_wrong/rules/examples.py`](../src/once_wrong/rules/examples.py)：

- `life_example_rules()`：手冊上的真實規則 L0302、L0303（個人壽險異動序號），搭配 `examples/mock_life_policies_2025.csv`
- `example_rules()`：簡報第 8 頁的準備金示意規則，不是主辦方的規則

## 設定與執行

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env    # 填入 GOOGLE_API_KEY
```

| 環境變數 | 說明 |
|---|---|
| `GOOGLE_API_KEY` | Google Cloud 或 AI Studio 的 API 金鑰 |
| `GOOGLE_GENAI_USE_VERTEXAI` | `true` 走 Vertex AI（Google Cloud 專案的金鑰），`false` 走 Gemini API |
| `ONCE_WRONG_MODEL` | 模型名稱，預設 `gemini-3.5-flash` |

建立知識庫（手冊放進 `manuals/`，見 [manuals/README.md](../manuals/README.md)）：

```bash
.venv/Scripts/python -m once_wrong.kb.build config/manuals.json
```

跑個人壽險範例（第 2–6 列有故意埋的錯）：

```bash
.venv/Scripts/python -m once_wrong.ai_review.cli examples/mock_life_policies_2025.csv --rules life --product 個人壽險
```

跑測試（不需要金鑰，用假的 LLM；沒有知識庫時會跳過真實手冊那一項）：

```bash
.venv/Scripts/python -m pytest
```

## 評分（`once_wrong.evaluation`）

用程式產生規則全過的個人壽險承保資料（`rules/life.py` 的 11 條規則），每個案例故意弄壞一處，被改掉之前的值就是標準答案，不用人工標註。13 種弄壞方式涵蓋序號、前後筆接續、加退保別與日期。

```bash
.venv/Scripts/python -m once_wrong.evaluation.run --cases 39 --dry-run   # 只看會產生哪些案例
.venv/Scripts/python -m once_wrong.evaluation.run --cases 130 --seed 1   # 實際跑 Gemini
```

每筆錯誤依「AI 有沒有機會答對」分三類計分：

| 分類 | 意思 | 好的反應 |
|---|---|---|
| 推得出原值 | 送給 AI 的資料裡有線索（序號要連續、加保日要等於上一筆退保日等） | 修回原值 |
| 推不出原值 | 資料裡沒有答案（例如漏填的日期是哪一天） | 不給修法，請人確認 |
| 要動到別列 | 要改 AI 不能改的列才修得好 | 不給修法，請人確認 |

結果寫在 `logs/eval/<時間>/summary.md`。遇到限流會自動等待重試，避免把「沒打到」算成答錯。

## 資料安全

- 送給 Gemini 的只有出錯的列、規則指定的相關列和挑出來的手冊段落，不是整份報表。
- 只能用模擬資料。真實保戶資料不可送外部 AI。
- 手冊、知識庫（`data/kb/`）和稽核紀錄（`logs/`）都排除在 git 之外。
