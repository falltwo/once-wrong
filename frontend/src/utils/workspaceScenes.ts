import type { Report } from "../types";
import type { reportsApi } from "../api/reports";

export type WorkspaceScene = "demo" | "life";
export const LIFE_SCENE_NAME = "壽險檢核實驗室（合成資料）";

/** These are report scenes sharing one sandbox, never separate tenants or real filing environments. */
export async function ensureSceneReport(
  scene: WorkspaceScene,
  api: Pick<typeof reportsApi, "get" | "list" | "create">,
  loadFixture: () => Promise<string>,
): Promise<Report> {
  if (scene === "demo") return api.get("reserve-202609");
  const reports = await api.list();
  const existing = reports.find(
    (report) => report.name === LIFE_SCENE_NAME && report.period === "2025-10",
  );
  if (existing) return existing;
  const csv = await loadFixture();
  return api.create(
    LIFE_SCENE_NAME,
    "2025-10",
    new File([csv], "workspace-life-demo.csv", { type: "text/csv" }),
  );
}
