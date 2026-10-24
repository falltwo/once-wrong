import { Link, Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { ReportsPage } from "./pages/ReportsPage";
import { WorkspacePage } from "./pages/WorkspacePage";
import { CheckReportPage } from "./pages/CheckReportPage";
import { TestResultsPage } from "./pages/TestResultsPage";

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route
          path="/"
          element={<Navigate to="/reports/reserve-202609" replace />}
        />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/evaluation" element={<TestResultsPage />} />
        <Route path="/reports/:reportId" element={<WorkspacePage />} />
        <Route path="/reports/:reportId/report" element={<CheckReportPage />} />
        <Route
          path="*"
          element={
            <main className="empty-state">
              <h1>找不到這個頁面</h1>
              <Link to="/reports">回到報表列表</Link>
            </main>
          }
        />
      </Routes>
    </Shell>
  );
}
