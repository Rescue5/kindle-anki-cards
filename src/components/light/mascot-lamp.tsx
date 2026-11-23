import * as React from "react";
import { DeskLamp } from "./lamps";
import { PencilFrame } from "@/components/sketch/sketch";
import "./mascot-lamp.css";

type Props = { phase: "preparing" | "ready"; motion: boolean };

/** The host keeps the same lamp anchor when the batch changes. Only an ear moves. */
export function MascotLamp({ phase, motion }: Props) {
  const trigger = React.useRef<HTMLButtonElement>(null);
  const bubble = React.useRef<HTMLDivElement>(null);
  const animation = React.useRef<Animation | null>(null);
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(false);
  const [reduced, setReduced] = React.useState(true);
  const idleRemaining = React.useRef(25_000);
  const idleDone = React.useRef(false);
  const previousPhase = React.useRef(phase);
  const readyPending = React.useRef(false);
  const bubbleId = React.useId();
  const allowed = motion && !reduced;

  const reconcileVisibility = React.useCallback(() => {
    const button = trigger.current;
    const host = button?.closest<HTMLElement>(".lamp-host");
    const drawing = host?.querySelector(".desk-lamp-drawing");
    const visible = Boolean(button?.getClientRects().length && drawing && getComputedStyle(drawing).display !== "none");
    if (!visible) {
      setOpen(false);
      if (document.activeElement === button || bubble.current?.contains(document.activeElement)) {
        host?.querySelector<HTMLElement>("#home-title, h1, [tabindex='-1']")?.focus({ preventScroll: true });
      }
    }
    return visible;
  }, []);

  React.useEffect(() => { reconcileVisibility(); }, [phase, reconcileVisibility]);

  const gesture = React.useCallback(() => {
    if (!allowed || !active) return;
    const ear = trigger.current?.closest(".lamp-host")?.querySelector<SVGGElement>(".mascot-ear-left");
    if (!ear) return;
    animation.current?.cancel();
    animation.current = ear.animate([
      { transform: "rotate(0deg)" }, { transform: "rotate(-13deg)", offset: .36 },
      { transform: "rotate(5deg)", offset: .7 }, { transform: "rotate(0deg)" },
    ], { duration: 850, easing: "ease-in-out" });
  }, [allowed, active]);

  React.useEffect(() => {
    const host = trigger.current?.closest<HTMLElement>(".lamp-host");
    if (!host) return;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let inView = false;
    const update = () => {
      setReduced(media.matches);
      const visible = reconcileVisibility();
      setActive(inView && visible && document.visibilityState === "visible");
    };
    const intersection = new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; update(); });
    const resize = new ResizeObserver(update);
    intersection.observe(host);
    resize.observe(host);
    media.addEventListener("change", update);
    document.addEventListener("visibilitychange", update);
    window.addEventListener("resize", update);
    update();
    return () => {
      intersection.disconnect();
      resize.disconnect();
      media.removeEventListener("change", update);
      document.removeEventListener("visibilitychange", update);
      window.removeEventListener("resize", update);
      animation.current?.cancel();
    };
  }, [reconcileVisibility]);

  React.useEffect(() => {
    if (!allowed || !active) animation.current?.cancel();
  }, [allowed, active]);

  React.useEffect(() => {
    if (phase === "preparing" && previousPhase.current === "ready") {
      idleRemaining.current = 25_000;
      idleDone.current = false;
    }
    if (phase === "ready" && previousPhase.current === "preparing") readyPending.current = allowed;
    previousPhase.current = phase;
    if (phase === "preparing" || !allowed) readyPending.current = false;
    if (phase === "ready" && readyPending.current && active && allowed) {
      readyPending.current = false;
      gesture();
    }
  }, [phase, active, allowed, gesture]);

  React.useEffect(() => {
    if (phase !== "preparing" || !allowed || !active || idleDone.current) return;
    const started = performance.now();
    const timer = window.setTimeout(() => {
      idleDone.current = true;
      gesture();
    }, idleRemaining.current);
    return () => {
      window.clearTimeout(timer);
      idleRemaining.current = Math.max(0, idleRemaining.current - (performance.now() - started));
    };
  }, [phase, allowed, active, gesture]);

  const close = React.useCallback(() => {
    setOpen(false);
    // A click elsewhere keeps its focus. Escape/close from within the bubble returns to the head.
    if (bubble.current?.contains(document.activeElement)) trigger.current?.focus({ preventScroll: true });
  }, []);

  React.useEffect(() => {
    if (!open) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { close(); event.stopPropagation(); }
    };
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!bubble.current?.contains(target) && !trigger.current?.contains(target)) close();
    };
    document.addEventListener("keydown", escape);
    document.addEventListener("pointerdown", outside);
    return () => {
      document.removeEventListener("keydown", escape);
      document.removeEventListener("pointerdown", outside);
    };
  }, [open, close]);

  return <>
    <DeskLamp lit mascot className={`mascot-lamp${allowed && active ? " mascot-motion" : ""}`} />
    <button ref={trigger} type="button" className="mascot-greet" aria-label="Поприветствовать лампу"
      aria-expanded={open} aria-controls={open ? bubbleId : undefined}
      onPointerEnter={gesture} onFocus={gesture} onClick={() => { setOpen((value) => !value); gesture(); }} />
    {open ? <div ref={bubble} id={bubbleId} className="mascot-bubble" role="region" aria-label="Реплика лампы">
      <PencilFrame />
      <p>{phase === "preparing" ? "Я посвечу, пока собираются слова." : "А какую фразу из книги вы бы оставили?"}</p>
      <button type="button" className="mascot-close" onClick={close}>Закрыть</button>
    </div> : null}
  </>;
}
