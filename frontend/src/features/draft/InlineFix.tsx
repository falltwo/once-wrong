import { useEffect, useLayoutEffect, useState, type RefObject } from "react";
import type { CellValue } from "../../types";

const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Thin bracket under the selected row linking the error cell to the cell the rule compared
 * it with. Cells are found by class, so the table only has to mark them.
 */
export function CellLink({
  container,
  label,
  trigger,
}: {
  container: RefObject<HTMLDivElement | null>;
  label: string;
  trigger: string;
}) {
  const [path, setPath] = useState<{ d: string; x: number; y: number } | null>(null);

  useLayoutEffect(() => {
    const box = container.current;
    if (!box) return;
    const measure = () => {
      const from = box.querySelector<HTMLElement>(".cell-focus-error");
      const to = box.querySelector<HTMLElement>(".cell-focus-compare");
      if (!from || !to || from.parentElement !== to.parentElement) return setPath(null);
      const origin = box.getBoundingClientRect();
      const point = (cell: HTMLElement) => {
        const rect = cell.getBoundingClientRect();
        return {
          x: rect.left - origin.left + box.scrollLeft + rect.width / 2,
          y: rect.bottom - origin.top + box.scrollTop - 4,
        };
      };
      const a = point(from);
      const b = point(to);
      const low = Math.max(a.y, b.y) + 7;
      setPath({
        d: `M${a.x} ${a.y} V${low} H${b.x} V${b.y}`,
        x: (a.x + b.x) / 2,
        y: low,
      });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, [container, trigger]);

  if (!path) return null;
  return (
    <svg className="cell-link" aria-hidden="true">
      <path d={path.d} pathLength={1} />
      <text x={path.x} y={path.y + 11}>
        {label}
      </text>
    </svg>
  );
}

/** Shows a draft value; numbers count up from the original so the change is visible. */
export function DraftValue({
  from,
  to,
  format,
}: {
  from: CellValue;
  to: CellValue;
  format: (value: CellValue) => string;
}) {
  const numeric = typeof from === "number" && typeof to === "number";
  const [shown, setShown] = useState<CellValue>(numeric && !reduceMotion() ? from : to);

  useEffect(() => {
    if (!numeric || reduceMotion()) return setShown(to);
    const start = performance.now();
    let frame = requestAnimationFrame(function step(now) {
      const t = Math.min(1, (now - start) / 700);
      const eased = 1 - (1 - t) ** 3;
      setShown(Math.round((from as number) + ((to as number) - (from as number)) * eased));
      if (t < 1) frame = requestAnimationFrame(step);
    });
    return () => cancelAnimationFrame(frame);
  }, [from, to, numeric]);

  return (
    <span className="draft-value">
      <span className="draft-number">{format(shown)}</span>
      <small>草稿・待重新驗證</small>
    </span>
  );
}
