import * as React from "react";
import { cn } from "@/lib/utils";
import { SketchPaths, graphite, pencil } from "@/components/sketch/sketch";

/**
 * Light sources and their rays — the signature of the "Night reading" world
 * (DESIGN.md › Light). A lamp is always drawn together with its beam so the
 * cone leaves exactly from the shade. Lamps are lit in the night theme and
 * unlit (but still drawn) by day.
 */

type BeamProps = {
  /** Width of the beam where it leaves the shade, px. */
  mouth: number;
  /** Width of the beam where it lands, px. */
  spread: number;
  length: number;
  /** Rotation in degrees; 0 points straight down. */
  angle?: number;
  intensity?: number;
  dust?: boolean;
  className?: string;
  style?: React.CSSProperties;
};

/** A volumetric cone of light with rays, a landing pool and drifting dust. */
export function LightBeam({ mouth, spread, length, angle = 0, intensity = 1, dust = true, className, style }: BeamProps) {
  const inset = Math.max(0, (spread - mouth) / 2);
  const cone = `polygon(${inset}px 0, ${inset + mouth}px 0, ${spread}px 100%, 0 100%)`;
  return (
    <div
      className={cn("light-beam", className)}
      aria-hidden="true"
      style={{
        width: spread,
        height: length,
        marginLeft: -spread / 2,
        transform: `rotate(${angle}deg)`,
        ["--beam-intensity" as string]: intensity,
        ...style,
      }}
    >
      <div className="light-beam-cone" style={{ clipPath: cone }} />
      <div className="light-beam-rays" style={{ clipPath: cone }} />
      <div className="light-beam-pool" />
      {dust ? <DustMotes mouth={mouth} spread={spread} length={length} /> : null}
    </div>
  );
}

/** A few slow motes drifting inside the cone; paused when hidden or with reduced motion. */
function DustMotes({ mouth, spread, length }: { mouth: number; spread: number; length: number }) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  React.useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = spread * ratio;
    canvas.height = length * ratio;
    context.scale(ratio, ratio);

    // Deterministic pseudo-random so motes start in the same places each time.
    let seed = 17;
    const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const halfAt = (y: number) => (mouth + (spread - mouth) * (y / length)) / 2;
    const motes = Array.from({ length: 26 }, () => {
      const y = random() * length;
      return { y, x: spread / 2 + (random() * 2 - 1) * halfAt(y) * 0.85, r: 0.5 + random() * 1.3, vx: (random() - 0.5) * 0.07, vy: -0.02 - random() * 0.05, phase: random() * Math.PI * 2 };
    });
    const color = getComputedStyle(canvas).color;

    let frame = 0;
    let running = !reduce;
    const draw = (time: number) => {
      context.clearRect(0, 0, spread, length);
      for (const mote of motes) {
        if (running) {
          mote.x += mote.vx + Math.sin(time / 2400 + mote.phase) * 0.04;
          mote.y += mote.vy;
          if (mote.y < 0) mote.y = length;
          const half = halfAt(mote.y) * 0.9;
          if (Math.abs(mote.x - spread / 2) > half) mote.vx *= -1;
        }
        // Brighter near the shade, fading towards the floor.
        const alpha = (0.75 - (mote.y / length) * 0.55) * (0.6 + 0.4 * Math.sin(time / 1300 + mote.phase));
        context.globalAlpha = Math.max(0, alpha);
        context.fillStyle = color;
        context.beginPath();
        context.arc(mote.x, mote.y, mote.r, 0, Math.PI * 2);
        context.fill();
      }
      if (running) frame = requestAnimationFrame(draw);
    };
    const onVisibility = () => {
      cancelAnimationFrame(frame);
      running = !reduce && document.visibilityState === "visible";
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [mouth, spread, length]);
  return <canvas ref={canvasRef} className="light-dust" style={{ width: spread, height: length }} />;
}

