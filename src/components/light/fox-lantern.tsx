import * as React from "react";
import { FoxFigure } from "./fox-figure";
import { PencilFrame } from "@/components/sketch/sketch";
import "./fox-lantern.css";

const useFocusCleanup = typeof window === "undefined" ? React.useEffect : React.useLayoutEffect;

/** Mounted only during preparation. The SVG and hit target share the same 500 × 450 box. */
export function FoxLantern({ motion = true }: { motion?: boolean } = {}) {
  const scene = React.useRef<HTMLDivElement>(null);
  const trigger = React.useRef<HTMLButtonElement>(null);
  const speech = React.useRef<HTMLDivElement>(null);
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(false);
  const [reduced, setReduced] = React.useState(true);
  const speechId = React.useId();

  React.useEffect(() => {
    const element = scene.current;
    if (!element) return;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let inView = false;
    const update = () => {
      setReduced(media.matches);
      setActive(inView && document.visibilityState === "visible");
    };
    const observer = new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; update(); });
    observer.observe(element);
    document.addEventListener("visibilitychange", update);
    media.addEventListener("change", update);
    update();
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", update);
      media.removeEventListener("change", update);
    };
  }, []);

  // Capture focus before the scene is removed. A neighbouring page or a newly focused control wins.
  useFocusCleanup(() => {
    const element = scene.current;
    return () => {
      if (!element?.contains(document.activeElement)) return;
      queueMicrotask(() => {
        if (document.activeElement && document.activeElement !== document.body && document.activeElement.isConnected) return;
        document.getElementById("home-title")?.focus({ preventScroll: true });
      });
    };
  }, []);

  const close = React.useCallback(() => {
    setOpen(false);
    if (speech.current?.contains(document.activeElement)) trigger.current?.focus({ preventScroll: true });
  }, []);

  React.useEffect(() => {
    if (!open) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { close(); event.stopPropagation(); }
    };
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!speech.current?.contains(target) && !trigger.current?.contains(target)) close();
    };
    document.addEventListener("keydown", escape);
    document.addEventListener("pointerdown", outside);
    return () => {
      document.removeEventListener("keydown", escape);
      document.removeEventListener("pointerdown", outside);
    };
  }, [open, close]);

  return <div ref={scene} className="fox-lantern" data-motion={motion && !reduced} data-active={active}>
    <div className="fox-lantern-figure" aria-hidden="true"><FoxFigure /></div>
    <button ref={trigger} type="button" className="fox-lantern-greet" aria-label="Поприветствовать лиса"
      aria-expanded={open} aria-controls={open ? speechId : undefined} onClick={() => setOpen((value) => !value)} />
    {open ? <div ref={speech} id={speechId} className="fox-lantern-speech" role="region" aria-label="Реплика лиса">
      <PencilFrame />
      <p>Я посвечу.</p>
      <button type="button" className="fox-lantern-close" onClick={close}>Закрыть</button>
    </div> : null}
  </div>;
}
