import type { CSSProperties } from "react";
import type { Version } from "../../types";

function volumeState(version: Version): string {
  if (version.validationStatus !== "completed" || !version.summary)
    return "待檢核";
  const skipped = version.summary.notEvaluatedChecks ?? 0;
  if (skipped) return `${skipped} 項未檢查`;
  return version.issues.length
    ? `${version.issues.length} 項待修正`
    : "全部通過";
}

export function VersionStack({
  versions,
  currentId,
  latestId,
  onSelect,
  soundEnabled,
  onToggleSound,
}: {
  versions: Version[];
  currentId: string;
  latestId: string;
  onSelect: (versionId: string) => void;
  soundEnabled: boolean;
  onToggleSound: () => void;
}) {
  const ordered = [...versions].sort((a, b) => a.number - b.number);
  const current = ordered.find((item) => item.id === currentId);
  const shown = ordered.slice(-5);
  if (current && !shown.includes(current)) {
    shown[0] = current;
    shown.sort((a, b) => a.number - b.number);
  }
  return (
    <section className="archival-drawer" aria-label="版本控制時光機">
      <div className="archival-caption">
        <span className="archival-kicker">THE ARCHIVAL STACK</span>
        <h2>
          每次修訂，
          <br />
          皆有存卷。
        </h2>
        <p>抽出一冊，回看當時的資料與檢核紀錄。</p>
        <span className="archival-catalog">
          共 {versions.length} 卷 · 原始版本完整保留
        </span>
      </div>
      <div
        className="archival-shelf"
        style={{ "--volume-count": shown.length } as CSSProperties}
      >
        <div className="archival-books" role="group" aria-label="選擇版本">
          {shown.map((version, index) => {
            const selected = version.id === currentId;
            const latest = version.id === latestId;
            return (
              <button
                key={version.id}
                className={`archive-volume ${selected ? "is-drawn" : ""} ${latest ? "is-latest" : ""}`}
                style={
                  {
                    "--volume-order": index,
                    "--volume-z": selected ? 12 : index + 1,
                  } as CSSProperties
                }
                aria-pressed={selected}
                aria-label={`開啟第 ${version.number} 版${latest ? "（最新）" : "（歷史）"}，${volumeState(version)}`}
                onClick={() => onSelect(version.id)}
              >
                <span className="volume-pages" aria-hidden="true" />
                <span className="volume-cover">
                  <span className="volume-binding" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                    <i />
                  </span>
                  <span className="volume-index">
                    VOL. {String(version.number).padStart(2, "0")}
                  </span>
                  <span className="volume-title">
                    資料檢核卷宗<span>第 {version.number} 卷</span>
                  </span>
                  <span className="volume-stamp" aria-hidden="true">
                    {latest ? "新卷" : "存卷"}
                  </span>
                  <span className="volume-bottom">
                    ONCE WRONG ·{" "}
                    {version.createdAt.slice(0, 10).replaceAll("-", ".")}
                  </span>
                </span>
                <span className="volume-tab">
                  V{version.number}
                  {selected ? " · 閱覽中" : latest ? " · 最新" : ""}
                </span>
              </button>
            );
          })}
        </div>
        <span className="archival-shelf-line" aria-hidden="true" />
      </div>
      <div className="archival-reading">
        <span className="archival-reading-label">目前閱覽</span>
        <strong>
          第 <b>{current?.number ?? "—"}</b> 卷
        </strong>
        <span
          className={`archival-version-kind ${currentId !== latestId ? "historical" : ""}`}
        >
          {currentId === latestId ? "最新版本" : "歷史存卷"}
        </span>
        <p>{current ? volumeState(current) : "選擇版本"}</p>
        <button
          className="archive-sound"
          type="button"
          aria-pressed={soundEnabled}
          onClick={onToggleSound}
        >
          <span className="archive-sound-switch" aria-hidden="true">
            <i />
          </span>
          翻頁音效{soundEnabled ? "開啟" : "關閉"}
        </button>
      </div>
    </section>
  );
}
