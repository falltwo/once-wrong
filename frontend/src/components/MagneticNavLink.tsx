import { useEffect, useRef, type PointerEvent, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import "./magnetic-nav.css";

/** Keep the pointer target still while the link surface follows the mouse a few pixels. */
export function MagneticNavLink({
  to,
  icon,
  children,
}: {
  to: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  const target = useRef<HTMLDivElement>(null);
  const frame = useRef<number | null>(null);
  const point = useRef({ x: 0, y: 0 });

  const reset = () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
    target.current?.style.removeProperty("--magnet-x");
    target.current?.style.removeProperty("--magnet-y");
  };

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const pointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    motion.addEventListener("change", reset);
    pointer.addEventListener("change", reset);
    window.addEventListener("blur", reset);
    return () => {
      reset();
      motion.removeEventListener("change", reset);
      pointer.removeEventListener("change", reset);
      window.removeEventListener("blur", reset);
    };
  }, []);

  const followPointer = (event: PointerEvent<HTMLDivElement>) => {
    if (
      event.pointerType !== "mouse" ||
      !window.matchMedia("(hover: hover) and (pointer: fine)").matches ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      reset();
      return;
    }
    point.current = { x: event.clientX, y: event.clientY };
    if (frame.current !== null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      const element = target.current;
      if (!element) return;
      const rect = element.getBoundingClientRect();
      const x = Math.max(
        -5,
        Math.min(5, (point.current.x - rect.left - rect.width / 2) * 0.07),
      );
      const y = Math.max(
        -3,
        Math.min(3, (point.current.y - rect.top - rect.height / 2) * 0.12),
      );
      element.style.setProperty("--magnet-x", `${x.toFixed(2)}px`);
      element.style.setProperty("--magnet-y", `${y.toFixed(2)}px`);
    });
  };

  return (
    <div
      ref={target}
      className="magnetic-nav-target"
      onPointerEnter={followPointer}
      onPointerMove={followPointer}
      onPointerLeave={reset}
      onPointerCancel={reset}
      onBlur={reset}
    >
      <NavLink
        to={to}
        className={({ isActive }) =>
          `nav-item magnetic-nav-link${isActive ? " active" : ""}`
        }
      >
        <span className="nav-radar-sweep" aria-hidden="true" />
        <span className="magnetic-nav-icon" aria-hidden="true">
          {icon}
        </span>
        <span className="magnetic-nav-label">{children}</span>
        <span className="nav-selection-mark" aria-hidden="true">
          <i />
        </span>
      </NavLink>
    </div>
  );
}
