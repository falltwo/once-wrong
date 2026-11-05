import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  ArrowDownToLine,
  Check,
  ChevronRight,
  CircleHelp,
  Files,
  LampDesk,
  LayoutDashboard,
  ChartNoAxesCombined,
} from "lucide-react";
import { Dialog } from "./Dialog";
import { AmbientLibrary } from "./AmbientLibrary";
import { MagneticNavLink } from "./MagneticNavLink";
import { AuditStream } from "./AuditStream";
import { WorkspaceSwitcher, useWorkspaceScenes } from "./WorkspaceSwitcher";
import { DataPipeline } from "./DataPipeline";

const ARCHIVE_KEY = "ow-archive-mode";
const readArchive = () => {
  try {
    return window.localStorage.getItem(ARCHIVE_KEY) === "on";
  } catch {
    return false;
  }
};

export function Shell({ children }: { children: React.ReactNode }) {
  const [help, setHelp] = useState(false);
  // Archive mode: dark library backdrop for demos; remembered per browser, off by default.
  const [archive, setArchive] = useState(readArchive);
  const toggleArchive = () => {
    const next = !archive;
    setArchive(next);
    try {
      window.localStorage.setItem(ARCHIVE_KEY, next ? "on" : "off");
    } catch {
      // Storage can be blocked; the toggle still works for this visit.
    }
  };
  const location = useLocation();
  const scenes = useWorkspaceScenes();
  return (
    <div className={`app-shell ${archive ? "archive-mode" : ""}`}>
      {archive && <AmbientLibrary />}
      <aside className="sidebar">
        <Link to="/reports" className="brand">
          <span className="brand-mark">
            <Check size={22} />
          </span>
          <span>
            Once Wrong<span className="brand-sub">資料品質檢核助手</span>
          </span>
        </Link>
        <div className="workspace-label">WORKSPACE</div>
        <nav aria-label="主要導覽">
          <MagneticNavLink to="/reports" icon={<LayoutDashboard size={18} />}>
            報表檢核
          </MagneticNavLink>
          <MagneticNavLink
            to="/evaluation"
            icon={<ChartNoAxesCombined size={18} />}
          >
            測試結果
          </MagneticNavLink>
        </nav>
        <AuditStream />
        <div className="sidebar-bottom">
          <button onClick={() => setHelp(true)}>
            <CircleHelp size={18} />
            使用說明
          </button>
          <WorkspaceSwitcher
            label={scenes.label}
            current={scenes.current}
            busy={scenes.busy}
            uploading={scenes.uploading}
            onSelect={scenes.select}
          />
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <Files size={16} />
            <Link to="/reports">工作空間</Link>
            <ChevronRight size={13} />
            <span>
              {location.pathname.startsWith("/evaluation")
                ? "測試結果"
                : "報表檢核"}
            </span>
          </div>
          <div className="topbar-actions">
            <WorkspaceSwitcher
              compact
              label={scenes.label}
              current={scenes.current}
              busy={scenes.busy}
              uploading={scenes.uploading}
              onSelect={scenes.select}
            />
            <button
              className={`archive-toggle ${archive ? "on" : ""}`}
              aria-pressed={archive}
              onClick={toggleArchive}
            >
              <LampDesk size={14} aria-hidden="true" />
              檔案館模式
            </button>
            <span className="demo-tag">
              <span />
              後端示範
            </span>
          </div>
        </header>
        {scenes.error && (
          <div className="workspace-switch-error" role="alert">
            {scenes.error}
          </div>
        )}
        <div className="workspace-flip-stage" aria-busy={scenes.busy}>
          {scenes.busy && (
            <div className="workspace-flip-underlay" role="status">
              <span className="flip-underlay-mark">OW</span>
              <strong>正在載入展示場景</strong>
              <small>共用本機沙盒 · 合成資料</small>
            </div>
          )}
          <div
            className={`workspace-flip-surface ${scenes.phase ? `flip-${scenes.phase}` : ""}`}
            inert={scenes.busy}
          >
            {children}
          </div>
        </div>
        <footer className="app-footer">
          <span>Once Wrong · 讓每一次修正，都能被驗證</span>
          <span>後端示範規則 · 僅記錄內部確認，不對外申報</span>
        </footer>
      </div>
      <DataPipeline />
      {help && (
        <Dialog title="開始使用 Once Wrong" onClose={() => setHelp(false)}>
          <p>
            選擇報表後，點擊有錯誤的資料查看檢核說明。修改 CSV
            並重新上傳，即可比較修正結果。
          </p>
          <p>
            示範支援兩條規則：險種代碼不可空白、期初等於上期末。重複錯誤以相同資料
            ID 與規則判定。
          </p>
          <p>
            版本與檢核紀錄儲存在後端。說明使用固定範本；確認僅記錄內部狀態，不會向外部申報。
          </p>
          <a className="button secondary" href="/sample-fixed.csv" download>
            <ArrowDownToLine size={16} />
            下載已修正範例
          </a>
        </Dialog>
      )}
    </div>
  );
}
