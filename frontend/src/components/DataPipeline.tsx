import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import {
  subscribePipelineIntent,
  transitionPipeline,
  type PipelineState,
} from "../utils/pipeline";
import "./workspace-mechanisms.css";

type Flight = PipelineState & {
  id: number;
  visualId: number;
  reportPath: string;
  launch: string;
  drop: string;
  edge: number;
  entry: number;
  sinkX: number;
  sinkY: number;
};

export function DataPipeline() {
  const client = useQueryClient();
  const location = useLocation();
  const currentPath = useRef(location.pathname);
  currentPath.current = location.pathname;
  const [flight, setFlight] = useState<Flight | null>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const sink = useRef<HTMLElement | null>(null);
  const visualSerial = useRef(0);
  const previewSerial = useRef(0);

  useEffect(() => {
    setFlight(null);
  }, [location.pathname]);
  useEffect(() => {
    const reset = () => setFlight(null);
    window.addEventListener("resize", reset);
    return () => window.removeEventListener("resize", reset);
  }, []);
  useEffect(() => {
    const launch = (
      reportId: string,
      id: number,
      origin?: { x: number; y: number },
    ) => {
      const reportPath = `/reports/${encodeURIComponent(reportId)}`;
      if (
        currentPath.current !== reportPath ||
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
      )
        return;
      const sidebar = document
        .querySelector<HTMLElement>(".sidebar")
        ?.getBoundingClientRect();
      const receiver = document.querySelector<HTMLElement>(
        "[data-pipeline-sink]",
      );
      const receiverRect = receiver?.getBoundingClientRect();
      if (!sidebar?.width || !receiverRect?.width) return;
      const focused =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      const source = focused?.matches("dialog button")
        ? focused
        : (document.querySelector<HTMLElement>(
            "dialog[open] .dialog-actions .primary",
          ) ?? document.querySelector<HTMLElement>("[data-pipeline-source]"));
      const rect = source?.getBoundingClientRect();
      if (!origin && !rect?.width) return;
      const x = origin?.x ?? rect!.left + rect!.width / 2;
      const y = origin?.y ?? rect!.top + rect!.height / 2;
      const edge = sidebar.right - 1;
      const entry = Math.max(
        sidebar.top + 100,
        Math.min(y - 70, sidebar.height * 0.32),
      );
      const sinkX = receiverRect.left + receiverRect.width / 2;
      const sinkY = receiverRect.top + receiverRect.height / 2;
      sink.current = receiver ?? null;
      const visualId = ++visualSerial.current;
      setFlight((previous) => {
        // Keep the original button-to-rail trajectory when the prepared upload is submitted.
        if (
          id >= 0 &&
          previous &&
          previous.id < 0 &&
          previous.reportPath === reportPath &&
          previous.outcome === "pending"
        ) {
          return { ...previous, id };
        }
        return {
          id,
          visualId,
          reportPath,
          stage: "launch",
          outcome: "pending",
          edge,
          entry,
          sinkX,
          sinkY,
          launch: `M ${x} ${y} C ${x - 90} ${y - 100}, ${edge + 80} ${entry - 35}, ${edge} ${entry}`,
          drop: `M ${edge} ${entry} L ${edge} ${sinkY - 35} Q ${edge} ${sinkY}, ${sinkX} ${sinkY}`,
        };
      });
    };
    const offIntent = subscribePipelineIntent((intent) => {
      if (intent.kind === "prepare") {
        launch(intent.reportId, --previewSerial.current, intent);
      } else {
        const path = `/reports/${encodeURIComponent(intent.reportId)}`;
        setFlight((previous) =>
          previous && previous.id < 0 && previous.reportPath === path
            ? null
            : previous,
        );
      }
    });
    const offMutation = client.getMutationCache().subscribe((event) => {
      if (
        event.type !== "updated" ||
        event.mutation.options.mutationKey?.[0] !== "upload-version"
      )
        return;
      const reportId = event.mutation.options.meta?.reportId;
      if (typeof reportId !== "string") return;
      const reportPath = `/reports/${encodeURIComponent(reportId)}`;
      if (currentPath.current !== reportPath) return;
      if (event.action.type === "pending") {
        launch(reportId, event.mutation.mutationId);
      } else if (
        event.action.type === "success" ||
        event.action.type === "error"
      ) {
        const outcome = event.action.type;
        setFlight((previous) =>
          previous &&
          previous.id === event.mutation.mutationId &&
          previous.reportPath === currentPath.current
            ? { ...previous, ...transitionPipeline(previous, outcome) }
            : previous,
        );
      }
    });
    return () => {
      offIntent();
      offMutation();
    };
  }, [client]);

  useEffect(() => {
    if (!flight || flight.stage === "waiting") return;
    const stage = flight.stage;
    const visualId = flight.visualId;
    const timer = window.setTimeout(
      () => {
        if (stage === "deposit" && sink.current?.isConnected) {
          sink.current.animate(
            [
              { boxShadow: "0 0 0 0 #e4cb7c00", transform: "scale(1)" },
              {
                boxShadow: "0 0 0 10px #e4cb7c55, 0 0 28px #e4cb7c99",
                transform: "scale(1.12)",
                offset: 0.3,
              },
              { boxShadow: "0 0 0 22px #e4cb7c00", transform: "scale(1)" },
            ],
            { duration: 850, easing: "ease-out" },
          );
        }
        setFlight((previous) => {
          if (!previous || previous.visualId !== visualId) return previous;
          if (stage !== "launch") return null;
          return { ...previous, ...transitionPipeline(previous, "arrived") };
        });
      },
      stage === "launch" ? 680 : stage === "deposit" ? 850 : 450,
    );
    return () => window.clearTimeout(timer);
  }, [flight?.visualId, flight?.stage]);

  useEffect(() => {
    if (!flight) return;
    const element = overlay.current;
    if (!element) return;
    try {
      element.showPopover();
    } catch {
      element.classList.add("pipeline-fallback");
    }
    return () => {
      try {
        element.hidePopover();
      } catch {
        /* Already removed or unsupported. */
      }
    };
  }, [Boolean(flight)]);

  if (!flight) return null;
  const moving = flight.stage === "launch" || flight.stage === "deposit";
  const path = flight.stage === "launch" ? flight.launch : flight.drop;
  return createPortal(
    <div
      ref={overlay}
      popover="manual"
      className="pipeline-overlay"
      aria-hidden="true"
    >
      <svg className="pipeline-canvas">
        <defs>
          <filter
            id="pipeline-spark-glow"
            x="-200%"
            y="-200%"
            width="500%"
            height="500%"
          >
            <feGaussianBlur stdDeviation="4" />
          </filter>
        </defs>
        <path
          className="pipeline-rail-glow"
          d={`M ${flight.edge} 0 V ${window.innerHeight}`}
        />
        {moving ? (
          <g key={`${flight.visualId}:${flight.stage}`}>
            <path className="pipeline-flight-path" d={path} />
            <g>
              <circle
                r="13"
                fill="#e8d58e"
                opacity="0.6"
                filter="url(#pipeline-spark-glow)"
              />
              <circle cx="-24" r="1.3" fill="#e8d58e" opacity="0.25" />
              <circle cx="-16" r="1.8" fill="#f8e6ad" opacity="0.45" />
              <circle cx="-8" r="2.4" fill="#fff4d5" opacity="0.7" />
              <circle r="4" fill="#fffef2" />
              <circle r="1" fill="#ffffff" />
              <animateMotion
                path={path}
                dur={flight.stage === "launch" ? "0.65s" : "0.8s"}
                fill="freeze"
                calcMode="spline"
                keyTimes="0;1"
                keySplines="0.35 0 0.2 1"
                rotate="auto"
              />
            </g>
          </g>
        ) : (
          <g
            className={
              flight.stage === "failure"
                ? "pipeline-spark-failure"
                : "pipeline-spark-waiting"
            }
          >
            <circle
              cx={flight.edge}
              cy={flight.entry}
              r="8"
              fill={flight.stage === "failure" ? "#cf7255" : "#dcca8d"}
              opacity="0.4"
              filter="url(#pipeline-spark-glow)"
            />
            <circle
              cx={flight.edge}
              cy={flight.entry}
              r="2.5"
              fill={flight.stage === "failure" ? "#df8b70" : "#fff4d1"}
            />
          </g>
        )}
      </svg>
    </div>,
    document.body,
  );
}
