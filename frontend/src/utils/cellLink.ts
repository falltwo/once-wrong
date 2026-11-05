type LayoutCell = { left: number; top: number; width: number; height: number };

/** All coordinates are local to the error cell, unaffected by ancestor transforms/scroll. */
export function cellLinkGeometry(from: LayoutCell, to: LayoutCell) {
  const a = { x: from.width / 2, y: from.height - 22 };
  const b = {
    x: to.left - from.left + to.width / 2,
    y: to.top - from.top + to.height - 22,
  };
  const low = Math.max(a.y, b.y) + 6;
  return {
    d: `M${a.x} ${a.y} V${low} H${b.x} V${b.y}`,
    x: (a.x + b.x) / 2,
    y: low + 11,
  };
}
