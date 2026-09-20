/**
 * @author: @kokonutui / Trenston
 * @description: Smooth Tab — sliding active indicator (KokonutUI, restyled)
 * Vertical or horizontal track for nav active-state indication.
 * @website: https://kokonutui.com
 */

import { motion, useReducedMotion } from "motion/react";
import * as React from "react";
import { cn } from "@/lib/utils";

const SmoothTabContext = React.createContext(null);

/**
 * Sliding indicator track. Wrap nav items with <SmoothTabItem id="…">.
 * @param {"vertical"|"horizontal"} orientation
 * @param {string|null} activeId
 * @param {"bar"|"underline"|"pill"} variant — thin bar, bottom underline, or full-row solid pill
 */
export default function SmoothTab({
  orientation = "horizontal",
  activeId = null,
  variant,
  className,
  indicatorClassName,
  children,
}) {
  const reduceMotion = useReducedMotion();
  const containerRef = React.useRef(null);
  const itemRefs = React.useRef(new Map());
  const [box, setBox] = React.useState({
    top: 0,
    left: 0,
    width: 0,
    height: 0,
    visible: false,
  });

  const resolvedVariant = variant || (orientation === "vertical" ? "bar" : "underline");

  const register = React.useCallback((id, el) => {
    if (el) itemRefs.current.set(id, el);
    else itemRefs.current.delete(id);
  }, []);

  const measure = React.useCallback(() => {
    const container = containerRef.current;
    const el = activeId ? itemRefs.current.get(activeId) : null;
    if (!container || !el) {
      setBox((prev) => (prev.visible ? { ...prev, visible: false } : prev));
      return;
    }
    const c = container.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    setBox({
      top: r.top - c.top,
      left: r.left - c.left,
      width: r.width,
      height: r.height,
      visible: true,
    });
  }, [activeId]);

  React.useLayoutEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure, children]);

  const indicatorAnimate =
    resolvedVariant === "pill"
      ? {
          x: box.left,
          y: box.top,
          width: box.width,
          height: box.height,
          opacity: box.visible ? 1 : 0,
        }
      : resolvedVariant === "bar"
        ? {
            x: 0,
            y: box.top + Math.max(0, (box.height - 20) / 2),
            width: 2,
            height: 20,
            opacity: box.visible ? 1 : 0,
          }
        : {
            x: box.left,
            y: box.top + box.height - 2,
            width: box.width,
            height: 2,
            opacity: box.visible ? 1 : 0,
          };

  return (
    <SmoothTabContext.Provider value={{ register }}>
      <div
        ref={containerRef}
        className={cn(
          "relative",
          orientation === "vertical" && "flex w-full flex-col items-stretch",
          className,
        )}
      >
        <motion.div
          aria-hidden
          className={cn(
            "pointer-events-none absolute z-[1] rounded-full",
            resolvedVariant === "pill" ? "bg-sky-100" : "bg-helm-gold",
            indicatorClassName,
          )}
          initial={false}
          animate={indicatorAnimate}
          transition={
            reduceMotion
              ? { duration: 0 }
              : { type: "spring", stiffness: 420, damping: 32 }
          }
          style={{ left: 0, top: 0 }}
        />
        {children}
      </div>
    </SmoothTabContext.Provider>
  );
}

/** Registers an item in the nearest SmoothTab track for indicator measurement. */
export function SmoothTabItem({ id, className, children, as: Comp = "div", ...props }) {
  const ctx = React.useContext(SmoothTabContext);
  return (
    <Comp
      ref={(el) => ctx?.register?.(id, el)}
      className={cn("relative z-[2] flex w-full", className)}
      {...props}
    >
      {children}
    </Comp>
  );
}
