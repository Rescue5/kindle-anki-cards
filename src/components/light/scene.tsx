import * as React from "react";
import { cn } from "@/lib/utils";
import { SketchPaths, graphite, pencil } from "@/components/sketch/sketch";
import { beamPolygon, center, inflate, lerp, pointInPolygon, toPath, type Point, type Rect } from "./geometry";
import { lampModel, type LampKind, type LampModel } from "./lamps";

/**
 * A light scene: lamps aimed at the important parts of a screen (DESIGN.md › Light).
 *
 * Wrap a screen in <LightScene> and mark what matters with <Lit lamp="…">. The
 * scene measures those elements, places each lamp relative to its subject and
 * draws the beam as the exact hull between the shade's mouth and the subject.
 * Empty areas stay in shadow. Layers: shadow and cones below the content (text
 * stays crisp), a soft glaze on the lit element and the lamps above it.
 */

type RegionOptions = { lamp: LampKind; strength: number; follow: boolean };
type Registry = { register: (id: string, element: HTMLElement, options: RegionOptions) => () => void };
const SceneContext = React.createContext<Registry | null>(null);

type Measured = RegionOptions & { id: string; rect: Rect };

export function LightScene({ children, className, onPullChain, chainLabel }: { children: React.ReactNode; className?: string; onPullChain?: () => void; chainLabel?: string }) {
  const uid = React.useId().replace(/[^a-zA-Z0-9]/g, "");
  const containerRef = React.useRef<HTMLDivElement>(null);
  const regions = React.useRef(new Map<string, { element: HTMLElement; options: RegionOptions }>());
  const [measured, setMeasured] = React.useState<Measured[]>([]);
  const [size, setSize] = React.useState({ width: 0, height: 0 });

  const measure = React.useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const origin = container.getBoundingClientRect();
    setSize({ width: container.offsetWidth, height: container.offsetHeight });
    setMeasured(
      [...regions.current.entries()].map(([id, { element, options }]) => {
        const box = element.getBoundingClientRect();
        return { id, ...options, rect: { x: box.left - origin.left, y: box.top - origin.top, width: box.width, height: box.height } };
      }),
    );
  }, []);

  const observer = React.useMemo(() => (typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => measure())), [measure]);

  React.useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container || !observer) return;
    observer.observe(container);
    measure();
    void document.fonts?.ready.then(measure);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [measure, observer]);

  const registry = React.useMemo<Registry>(
    () => ({
      register(id, element, options) {
        regions.current.set(id, { element, options });
        observer?.observe(element);
        measure();
        return () => {
          regions.current.delete(id);
          observer?.unobserve(element);
          measure();
        };
      },
    }),
    [measure, observer],
  );

  const shown = useFollow(measured);
  const lights = shown.map((region) => {
    const model = lampModel(region.lamp, region.rect, size);
    const landing = inflate(region.rect, 4);
    return { region, model, beam: beamPolygon(model.mouth, landing) };
  });
  const chain = lights.find((light) => light.model.chainEnd);

  return (
    <SceneContext.Provider value={registry}>
      <div ref={containerRef} className={cn("light-scene", className)}>
        <svg className="scene-layer scene-shadow" width={size.width} height={size.height} aria-hidden="true">
          <defs>
            <filter id={`${uid}-soft`} x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="34" /></filter>
            <mask id={`${uid}-lit`} maskUnits="userSpaceOnUse" x="0" y="0" width={size.width} height={size.height}>
              <rect width={size.width} height={size.height} fill="white" />
              <g filter={`url(#${uid}-soft)`}>
                {lights.map(({ region, beam }) => <path key={region.id} d={toPath(beam)} fill="black" opacity={0.55 + 0.45 * region.strength} />)}
              </g>
            </mask>
          </defs>
          <rect className="scene-shadow-fill" width={size.width} height={size.height} mask={`url(#${uid}-lit)`} />
        </svg>
        <svg className="scene-layer scene-light" width={size.width} height={size.height} aria-hidden="true">
          <defs>
            <filter id={`${uid}-cone`} x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="12" /></filter>
            {lights.map(({ region, model }) => {
              const from = lerp(model.mouth[0], model.mouth[1], 0.5);
              const to = center(region.rect);
              return (
                <linearGradient key={region.id} id={`${uid}-beam-${safe(region.id)}`} gradientUnits="userSpaceOnUse" x1={from.x} y1={from.y} x2={to.x} y2={to.y + region.rect.height / 2}>
                  <stop offset="0" className="beam-stop-0" />
                  <stop offset="0.45" className="beam-stop-1" />
                  <stop offset="1" className="beam-stop-2" />
                </linearGradient>
              );
            })}
          </defs>
          {lights.map(({ region, beam }) => (
            <path key={region.id} d={toPath(beam)} fill={`url(#${uid}-beam-${safe(region.id)})`} filter={`url(#${uid}-cone)`} opacity={region.strength} />
          ))}
        </svg>
        <DustLayer polygons={lights.map((light) => light.beam)} width={size.width} height={size.height} />
        {children}
        <svg className="scene-layer scene-glaze" width={size.width} height={size.height} aria-hidden="true">
          <defs>
            {lights.map(({ region }) => {
              return (
                <radialGradient key={region.id} id={`${uid}-pool-${safe(region.id)}`}>
                  <stop offset="0" className="pool-stop-0" />
                  <stop offset="1" className="pool-stop-1" />
                </radialGradient>
              );
            })}
          </defs>
          {lights.map(({ region }) => {
            const c = center(region.rect);
            return <ellipse key={region.id} cx={c.x} cy={c.y} rx={region.rect.width * 0.62} ry={region.rect.height * 0.66} fill={`url(#${uid}-pool-${safe(region.id)})`} opacity={region.strength} />;
          })}
        </svg>
        <svg className="scene-layer scene-lamps" width={size.width} height={size.height} aria-hidden="true">
          {lights.map(({ region, model }) => <LampDrawing key={region.id} model={model} />)}
        </svg>
        {chain?.model.chainEnd && onPullChain ? (
          <button
            type="button"
            className="lamp-chain"
            style={{ left: chain.model.chainEnd.x - 9, top: chain.model.chainEnd.y - 9 }}
            onClick={onPullChain}
            aria-label={chainLabel}
            title={chainLabel}
          />
        ) : null}
      </div>
    </SceneContext.Provider>
  );
}

