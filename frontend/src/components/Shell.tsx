import { useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import {
  ArrowDownToLine,
  Check,
  ChevronRight,
  CircleHelp,
  Files,
  LayoutDashboard,
  ChartNoAxesCombined,
  ShieldCheck,
} from "lucide-react";
import { Dialog } from "./Dialog";

export function Shell({ children }: { children: React.ReactNode }) {
  const [help, setHelp] = useState(false);
  const location = useLocation();
  return (
    <div className="app-shell">
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
        <nav>
          <NavLink
            to="/reports"
            className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
          >
            <LayoutDashboard size={18} />
            報表檢核
          </NavLink>
          <NavLink
            to="/evaluation"
            className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
          >
            <ChartNoAxesCombined size={18} />
            測試結果
          </NavLink>
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={24} />
          <strong>每次修正，都有依據。</strong>
          <p>
            規則把關，AI 說明。
            <br />
            讓下一版更接近正確。
          </p>
        </div>
        <div className="sidebar-bottom">
          <button onClick={() => setHelp(true)}>
            <CircleHelp size={18} />
            使用說明
          </button>
          <div className="profile">
            <span className="avatar">OW</span>
            <div>
              展示工作空間<small>前端原型 · 本機資料</small>
            </div>
            <span className="online-dot" />
          </div>
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
          <span className="demo-tag">
            <span />
            示範模式
          </span>
        </header>
        {children}
        <footer className="app-footer">
          <span>Once Wrong · 讓每一次修正，都能被驗證</span>
          <span>模擬資料與規則 · 未連接正式申報系統</span>
        </footer>
      </div>
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
            資料僅儲存在目前瀏覽器。AI 說明為示範範本；送出僅記錄本機確認狀態。
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
