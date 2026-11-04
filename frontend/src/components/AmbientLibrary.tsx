import { useEffect, useRef } from "react";

/**
 * Archive-mode backdrop: oat-white museum wall, a soft pool of warm light that lazily follows
 * the pointer, and faint manual-term watermarks that scroll slower than the page (parallax).
 * Purely decorative; under reduced motion the lamp stays put and nothing moves.
 */
export function AmbientLibrary() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const layer = ref.current;
    if (!layer) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // Lamp starts over the manual panel on the right and drifts toward the pointer.
    const target = { x: 0.72, y: 0.35 };
    const lamp = { ...target };
    let frame = 0;
    const tick = () => {
      lamp.x += (target.x - lamp.x) * 0.04;
      lamp.y += (target.y - lamp.y) * 0.04;
      layer.style.setProperty("--lamp-x", `${(lamp.x * 100).toFixed(2)}%`);
      layer.style.setProperty("--lamp-y", `${(lamp.y * 100).toFixed(2)}%`);
      frame = requestAnimationFrame(tick);
    };
    const move = (event: PointerEvent) => {
      // Only a gentle pull toward the pointer, never the full distance.
      target.x = 0.72 + (event.clientX / window.innerWidth - 0.72) * 0.35;
      target.y = 0.35 + (event.clientY / window.innerHeight - 0.35) * 0.35;
    };
    const scroll = () => layer.style.setProperty("--scroll", `${window.scrollY}px`);
    frame = requestAnimationFrame(tick);
    window.addEventListener("pointermove", move, { passive: true });
    window.addEventListener("scroll", scroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("scroll", scroll);
    };
  }, []);

  return (
    <div ref={ref} className="ambient-library" aria-hidden="true">
      <div className="ambient-watermark" />
      <div className="ambient-lamp" />
    </div>
  );
}