const safe = (id: string) => id.replace(/[^a-zA-Z0-9]/g, "");

/** Marks an element as the subject of a lamp. */
export function Lit({ lamp, strength = 1, follow = false, children, className, as: Component = "div", ...rest }: { lamp: LampKind; strength?: number; follow?: boolean; as?: "div" | "section" | "span" } & React.HTMLAttributes<HTMLElement>) {
  const registry = React.useContext(SceneContext);
  const id = React.useId();
  const ref = React.useRef<HTMLElement>(null);
  React.useLayoutEffect(() => {
    if (!registry || !ref.current) return;
    return registry.register(id, ref.current, { lamp, strength, follow });
  }, [registry, id, lamp, strength, follow]);
  return React.createElement(Component, { ref, className: cn("lit", className), ...rest }, children);
}

/** Lamps that follow their subject (the nav sconce) turn smoothly instead of jumping. */
function useFollow(measured: Measured[]): Measured[] {
  const [shown, setShown] = React.useState(measured);
  const previous = React.useRef(new Map<string, Rect>());
  React.useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const starts = new Map(previous.current);
    const animated = measured.some((region) => region.follow && starts.has(region.lamp) && !reduce);
    measured.forEach((region) => previous.current.set(region.lamp, region.rect));
    if (!animated) {
      setShown(measured);
      return;
    }
    let frame = 0;
    const began = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - began) / 260);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(measured.map((region) => {
        const from = region.follow ? starts.get(region.lamp) : undefined;
        if (!from) return region;
        const a = lerp({ x: from.x, y: from.y }, { x: region.rect.x, y: region.rect.y }, eased);
        const b = lerp({ x: from.width, y: from.height }, { x: region.rect.width, y: region.rect.height }, eased);
        return { ...region, rect: { x: a.x, y: a.y, width: b.x, height: b.y } };
      }));
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [measured]);
  return shown;
}

