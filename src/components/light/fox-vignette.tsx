import { FoxFigure } from "./fox-figure";

/** The same lantern bearer at rest alongside the reader's work. */
export function FoxVignette() {
  return <span className="fox-vignette" aria-hidden="true"><FoxFigure /></span>;
}

/** Simplify the profile so the eyes and ears read at brand-mark size. */
export function FoxMark() {
  return <svg className="fox-mark" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
    <path d="M3 27 Q7 25 9 19 L12 14 Q14 7 23 2 Q24 9 21 16 Q29 12 38 13 Q34 20 28 23 L32 27 L28 28 L31 30 L25 30 L26 33 Q21 36 16 36 L13 32 Q7 32 3 29 Z"
      fill="#0c0d10" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    <g fill="#f9e9ce"><ellipse cx="9.8" cy="24" rx="1.05" ry="1.4" /><ellipse cx="16" cy="25" rx="1.4" ry="1.7" /></g>
  </svg>;
}
