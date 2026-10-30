import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Lamps are drawn objects anchored to the element they light. Each lamp renders
 * absolutely positioned layers inside a `position: relative` host: the beam is
 * a CSS clip-path cone whose points are offsets from the same corner the
 * drawing is anchored to, so the light always leaves the shade and lands on
 * the host at any width. A lamp is lit only while its subject needs attention;
 * by day the beams are gone and a lit subject keeps a faint warm wash.
 */

type LampProps = { lit: boolean; className?: string };

const graphite = { filter: "url(#pencil-graphite)" };

// Dust drifting in the desk lamp's cone, as offsets from the host's bottom-right corner.
const motes = [
  { right: 420, bottom: 330, size: 3, duration: 11, delay: 0 },
  { right: 520, bottom: 244, size: 3, duration: 9, delay: -3 },
  { right: 580, bottom: 180, size: 2, duration: 12, delay: -6 },
  { right: 700, bottom: 268, size: 3, duration: 10, delay: -2 },
  { right: 460, bottom: 98, size: 2, duration: 13, delay: -8 },
  { right: 470, bottom: 158, size: 2, duration: 12, delay: -1 },
];

/**
 * An architect's lamp standing on the desk line at the host's bottom-right,
 * its shade leaning over the content to the left. The host sets `--lamp-s`
 * to scale the lamp and its beam together.
 */
export function DeskLamp({ lit, className }: LampProps) {
  const state = cn("lamp", lit && "is-lit", className);
  return (
    <>
      <div className={cn(state, "desk-lamp-beam")} aria-hidden="true">
        <span className="desk-lamp-cone" />
        <span className="desk-lamp-core" />
      </div>
      <span className={cn(state, "lamp-pool desk-lamp-pool")} aria-hidden="true" />
      <span className={cn(state, "desk-lamp-desk-glow")} aria-hidden="true" />
      {motes.map((mote, index) => (
        <span
          key={index}
          className={cn(state, "lamp-mote desk-lamp-mote")}
          aria-hidden="true"
          style={{ "--mote-right": `${mote.right}px`, "--mote-bottom": `${mote.bottom}px`, width: mote.size, height: mote.size, animationDuration: `${mote.duration}s`, animationDelay: `${mote.delay}s` } as React.CSSProperties}
        />
      ))}
      <svg className={cn(state, "desk-lamp-drawing")} viewBox="0 0 400 600" aria-hidden="true">
        <defs>
          <clipPath id="desk-lamp-shade"><path d="M128.8 118.4 Q87.2 129.6 54 132 L111.6 208.8 Q123.2 177.6 145.6 140.8 Z" /></clipPath>
          <clipPath id="desk-lamp-base"><path d="M234 574 L234 584 A66 11 0 0 0 366 584 L366 574 A66 11 0 0 1 234 574 Z" /></clipPath>
        </defs>
        <ellipse className="lamp-cast" cx="290" cy="597" rx="96" ry="5" />
        <g className="lamp-strokes" style={graphite}>
          <path d="M364 586 C378 596 392 598 406 597" strokeWidth="1.2" />
          <path className="lamp-body" d="M234 574 L234 584 A66 11 0 0 0 366 584 L366 574" />
          <g clipPath="url(#desk-lamp-base)" className="lamp-hatch"><path d="M236 572 L230 598 M244 572 L238 598 M252 572 L246 598 M260 572 L254 598 M268 572 L262 598 M276 572 L270 598 M284 572 L278 598 M292 572 L286 598 M300 572 L294 598 M308 572 L302 598 M316 572 L310 598 M324 572 L318 598 M332 572 L326 598 M340 572 L334 598 M348 572 L342 598 M356 572 L350 598 M364 572 L358 598 M372 572 L366 598" /></g>
          <ellipse className="lamp-body" cx="300" cy="574" rx="66" ry="11" />
          <ellipse className="lamp-soft" cx="300" cy="573" rx="44" ry="6.5" />
          <rect className="lamp-body" x="336" y="562" width="13" height="9" rx="2.5" />
          <path d="M296 572 L296 552 M304 572 L304 552" />
          <ellipse className="lamp-body" cx="300" cy="552" rx="8" ry="3" />
          <circle className="lamp-body" cx="300" cy="546" r="7.5" />
          <circle cx="300" cy="546" r="2.4" />
          <path d="M302.9 546.6 L354.9 300.6 M297.1 545.4 L349.1 299.4" />
          <path className="lamp-soft" d="M320 509.3 L324.3 504.7 L319.1 498.1 L326.5 494.1 L321.4 487.5 L328.7 483.5 L323.6 476.9 L331 472.9 L325.8 466.3 L333.2 462.3 L328.1 455.7 L335.5 451.7 L330.3 445.1 L337.7 441.1 L332.6 434.5 L339.9 430.5 L334.8 423.9 L342.2 419.9 L337 413.3 L344.4 409.3 L339.3 402.7 L346.7 398.7 L341.5 392.1 L348.9 388.1 L346.9 382.2 M303.4 538 L320 509.3 M346.9 382.2 L351 318" />
          <circle className="lamp-body" cx="352" cy="300" r="9.5" />
          <circle cx="352" cy="300" r="3" />
          <path d="M361 296.5 L371 292.5" />
          <circle className="lamp-body" cx="375" cy="291" r="4.2" />
          <path d="M354 297.8 L152 117.8 M350 302.2 L148 122.2" />
          <path className="lamp-soft" d="M314.2 282.3 L312.5 276.6 L304.6 278.1 L305.1 270 L297.1 271.4 L297.6 263.3 L289.6 264.8 L290.2 256.7 L282.2 258.1 L282.7 250 L274.7 251.5 L275.2 243.4 L267.2 244.8 L267.8 236.7 L259.8 238.2 L260.3 230.1 L252.3 231.5 L252.8 223.4 L244.8 224.9 L245.4 216.8 L237.4 218.2 L237.9 210.1 L229.9 211.6 L230.4 203.5 L224.6 202.5 M341 300 L314.2 282.3 M224.6 202.5 L172 152" />
          <circle className="lamp-body" cx="150" cy="120" r="8.5" />
          <circle cx="150" cy="120" r="2.6" />
          <path className="lamp-body" d="M128.8 118.4 Q87.2 129.6 54 132 L111.6 208.8 Q123.2 177.6 145.6 140.8 Z" />
          <g clipPath="url(#desk-lamp-shade)" className="lamp-hatch"><path d="M40 110 L-10 215 M47 110 L-3 215 M54 110 L4 215 M61 110 L11 215 M68 110 L18 215 M75 110 L25 215 M82 110 L32 215 M89 110 L39 215 M96 110 L46 215 M103 110 L53 215 M110 110 L60 215 M117 110 L67 215 M124 110 L74 215 M131 110 L81 215 M138 110 L88 215 M145 110 L95 215 M152 110 L102 215 M159 110 L109 215 M166 110 L116 215" /></g>
          <path className="lamp-soft" d="M131 121 Q95 131 60 134" />
        </g>
        <ellipse className="lamp-halo" cx="82.8" cy="170.4" rx="54" ry="18" transform="rotate(-126.87 82.8 170.4)" />
        <ellipse className="lamp-mouth" cx="82.8" cy="170.4" rx="48" ry="11" transform="rotate(-126.87 82.8 170.4)" />
        <ellipse className="lamp-filament" cx="87" cy="166.5" rx="15" ry="8" transform="rotate(-126.87 87 166.5)" />
      </svg>
      <span className={cn(state, "lamp-bloom desk-lamp-bloom")} aria-hidden="true" />
    </>
  );
}

