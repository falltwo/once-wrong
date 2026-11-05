export type PipelineState = {
  stage: "launch" | "waiting" | "deposit" | "failure" | "done";
  outcome: "pending" | "success" | "error";
};
export type PipelineIntent =
  | { kind: "prepare"; reportId: string; x: number; y: number }
  | { kind: "cancel"; reportId: string };
const intentListeners = new Set<(intent: PipelineIntent) => void>();
export function announcePipelineIntent(intent: PipelineIntent) {
  intentListeners.forEach((listener) => listener(intent));
}
export function subscribePipelineIntent(
  listener: (intent: PipelineIntent) => void,
) {
  intentListeners.add(listener);
  return () => {
    intentListeners.delete(listener);
  };
}
export function transitionPipeline(
  state: PipelineState,
  event: "success" | "error" | "arrived" | "settled",
): PipelineState {
  if (event === "settled") return { ...state, stage: "done" };
  const outcome =
    event === "success" || event === "error" ? event : state.outcome;
  if (event === "arrived" || state.stage === "waiting") {
    return {
      outcome,
      stage:
        outcome === "success"
          ? "deposit"
          : outcome === "error"
            ? "failure"
            : "waiting",
    };
  }
  return { ...state, outcome };
}
