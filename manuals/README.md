# 填報手冊

把主辦方提供的填報手冊放在這個資料夾。手冊本身**不進版控**（`.gitignore` 已排除），只有這份說明會提交。

目前用到的手冊與險別對應寫在 [`config/manuals.json`](../config/manuals.json)：

| 檔名 | 險別 |
|---|---|
| 新式個人壽險填報說明手冊範例&檢核規則_2025.pdf.pdf | 個人壽險 |
| 附件二_人壽保險業個人壽險填報手冊_2025填報年度.pdf | 個人壽險 |
| 個人年金保險填報手冊.pdf | 個人年金 |
| 新式傷害保險填報手冊.docx | 傷害保險 |
| 新式癌症保險填報手冊_2024.pdf | 癌症保險 |

放好後建立知識庫（約 1 分鐘）：

```bash
.venv/Scripts/python -m once_wrong_ai.kb.build config/manuals.json
```
