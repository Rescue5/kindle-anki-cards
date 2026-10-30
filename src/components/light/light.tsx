import * as React from "react";
import { cn } from "@/lib/utils";

export { LightScene, Lit } from "./scene";

/**
 * Switching between day and night is a lamp switch: the room goes dark,
 * the theme changes in the dark, and the light comes back.
 */
export function useLightSwitch(apply: () => void) {
  const [phase, setPhase] = React.useState<"idle" | "dark">("idle");
  const busy = React.useRef(false);
  const toggle = React.useCallback(() => {
    if (busy.current) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      apply();
      return;
    }
    busy.current = true;
    setPhase("dark");
    window.setTimeout(() => {
      apply();
      window.setTimeout(() => {
        setPhase("idle");
        busy.current = false;
      }, 120);
    }, 260);
  }, [apply]);
  const curtain = <div className={cn("light-curtain", phase === "dark" && "is-dark")} aria-hidden="true" />;
  return { toggle, curtain };
}
