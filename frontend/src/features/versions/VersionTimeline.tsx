import { Hint } from "../../components/Hint";
import type { Issue, Version } from "../../types";
import { date } from "../../utils/format";

type Health = "pass" | "improving" | "failing";

const healthLabels: Record<Health, string> = {
  pass: "全部通過",
  improving: "錯誤減少中",
  failing: "仍有錯誤",
};

const issueKey = (issue: Issue) => issue.issueKey ?? issue.id;

/** 每一版的健康度與跟上一版相比修好、新增了幾個錯（用 issueKey 比對，不看列號）。 */
export function versionStats(versions: Version[]) {
  return versions.map((version, index) => {
    const previous = versions[index - 1];
    const current = new Set(version.issues.map(issueKey));
    const before = new Set(previous?.issues.map(issueKey) ?? []);
    const fixed = [...before].filter((key) => !current.has(key)).length;
    const added = [...current].filter((key) => !before.has(key)).length;
    const errors = version.issues.length;
    const health: Health =
      errors === 0 && (version.summary?.notEvaluatedChecks ?? 0) === 0
        ? "pass"
        : previous && errors < previous.issues.length
          ? "improving"
          : "failing";
    return { version, errors, fixed, added, health, hasPrevious: Boolean(previous) };
  });
}

export function VersionTimeline({
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
  const ordered = [...versions].sort((a, b) => a.number - b.number);
  return (
    <ol className="version-timeline" aria-label="報表版本">
      {versionStats(ordered).map(({ version, errors, fixed, added, health, hasPrevious }) => {
        const summary = [
          `${errors} 個錯誤`,
          hasPrevious ? `修好上一版 ${fixed} 個` : "第一次上傳",
          hasPrevious && added ? `新增 ${added} 個` : "",
        ]
          .filter(Boolean)
          .join("，");
        const current = version.id === currentId;
        return (
          <li key={version.id} className={`timeline-node ${health}`}>
            <Hint
              content={
                <span className="hint-lines">
                  <strong>
                    第 {version.number} 版{version.id === latestId ? "（最新）" : ""} · {healthLabels[health]}
                  </strong>
                  <span>{date(version.createdAt)}</span>
                  <span>{summary}</span>
                </span>
              }
            >
              <button
                aria-current={current ? "true" : undefined}
                aria-label={`V${version.number}，第 ${version.number} 版${version.id === latestId ? "（最新）" : ""}：${healthLabels[health]}，${summary}`}
                onClick={() => onSelect(version.id)}
              >
                <span className="timeline-dot" aria-hidden="true" />
                <span className="timeline-label" aria-hidden="true">
                  V{version.number}
                </span>
              </button>
            </Hint>
          </li>
        );
      })}
    </ol>
  );
}