function LampDrawing({ model }: { model: LampModel }) {
  const shapes = React.useMemo(() => {
    const line = { ...graphite, roughness: 0.35, bowing: 0.4, seed: 5 };
    const result = [
      ...model.lines.map(([a, b], index) => pencil.line(a.x, a.y, b.x, b.y, { ...line, seed: 11 + index })),
      ...model.ellipses.map((ellipse, index) => pencil.ellipse(ellipse.c.x, ellipse.c.y, ellipse.w, ellipse.h, { ...line, seed: 31 + index })),
    ];
    const hatch = { ...line, seed: 51, fill: "currentColor", fillStyle: "hachure" as const, hachureGap: 3.2, hachureAngle: 52, fillWeight: 0.55 };
    if (model.shade.length) result.push(pencil.polygon(model.shade.map((p) => [p.x, p.y] as [number, number]), hatch));
    if (model.shadePath) result.push(pencil.path(model.shadePath, hatch));
    return result;
    // Re-roll only when the geometry moves by at least a pixel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(model, (_, value) => (typeof value === "number" ? Math.round(value) : value))]);
  return (
    <g className="lamp-model">
      {model.cord ? <CordLine from={model.cord[0]} to={model.cord[1]} /> : null}
      <circle cx={model.bulb.x} cy={model.bulb.y} r={14} className="lamp-halo" />
      <SketchPaths shapes={shapes} fillOpacity={0.4} />
      <circle cx={model.bulb.x} cy={model.bulb.y} r={3.4} className="lamp-filament" />
      {model.chainEnd ? <circle cx={model.chainEnd.x} cy={model.chainEnd.y} r={3.2} className="lamp-chain-bead" /> : null}
    </g>
  );
}

function CordLine({ from, to }: { from: Point; to: Point }) {
  const id = React.useId().replace(/[^a-zA-Z0-9]/g, "");
  return (
    <>
      <defs>
        <linearGradient id={id} gradientUnits="userSpaceOnUse" x1={from.x} y1={from.y} x2={to.x} y2={to.y}>
          <stop offset="0" stopColor="currentColor" stopOpacity="0" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0.9" />
        </linearGradient>
      </defs>
      <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={`url(#${id})`} strokeWidth={1.1} />
    </>
  );
}

/** Slow dust motes inside the beams; paused when hidden, static with reduced motion. */
function DustLayer({ polygons, width, height }: { polygons: Point[][]; width: number; height: number }) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const key = JSON.stringify(polygons.map((polygon) => polygon.map((p) => [Math.round(p.x), Math.round(p.y)])));
  React.useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context || !width || !height || !polygons.length) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let seed = 23;
    const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const motes = polygons.flatMap((polygon, index) => {
      const xs = polygon.map((p) => p.x);
      const ys = polygon.map((p) => p.y);
      const box = { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
      const result: Array<{ x: number; y: number; r: number; phase: number; drift: number; polygon: number; box: typeof box }> = [];
      for (let attempt = 0; attempt < 200 && result.length < 18; attempt += 1) {
        const point = { x: box.x + random() * box.w, y: box.y + random() * box.h };
        if (pointInPolygon(point, polygon)) result.push({ ...point, r: 0.5 + random() * 1.2, phase: random() * Math.PI * 2, drift: 0.03 + random() * 0.05, polygon: index, box });
      }
      return result;
    });
    const color = getComputedStyle(canvas).color;
    let frame = 0;
    let running = !reduce && document.visibilityState === "visible";
    const draw = (time: number) => {
      context.clearRect(0, 0, width, height);
      context.fillStyle = color;
      for (const mote of motes) {
        if (running) {
          const next = { x: mote.x + Math.sin(time / 2600 + mote.phase) * 0.06, y: mote.y - mote.drift };
          if (pointInPolygon(next, polygons[mote.polygon])) Object.assign(mote, next);
          else mote.y = mote.box.y + mote.box.h * (0.6 + Math.random() * 0.4);
        }
        context.globalAlpha = 0.35 + 0.35 * Math.sin(time / 1400 + mote.phase);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, width, height]);
  return <canvas ref={canvasRef} className="scene-layer scene-dust" style={{ width, height }} aria-hidden="true" />;
}
