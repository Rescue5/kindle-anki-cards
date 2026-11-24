import * as React from "react";
import { FoxFigure } from "./fox-figure";
import "./fox-lantern.css";

const useFocusCleanup = typeof window === "undefined" ? React.useEffect : React.useLayoutEffect;
const STORAGE_KEY = "kindle-cards.fox-speech.enabled";
export const FOX_LINES = ["Я посвечу.", "У каждой книги свой голос.", "Хорошую фразу хочется сохранить.", "Пусть слова немного побудут рядом."];
// Shared across Home mounts, so navigation cannot restart the first greeting.
const schedule = { remaining: 8000, next: 0 };
type Speech = { text: string; count: number; phase: "typing" | "hold" | "leaving" };

export function FoxLantern({ motion = true, quiet = false }: { motion?: boolean; quiet?: boolean } = {}) {
  const scene = React.useRef<HTMLDivElement>(null);
  const [speech, setSpeech] = React.useState<Speech | null>(null);
  const [enabled, setEnabled] = React.useState(() => {
    try { return typeof window === "undefined" || localStorage.getItem(STORAGE_KEY) !== "false"; } catch { return true; }
  });
  const [active, setActive] = React.useState(false);
  const [reduced, setReduced] = React.useState(true);

  React.useEffect(() => {
    const element = scene.current;
    if (!element) return;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let inView = false;
    const update = () => { setReduced(media.matches); setActive(inView && document.visibilityState === "visible"); };
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

  React.useEffect(() => {
    if (quiet || !enabled) {
      setSpeech(null);
      schedule.remaining = Math.max(schedule.remaining, 60000);
    }
  }, [quiet, enabled]);

  React.useEffect(() => {
    if (!active || quiet || !enabled) return;
    if (!speech) {
      const started = performance.now();
      const remaining = schedule.remaining;
      let fired = false;
      const timer = window.setTimeout(() => {
        fired = true;
        const text = FOX_LINES[schedule.next];
        schedule.next = (schedule.next + 1) % FOX_LINES.length;
        schedule.remaining = 60000;
        setSpeech({ text, count: reduced || !motion ? Array.from(text).length : 0, phase: reduced || !motion ? "hold" : "typing" });
      }, remaining);
      return () => { clearTimeout(timer); if (!fired) schedule.remaining = Math.max(0, remaining - (performance.now() - started)); };
    }
    const characters = Array.from(speech.text);
    const delay = speech.phase === "typing" ? 65 : speech.phase === "hold" ? 6000 : reduced ? 0 : 350;
    const timer = window.setTimeout(() => {
      if (speech.phase === "leaving") { setSpeech(null); return; }
      if (speech.phase === "hold") { setSpeech({ ...speech, phase: "leaving" }); return; }
      const count = reduced || !motion ? characters.length : speech.count + 1;
      setSpeech({ ...speech, count, phase: count >= characters.length ? "hold" : "typing" });
    }, delay);
    return () => clearTimeout(timer);
  }, [active, quiet, enabled, reduced, motion, speech]);

  React.useEffect(() => {
    if (!speech) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") { schedule.remaining = 60000; setSpeech(null); }
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [speech !== null]);

  function toggleSpeech() {
    const next = !enabled;
    setEnabled(next);
    setSpeech(null);
    schedule.remaining = 60000;
    try { localStorage.setItem(STORAGE_KEY, String(next)); } catch { /* The current session still respects the choice. */ }
  }

  const visible = speech && enabled && !quiet;
  return <div ref={scene} className="fox-lantern" data-motion={motion && !reduced} data-active={active}>
    <div className="fox-lantern-figure" aria-hidden="true"><FoxFigure /></div>
    <button type="button" className="fox-speech-toggle" aria-label="Реплики лиса" aria-pressed={enabled} onClick={toggleSpeech}>
      <span aria-hidden="true">{enabled ? "●" : "○"}</span> Реплики лиса
    </button>
    {visible ? <div className="fox-lantern-speech" data-phase={speech.phase} role="region" aria-label="Реплика лиса" aria-live="off">
      <svg className="fox-speech-paper" viewBox="0 0 200 110" preserveAspectRatio="none" aria-hidden="true"><path d="M24 9 C64 3 148 5 178 12 C193 17 196 40 192 64 C190 82 164 91 132 90 L43 89 Q21 87 8 105 Q13 86 15 73 C3 60 5 26 13 17 Q17 11 24 9 Z" /></svg>
      <p aria-hidden="true"><span className="fox-speech-measure">{speech.text}</span><span>{reduced || !motion ? speech.text : Array.from(speech.text).slice(0, speech.count).join("")}</span></p>
      <span className="sr-only">{speech.text}</span>
    </div> : null}
  </div>;
}
