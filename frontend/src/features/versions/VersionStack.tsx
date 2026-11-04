import type { Version } from "../../types";
import { issueAffectsRow } from "../../utils/reportData";

const MAX_CARDS = 5;
const MAX_DOTS = 24;

/**
 * 2.5D stack of version cards: every upload is a separate, unchangeable layer. The version
 * being viewed lifts to the top; the rest sink and fade. Each card's dots are its rows,
 * red where that version had an error.
 */
export function VersionStack({
  versions,
  currentId,
  latestId,
  onSelect,
}: {
  versions: Version[];
  currentId: string;
  latestId: string;
  onSelect: (versionId: string) => void;
}) {
  const shown = [...versions].sort((a, b) => a.number - b.number).slice(-MAX_CARDS);
  return (
    <div className="version-stack" role="group" aria-label="版本堆疊">
      {shown.map((version, index) => {
        const current = version.id === currentId;
        const rows = version.rows.slice(0, MAX_DOTS);
        return (
          <button
            key={version.id}
            className={`stack-card ${current ? "current" : ""}`}
            style={{ "--layer": index } as React.CSSProperties}
            aria-current={current ? "true" : undefined}
            aria-label={`第 ${version.number} 版${version.id === latestId ? "（最新）" : ""}，${version.issues.length} 個錯誤`}
            onClick={() => onSelect(version.id)}
          >
            <span className="stack-card-head">
              <strong>V{version.number}</strong>
              <span>{version.issues.length ? `${version.issues.length} 錯` : "全過"}</span>
            </span>
            <span className="stack-dots" aria-hidden="true">
              {rows.map((row) => (
                <i
                  key={row.id}
                  className={version.issues.some((issue) => issueAffectsRow(issue, row)) ? "bad" : ""}
                />
              ))}
            </span>
          </button>
        );
      })}
    </div>
  );
}
