import { cn } from "@/lib/utils";

/**
 * Pencil drawing primitives (see DESIGN.md › Pencil and paper).
 *
 * Strokes are hand-placed, slightly wobbly paths stretched over their host
 * with `vector-effect: non-scaling-stroke`: the line keeps a pencil's weight at
 * any size and its colour follows the theme through `currentColor`. Variants
 * are fixed paths, so an element is drawn the same way on every render.
 */

const ruleLines = [
  "M0 3.12 Q33 3.37 66 4.61 Q152 3.98 238 3.57 Q304 3.81 370 3.52 Q457 4.18 544 4.89 Q574 4.93 604 3.95 Q615 4.38 626 4.61 Q813 4.91 1000 3.96",
  "M0 3.2 Q36 2.53 72 4.01 Q112 3.52 151 3.17 Q237 3.4 324 3.88 Q345 4.69 366 3.23 Q451 3.36 536 3.26 Q593 3.08 651 3.86 Q825 4.72 1000 4.59",
  "M0 3.43 Q226 3.78 452 4.02 Q459 3.2 466 4.23 Q487 5.1 508 4.53 Q534 5.36 560 3.27 Q574 3.55 587 3.65 Q756 3.85 924 3.26 Q962 2.65 1000 4.56",
];

/** A hand-drawn horizontal rule that stretches to its container's width. */
export function PencilRule({ variant = 0, className }: { variant?: number; className?: string }) {
  return (
    <svg className={cn("pencil-rule", className)} viewBox="0 0 1000 8" preserveAspectRatio="none" aria-hidden="true">
      <path d={ruleLines[variant % ruleLines.length]} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

const frames = [
  [
    "M1.5 2.4 C24 1.2 61 2.9 98.4 1.6 M98.9 1 C98.2 28 99.4 71 98.6 98.6 M99.3 98.2 C72 99.1 31 97.9 1.2 98.8 M1.9 99.4 C2.6 70 1.1 31 2.1 1.1",
    "M3 1.2 C30 2.6 70 0.9 97.2 2.8 M97.6 3 C99.6 31 97.9 68 99.4 96.8 M97.7 99.3 C68 97.6 30 99.6 2.7 97.4 M0.8 97.6 C1.9 66 0.4 34 1.4 3.4",
  ],
  [
    "M3 1.2 C30 2.6 70 0.9 97.2 2.8 M97.6 3 C99.6 31 97.9 68 99.4 96.8 M97.7 99.3 C68 97.6 30 99.6 2.7 97.4 M0.8 97.6 C1.9 66 0.4 34 1.4 3.4",
    "M1.5 2.4 C24 1.2 61 2.9 98.4 1.6 M98.9 1 C98.2 28 99.4 71 98.6 98.6 M99.3 98.2 C72 99.1 31 97.9 1.2 98.8 M1.9 99.4 C2.6 70 1.1 31 2.1 1.1",
  ],
];

/**
 * A rough, double-stroked outline laid over its `position: relative` parent.
 * The corners overshoot a little, like a frame drawn in two passes.
 */
export function PencilFrame({ variant = 0, className }: { variant?: number; className?: string }) {
  const [main, ghost] = frames[variant % frames.length];
  return (
    <svg className={cn("pencil-frame", className)} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <path className="pencil-frame-main" d={main} vectorEffect="non-scaling-stroke" />
      <path className="pencil-frame-ghost" d={ghost} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** A small scroll in a frame's corner; rotate it for the opposite corner. */
export function CornerCurl({ className }: { className?: string }) {
  return (
    <svg className={cn("corner-curl", className)} viewBox="0 0 40 40" aria-hidden="true">
      <path d="M6 34 C6 17 17 6 34 6 M6 34 c0-6 5-9 8-6 s1 6-4 6 M34 6 c-6 0-9 5-6 8 s6 1 6-4" />
    </svg>
  );
}

/** A centred flourish used to open a section or close an empty state. */
export function Flourish({ className, width = 168 }: { className?: string; width?: number }) {
  return (
    <svg className={cn("flourish", className)} width={width} height={24} viewBox="0 0 168 24" aria-hidden="true">
      <path d="M4 12 C28 12 40 4 56 7 C66 9 66 18 74 17 C80 16 80 9 84 9 C88 9 88 16 94 17 C102 18 102 9 112 7 C128 4 140 12 164 12" />
      <path d="M84 9 C82 5 84 2 84 2 C84 2 86 5 84 9" />
      <circle cx="84" cy="20" r="1.4" />
      <path d="M44 13 C50 16 54 15 57 12 M124 13 C118 16 114 15 111 12" />
    </svg>
  );
}

/**
 * Global SVG filters. `pencil-texture` is a faint wobble for icons;
 * `pencil-graphite` adds grain with small dropouts for larger drawings.
 */
export function PencilDefs() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true" focusable="false">
      <defs>
        <filter id="pencil-texture" x="-5%" y="-5%" width="110%" height="110%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="4" result="grain" />
          <feDisplacementMap in="SourceGraphic" in2="grain" scale="1.4" xChannelSelector="R" yChannelSelector="G" />
        </filter>
        <filter id="pencil-graphite" x="-10%" y="-10%" width="120%" height="120%">
          <feTurbulence type="fractalNoise" baseFrequency="0.75" numOctaves="2" seed="4" result="noise" />
          <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.8" xChannelSelector="R" yChannelSelector="G" result="wobble" />
          <feTurbulence type="fractalNoise" baseFrequency="1.6" numOctaves="1" seed="9" result="grain" />
          <feColorMatrix in="grain" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -2.2 1.9" result="mask" />
          <feComposite in="wobble" in2="mask" operator="in" />
        </filter>
      </defs>
    </svg>
  );
}
