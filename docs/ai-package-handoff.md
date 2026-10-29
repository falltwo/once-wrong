# AI 套件命名與分工

日期：2026-10-29。已比對宥勳的 `feat/ai-review@ea44b2f` 與本機整合分支。目前本機只有 `backend/once_wrong/` 和 `src/once_wrong_ai/`，沒有兩份同名套件；重疊的是兩邊先後處理了同一項 AI 改名工作。

## 單一命名契約

| 部分 | pip distribution | Python import | 原始碼位置 | 維護範圍 |
| --- | --- | --- | --- | --- |
| 後端 | `once-wrong-backend` | `once_wrong` | `backend/once_wrong/` | 後端 API、儲存、profile adapter 與 AI 呼叫端 |
| AI | `once-wrong` | `once_wrong_ai` | `src/once_wrong_ai/` | 由宥勳維護 namespace、AI 內部 imports、CLI 與 AI 流程 |

原文件寫的是「AI 這邊會把 `src/once_wrong` 改名（暫定 `once_wrong_ai`）」。因此後端名稱維持原樣；本機整合先採用這個暫定 AI import 名稱，pip 安裝名稱則保留上游原本的 `once-wrong`，不另新增一個安裝名稱。

截至上述比對的上游提交，AI 仍在 `src/once_wrong/`。本次工作沒有修改或傳訊至宥勳的遠端分支，也不代表他已確認最終名稱或採用本機配套。

## 只採用一次改名配套

交接提供兩份分開的 patch，依序處理：

- `ai-namespace.patch`：以 `ea44b2f` 為基準，包含 AI 目錄改名、內部與測試 imports、CLI 入口，以及明確限定 AI 套件的 package discovery。pip 名稱維持 `once-wrong`。
- `ai-runtime.patch`：以已套用 namespace 補丁的來源為基準，包含 `httpx` 依賴、同步網路呼叫的 timeout 配套與對應測試；這些不屬於命名，於改名後另行檢視及選擇採用。

本整合分支已真正合併 AI 上游提交並保留其作者紀錄，以上配套也各自成為獨立提交，可直接檢視或沿用：[namespace 改名](https://github.com/falltwo/once-wrong/commit/77e721dd4659ca7576e1b5f491114ae71dcb4c4e)、[HTTP 依賴與 timeout](https://github.com/falltwo/once-wrong/commit/286a5bce9b02a527750e02229d870e4c3e0f85b9)。尚未改名的 AI 工作分支可在取得本整合分支後，依序 cherry-pick 這兩筆；已完成相同改名者先比較差異，勿重複套用。本 PR 不包含第二份相容舊名的 AI 原始碼。

由 AI 端檢查並沿用這份改名配套，可避免再獨立做一次相同工作。如果宥勳已完成改名，先比對結果，不再套用 `ai-namespace.patch`。補丁基準之後若有新提交，先執行 `git apply --check` 並處理實際差異，不強制套用。

不要同時保留舊 `src/once_wrong/` 與新 `src/once_wrong_ai/`，也不要再改成 `once_wrong_ai_ai` 或另複製一份到後端。後端只 import 同一份 `once_wrong_ai`，不維護另一套 AI 原始碼。

## 安裝與交付順序

目前包含 AI 配套的本機整合分支可持續測試，在 repo 根目錄同時安裝兩個本機套件：

```sh
python -m pip install -e '.[dev]' -e './backend[dev]'
python -m pip check
python -m pytest tests -q
python -m pytest backend/tests -q
```

根 `pyproject.toml` 只發現 `once_wrong_ai` 與其子套件；後端 `pyproject.toml` 只發現 `once_wrong` 與其子套件。整合測試會確認實際安裝的 metadata、module 來源及來源目錄沒有重複套件。

若要只發布後端自己的變更，AI 改名配套必須先存在於可供團隊取得的依賴中，並符合上述 import 契約；目前不假定 PyPI 已發布這個配套。後端 PR 應標明所依賴的 AI 提交，避免將尚未具備 AI 配套的分支當成可獨立安裝版本。

名稱與配套對齊後，後續 AI 流程修改回到宥勳維護的來源；後端只更新自己的 adapter 與回應契約。這份分工和檢查可阻擋重複目錄，不能取代未來上游變更的正常合併與測試。
