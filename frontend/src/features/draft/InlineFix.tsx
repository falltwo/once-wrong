import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CellValue } from "../../types";
import { cellLinkGeometry } from "../../utils/cellLink";

const reduceMotion = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Thin bracket under the selected row linking the error cell to the cell the rule compared
 * it with. Cells are found by class, so the table only has to mark them.
 */
export function CellLink({
  label,
  trigger,
}: {
  label: string;
  trigger: string;
}) {
  const [path, setPath] = useState<{ d: string; x: number; y: number } | null>(
    null,
  );
  const graphic = useRef<SVGSVGElement>(null);

  useLayoutEffect(() => {
    const from = graphic.current?.parentElement as HTMLTableCellElement | null;
    const row = from?.closest("tr");
    const to = row?.querySelector<HTMLTableCellElement>(".cell-focus-compare");
    if (!from || !to) {
      setPath(null);
      return;
    }
    const measure = () => {
      if (from.offsetParent !== to.offsetParent) {
        setPath(null);
        return;
      }
      const layout = (cell: HTMLTableCellElement) => ({
        left: cell.offsetLeft,
        top: cell.offsetTop,
        width: cell.offsetWidth,
        height: cell.offsetHeight,
      });
      setPath(cellLinkGeometry(layout(from), layout(to)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(from);
    observer.observe(to);
    return () => observer.disconnect();
  }, [trigger]);

  return (
    <svg ref={graphic} className="cell-link" aria-hidden="true">
      {path && (
        <>
          <path d={path.d} pathLength={1} />
          <text x={path.x} y={path.y}>
            {label}
          </text>
        </>
      )}
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
  const [shown, setShown] = useState<CellValue>(
    numeric && !reduceMotion() ? from : to,
  );

  useEffect(() => {
    if (!numeric || reduceMotion()) return setShown(to);
    const start = performance.now();
    let frame = requestAnimationFrame(function step(now) {
      const t = Math.min(1, (now - start) / 700);
      const eased = 1 - (1 - t) ** 3;
      setShown(
        Math.round(
          (from as number) + ((to as number) - (from as number)) * eased,
        ),
      );
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
