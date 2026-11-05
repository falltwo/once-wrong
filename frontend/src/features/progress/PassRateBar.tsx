import { useEffect, useRef, useState } from "react";
import confetti from "canvas-confetti";
import type { ValidationSummary } from "../../types";

/** Short confetti burst from a point on screen; canvas-confetti skips it under reduced motion. */
function burst(x: number, y: number) {
  const origin = { x: x / window.innerWidth, y: y / window.innerHeight };
  const colors = ["#3f8a55", "#8cc276", "#e0b43c", "#f2d27a", "#2c4a3b"];
  const shared = { origin, colors, disableForReducedMotion: true, zIndex: 100 };
  void confetti({ ...shared, particleCount: 70, spread: 70, startVelocity: 38 });
  void confetti({ ...shared, particleCount: 40, spread: 120, startVelocity: 24, scalar: 0.8 });
}

/**
 * 檢核通過率：已執行的規則檢查裡通過幾項。只有零錯誤而且沒有未檢查的規則才算 100%；
 * 剛上傳的新版達到 100% 時放一次紙花。
 */
export function PassRateBar({
  summary,
  celebrate,
  onCelebrated,
}: {
  summary?: ValidationSummary;
  celebrate: boolean;
  onCelebrated: () => void;
}) {
  const gaugeRef = useRef<SVGSVGElement>(null);
  const total = summary?.totalChecks ?? 0;
  const passed = summary?.passedChecks ?? 0;
  const notEvaluated = summary?.notEvaluatedChecks ?? 0;
  const complete = Boolean(summary) && summary!.failedChecks === 0 && notEvaluated === 0;
  const rate = total ? Math.round((passed / total) * 100) : 0;
  const shown = complete ? 100 : Math.min(rate, 99);
  // Start the needle at 0 and let it swing to the value, so the first view moves too.
  const [needle, setNeedle] = useState(0);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setNeedle(shown));
    return () => cancelAnimationFrame(frame);
  }, [shown]);

  useEffect(() => {
    if (!celebrate) return;
    onCelebrated();
    if (!complete) return;
    // Wait for the needle to reach 100, then burst from the top of the dial.
    const timer = window.setTimeout(() => {
      const rect = gaugeRef.current?.getBoundingClientRect();
      if (rect) burst(rect.left + rect.width / 2, rect.top + rect.height * 0.25);
    }, 1100);
    return () => window.clearTimeout(timer);
  }, [celebrate, complete, onCelebrated]);

  if (!summary) return null;
  return (
    <section className={`pass-rate ${complete ? "complete" : ""}`} aria-label="檢核通過率">
      {/* Sundial: a half-circle scale with a brass needle; the arc fills as checks pass. */}
      <svg
        ref={gaugeRef}
        className="sundial"
        viewBox="0 0 150 88"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={shown}
        aria-label={`檢核通過率 ${shown}%`}
      >
        <defs>
          <linearGradient id="brass" x1="0" x2="1">
            <stop offset="0" stopColor="#7a5a1e" />
            <stop offset="0.5" stopColor="#e6c36a" />
            <stop offset="1" stopColor="#8a6a26" />
          </linearGradient>
        </defs>
        <path className="sundial-track" d="M 13 78 A 62 62 0 0 1 137 78" />
        <path
          className="sundial-fill"
          d="M 13 78 A 62 62 0 0 1 137 78"
          pathLength={100}
          strokeDasharray="100"
          strokeDashoffset={100 - needle}
        />
        {/* Clock-style scale: fine ticks every 2%, longer every 10%, longest at 0/50/100. */}
        <path className="sundial-ring" d="M 3 78 A 72 72 0 0 1 147 78" />
        {Array.from({ length: 51 }, (_, index) => {
          const angle = Math.PI - (index / 50) * Math.PI;
          const inner = index % 25 === 0 ? 42 : index % 5 === 0 ? 46 : 50;
          return (
            <line
              key={index}
              className={`sundial-tick ${index % 5 === 0 ? "major" : ""}`}
              x1={75 + inner * Math.cos(angle)}
              y1={78 - inner * Math.sin(angle)}
              x2={75 + 54 * Math.cos(angle)}
              y2={78 - 54 * Math.sin(angle)}
            />
          );
        })}
        <text className="sundial-label" x="13" y="87">0</text>
        <text className="sundial-label" x="137" y="87" textAnchor="end">100</text>
        <g className="sundial-needle" style={{ transform: `rotate(${-90 + 1.8 * needle}deg)` }}>
          <path d="M 73.4 78 L 75 26 L 76.6 78 Z" fill="url(#brass)" />
        </g>
        <circle className="sundial-hub" cx="75" cy="78" r="5" />
      </svg>
      <div className="pass-rate-text">
        <div className="pass-rate-head">
          <span>檢核通過率</span>
          <strong>{shown}%</strong>
        </div>
        <p>
          {complete
            ? "全部規則檢查都通過，可以進行最後確認。"
            : `已執行 ${total} 項規則檢查，通過 ${passed} 項${notEvaluated ? `；另有 ${notEvaluated} 項未檢查，不算通過` : ""}。`}
        </p>
      </div>
    </section>
  );
}
