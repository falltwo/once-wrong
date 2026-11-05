// Dev-only sample for previewing the manual-evidence view. Loaded by default in
// `npm run dev` (off with ?evidenceDemo=0); production builds never import it. The excerpt is the life-insurance rules
// manual text for L0302 as extracted by the knowledge base, not an invented passage.
import type { Citation, Issue, Suggestion } from "../types";

const L0302: Citation = {
  id: "LIFE-RULE-DEMO",
  source: "新式個人壽險填報說明手冊範例&檢核規則 2025（示範資料）",
  section: ["伍、資料欄位檢核", "異動序號"],
  page: 46,
  excerpt:
    "1.\n(一)保單只有一筆時 ,異動序號(欄 3)= 00000\n(二)保單有兩筆以上異動時,第一筆異動序號(欄 3)= 00001,其他要依序號\n排列 ,即 00001,00002,00003",
  quote: "(二)保單有兩筆以上異動時,第一筆異動序號(欄 3)= 00001,其他要依序號\n排列 ,即 00001,00002,00003",
  pdfUrl: null,
};

const UNQUOTED: Citation = {
  ...L0302,
  id: "LIFE-RULE-DEMO-2",
  section: ["伍、資料欄位檢核"],
  quote: null,
};

export function withDemoEvidence(issue: Issue, suggestion: Suggestion): Suggestion {
  // A sample verified fix for the demo's blank product code (R-01), so the inline fix pill
  // can be previewed without an AI key. R-07 gets none: the system cannot tell which of
  // the two amounts is wrong, and the demo must not pretend otherwise.
  const demoFix =
    issue.ruleId === "R-01" && issue.rowId && !suggestion.suggestion
      ? {
          suggestion: {
            reason: "（示範資料）假設已向來源核對險種代碼",
            verification: "passed" as const,
            changes: [{ rowId: issue.rowId, row: 0, column: "product", value: "CR-04" }],
          },
          verification: "passed" as const,
        }
      : {};
  return {
    ...suggestion,
    ...demoFix,
    citations: [...suggestion.citations, L0302, UNQUOTED],
    rejectedQuotes: [...(suggestion.rejectedQuotes ?? []), `${issue.ruleId} 的示範：對不上原文的句子`],
  };
}