/** A reading light clipped to the host's top edge near its right corner, bent over the content. */
export function ClipLamp({ lit, className }: LampProps) {
  const state = cn("lamp", lit && "is-lit", className);
  return (
    <>
      <div className={cn(state, "clip-lamp-beam")} aria-hidden="true"><span /></div>
      <span className={cn(state, "lamp-pool clip-lamp-pool")} aria-hidden="true" />
      <svg className={cn(state, "clip-lamp-drawing")} viewBox="0 0 260 110" aria-hidden="true">
        <g className="lamp-strokes" style={graphite}>
          <path d="M212 82 C212 30 120 14 42.5 33" strokeWidth="2.2" />
          <path className="lamp-cord-core" d="M212 82 C212 30 120 14 42.5 33" />
          <rect className="lamp-body" x="205" y="81" width="14" height="17" rx="3" />
          <path d="M219 86 L233 79" />
          <path className="lamp-body" d="M35.5 32.3 L21.7 50 L59.5 53.8 L49.5 33.7 Z" />
        </g>
        <ellipse className="lamp-halo" cx="40.6" cy="51.9" rx="24" ry="9" transform="rotate(-174.3 40.6 51.9)" />
        <ellipse className="lamp-mouth" cx="40.6" cy="51.9" rx="19" ry="4.4" transform="rotate(-174.3 40.6 51.9)" />
      </svg>
      <span className={cn(state, "lamp-bloom clip-lamp-bloom")} aria-hidden="true" />
    </>
  );
}

/**
 * A wall sconce on the navigation's right wall. It rides a rail to the active
 * item: the host sets `--sconce-index` and every item is one `--sconce-pitch` tall.
 */
export function Sconce({ lit, className }: LampProps) {
  const state = cn("lamp", lit && "is-lit", className);
  return (
    <>
      <svg className={cn(state, "sconce-beam")} viewBox="0 0 236 200" aria-hidden="true">
        <defs>
          <radialGradient id="sconce-light" cx="188" cy="75" r="190" gradientUnits="userSpaceOnUse">
            <stop offset="0" className="sconce-stop-0" />
            <stop offset=".45" className="sconce-stop-1" />
            <stop offset="1" className="sconce-stop-2" />
          </radialGradient>
          <filter id="sconce-soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="6" /></filter>
        </defs>
        <path d="M6 126 L7.7 120.8 L12.8 115.7 L21 111 L32.2 106.7 L181 63.8 L228.3 120.8 L230 126 L228.3 131.2 L223.2 136.3 L215 141 L203.8 145.3 L190 149 L174 152 L156.3 154.2 L137.4 155.5 L118 156 L98.5 155.5 L79.7 154.2 L62 152 L46 149 L32.2 145.3 L21 141 L12.8 136.3 L7.7 131.2 Z" fill="url(#sconce-light)" filter="url(#sconce-soft)" />
      </svg>
      <svg className={cn(state, "sconce-drawing")} viewBox="0 0 236 110" aria-hidden="true">
        <g className="lamp-strokes" style={graphite} strokeWidth="1.3">
          <rect className="lamp-body" x="227" y="44" width="9" height="28" rx="2.5" />
          <path d="M227 56.6 L210.2 60.2 M227 59.6 L210.6 63.6" />
          <circle className="lamp-body" cx="210" cy="62" r="3.8" />
          <path className="lamp-body" d="M202.3 60.7 L181 63.8 L194.1 86.3 L207.3 69.3 Z" />
        </g>
        <ellipse className="lamp-halo" cx="187.5" cy="75.1" rx="18" ry="8" transform="rotate(-120.19 187.5 75.1)" />
        <ellipse className="lamp-mouth" cx="187.5" cy="75.1" rx="13" ry="3.4" transform="rotate(-120.19 187.5 75.1)" />
      </svg>
    </>
  );
}
