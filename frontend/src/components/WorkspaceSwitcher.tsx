import { useEffect, useRef, useState } from "react";
import { useIsMutating, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useMatch, useNavigate } from "react-router-dom";
import { Check, ChevronDown, FlaskConical, Files } from "lucide-react";
import { reportsApi } from "../api/reports";
import {
  ensureSceneReport,
  LIFE_SCENE_NAME,
  type WorkspaceScene,
} from "../utils/workspaceScenes";
import "./workspace-mechanisms.css";

export function useWorkspaceScenes() {
  const location = useLocation();
  const navigate = useNavigate();
  const match = useMatch("/reports/:reportId/*");
  const reportId = match?.params.reportId ?? "";
  const client = useQueryClient();
  const report = useQuery({
    queryKey: ["report", reportId],
    queryFn: () => reportsApi.get(reportId),
    enabled: Boolean(reportId),
  });
  const uploading =
    useIsMutating({
      predicate: (mutation) =>
        ["upload-version", "create-report"].includes(
          String(mutation.options.mutationKey?.[0]),
        ),
    }) > 0;
  const [phase, setPhase] = useState<"out" | "in" | null>(null);
  const [error, setError] = useState("");
  const gate = useRef(false);
  const generation = useRef(0);
  const path = useRef(location.pathname);
  path.current = location.pathname;
  useEffect(
    () => () => {
      generation.current += 1;
    },
    [],
  );
  useEffect(() => {
    if (phase !== "in") return;
    const timer = window.setTimeout(
      () => setPhase(null),
      window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 480,
    );
    return () => window.clearTimeout(timer);
  }, [phase]);
  const select = async (scene: WorkspaceScene) => {
    if (gate.current || phase || uploading) return;
    const current = report.data;
    if (
      (scene === "demo" && current?.id === "reserve-202609") ||
      (scene === "life" && current?.name === LIFE_SCENE_NAME)
    )
      return;
    gate.current = true;
    const request = ++generation.current;
    const initialPath = path.current;
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)")
      .matches
      ? 0
      : 460;
    const started = performance.now();
    setError("");
    setPhase("out");
    try {
      const target = await ensureSceneReport(scene, reportsApi, async () => {
        const response = await fetch("/workspace-life-demo.csv");
        if (!response.ok) throw new Error("示範資料載入失敗");
        return response.text();
      });
      await new Promise((resolve) =>
        window.setTimeout(
          resolve,
          Math.max(0, duration - (performance.now() - started)),
        ),
      );
      if (request !== generation.current) return;
      if (path.current !== initialPath) {
        setPhase(null);
        return;
      }
      client.setQueryData(["report", target.id], target);
      void client.invalidateQueries({ queryKey: ["reports"] });
      navigate(`/reports/${encodeURIComponent(target.id)}`);
      window.scrollTo(0, 0);
      setPhase("in");
    } catch {
      if (request !== generation.current) return;
      if (path.current !== initialPath) {
        setPhase(null);
        return;
      }
      setError("場景未能載入，已保留目前報表。請稍後重試。");
      setPhase("in");
    } finally {
      gate.current = false;
    }
  };
  return {
    phase,
    error,
    select,
    uploading,
    busy: Boolean(phase),
    label:
      report.data?.name === LIFE_SCENE_NAME
        ? "壽險檢核實驗室"
        : report.data?.id === "reserve-202609"
          ? "展示工作空間"
          : (report.data?.name ?? "展示工作空間"),
    current:
      report.data?.name === LIFE_SCENE_NAME
        ? "life"
        : report.data?.id === "reserve-202609"
          ? "demo"
          : null,
  };
}

type Props = {
  label: string;
  current: string | null;
  busy: boolean;
  uploading: boolean;
  compact?: boolean;
  onSelect: (scene: WorkspaceScene) => void;
};
export function WorkspaceSwitcher({
  label,
  current,
  busy,
  uploading,
  compact = false,
  onSelect,
}: Props) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const firstOption = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    firstOption.current?.focus();
    const outside = (event: PointerEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    window.addEventListener("pointerdown", outside);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("pointerdown", outside);
      window.removeEventListener("keydown", key);
    };
  }, [open]);
  const choose = (scene: WorkspaceScene) => {
    setOpen(false);
    button.current?.focus();
    onSelect(scene);
  };
  return (
    <div
      ref={container}
      className={`workspace-switcher ${compact ? "compact" : ""}`}
    >
      <button
        ref={button}
        className={`profile workspace-profile ${busy ? "is-switching" : ""}`}
        onClick={() => setOpen(!open)}
        disabled={busy || uploading}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={`切換展示場景，目前是${label}`}
        title={uploading ? "上傳完成後可切換場景" : "切換展示場景"}
      >
        <span className="avatar" data-pipeline-sink={compact ? undefined : ""}>
          OW
        </span>
        <span className="workspace-profile-label">
          {label}
          <small>{busy ? "正在切換場景…" : "本機沙盒 · 合成資料"}</small>
        </span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && (
        <div
          className="workspace-picker"
          role="dialog"
          aria-label="切換展示場景"
        >
          <div className="workspace-picker-title">
            <span>WORKSPACE SCENES</span>
            <strong>選一個展示場景</strong>
          </div>
          <button
            ref={firstOption}
            onClick={() => choose("demo")}
            className={current === "demo" ? "selected" : ""}
          >
            <Files size={18} aria-hidden="true" />
            <span>
              展示工作空間<small>準備金檢核 · 版本比較</small>
            </span>
            {current === "demo" && <Check size={15} aria-hidden="true" />}
          </button>
          <button
            onClick={() => choose("life")}
            className={current === "life" ? "selected" : ""}
          >
            <FlaskConical size={18} aria-hidden="true" />
            <span>
              壽險檢核實驗室<small>合成壽險資料 · 不同報表</small>
            </span>
            {current === "life" && <Check size={15} aria-hidden="true" />}
          </button>
          <p>
            展示場景共用本機沙盒，並非正式申報環境。首次開啟實驗室會建立一份合成報表。
          </p>
        </div>
      )}
    </div>
  );
}
