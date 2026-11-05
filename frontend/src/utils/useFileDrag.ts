import { useEffect, useState } from "react";

const hasFiles = (event: DragEvent) => Boolean(event.dataTransfer?.types.includes("Files"));

/**
 * True while files are dragged over the window; calls onDrop with them when released.
 * A counter is needed because dragenter/dragleave also fire for every child element.
 */
export function useFileDrag(enabled: boolean, onDrop: (files: File[]) => void) {
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (!enabled) return setDragging(false);
    let depth = 0;
    const enter = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth += 1;
      setDragging(true);
    };
    const leave = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    // Without preventDefault the browser would open the file instead of dropping it here.
    const over = (event: DragEvent) => {
      if (hasFiles(event)) event.preventDefault();
    };
    const drop = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth = 0;
      setDragging(false);
      const files = Array.from(event.dataTransfer?.files ?? []);
      if (files.length) onDrop(files);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [enabled, onDrop]);

  return dragging;
}