/** A glowing bulb: a soft halo that only exists when the lamp is lit. */
function Bulb({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return (
    <g className="lamp-bulb">
      <circle cx={cx} cy={cy} r={r * 3.2} className="lamp-halo" />
      <circle cx={cx} cy={cy} r={r} className="lamp-filament" />
    </g>
  );
}

/** An articulated desk lamp leaning over its subject from the top-left. */
export function DeskLamp({ className, beamLength = 250, beamSpread = 300 }: { className?: string; beamLength?: number; beamSpread?: number }) {
  const shapes = React.useMemo(() => {
    const line = { ...graphite, seed: 21 };
    return [
      pencil.ellipse(42, 286, 74, 16, { ...line, seed: 22 }),
      pencil.line(42, 280, 60, 142, line),
      pencil.line(48, 280, 65, 144, { ...line, seed: 23, roughness: 0.6 }),
      pencil.circle(62, 140, 11, { ...line, seed: 24 }),
      pencil.line(66, 136, 148, 64, line),
      pencil.line(70, 143, 151, 70, { ...line, seed: 25, roughness: 0.6 }),
      pencil.circle(152, 62, 9, { ...line, seed: 26 }),
      // Shade: a cone opening downwards to the right.
      pencil.polygon([[146, 52], [166, 44], [210, 94], [172, 116]], { ...line, seed: 27, fill: "currentColor", fillStyle: "hachure", hachureGap: 5, hachureAngle: -30, fillWeight: 0.5 }),
      pencil.curve([[172, 116], [192, 110], [210, 94]], { ...line, seed: 28 }),
    ];
  }, []);
  return (
    <div className={cn("lamp lamp-desk", className)} aria-hidden="true">
      <svg viewBox="0 0 220 300" className="lamp-drawing">
        <SketchPaths shapes={shapes} fillOpacity={0.35} />
        <Bulb cx={191} cy={106} r={4.5} />
      </svg>
      <LightBeam className="lamp-desk-beam" mouth={34} spread={beamSpread} length={beamLength} angle={-46} />
    </div>
  );
}

/** A tall floor lamp at the edge of the room; its pull cord switches the light. */
export function FloorLamp({ className, onPull, lit }: { className?: string; onPull?: () => void; lit: boolean }) {
  const shapes = React.useMemo(() => {
    const line = { ...graphite, seed: 41 };
    return [
      pencil.ellipse(60, 560, 86, 18, { ...line, seed: 42 }),
      pencil.line(60, 556, 60, 96, { ...line, roughness: 0.5 }),
      pencil.line(63, 556, 63, 98, { ...line, seed: 43, roughness: 0.4, strokeWidth: 0.7 }),
      // Drum shade, wider at the bottom.
      pencil.polygon([[30, 30], [90, 30], [108, 96], [12, 96]], { ...line, seed: 44, fill: "currentColor", fillStyle: "hachure", hachureGap: 6, hachureAngle: 60, fillWeight: 0.45 }),
      pencil.ellipse(60, 96, 96, 10, { ...line, seed: 45 }),
    ];
  }, []);
  const cord = React.useMemo(() => [pencil.line(86, 96, 86, 150, { ...graphite, seed: 46, roughness: 0.6, strokeWidth: 0.8 })], []);
  return (
    <div className={cn("lamp lamp-floor", className)}>
      <svg viewBox="0 0 120 572" className="lamp-drawing" aria-hidden="true">
        <SketchPaths shapes={shapes} fillOpacity={0.3} />
        <Bulb cx={60} cy={90} r={5} />
      </svg>
      <LightBeam className="lamp-floor-beam" mouth={96} spread={340} length={470} dust={false} intensity={0.7} />
      <button type="button" className="lamp-cord" onClick={onPull} aria-label={lit ? "Включить дневной свет" : "Включить вечерний свет"} title={lit ? "Дневной свет" : "Вечерний свет"}>
        <svg viewBox="80 92 12 70" aria-hidden="true">
          <SketchPaths shapes={cord} />
          <circle cx="86" cy="154" r="3.6" className="lamp-cord-bead" />
        </svg>
      </button>
    </div>
  );
}

/** A small wall sconce that lights the navigation. */
export function Sconce({ className }: { className?: string }) {
  const shapes = React.useMemo(() => {
    const line = { ...graphite, seed: 61 };
    return [
      pencil.rectangle(6, 18, 8, 26, { ...line, seed: 62 }),
      pencil.curve([[14, 31], [26, 30], [34, 22]], { ...line, seed: 63 }),
      pencil.polygon([[26, 4], [44, 4], [52, 24], [18, 24]], { ...line, seed: 64, fill: "currentColor", fillStyle: "hachure", hachureGap: 4, hachureAngle: 70, fillWeight: 0.4 }),
    ];
  }, []);
  return (
    <div className={cn("lamp lamp-sconce", className)} aria-hidden="true">
      <svg viewBox="0 0 60 48" className="lamp-drawing">
        <SketchPaths shapes={shapes} fillOpacity={0.3} />
        <Bulb cx={35} cy={23} r={3} />
      </svg>
      <LightBeam className="lamp-sconce-beam" mouth={30} spread={190} length={150} dust={false} intensity={0.55} />
    </div>
  );
}

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
