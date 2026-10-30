import * as React from "react";
import rough from "roughjs";
import { cn } from "@/lib/utils";

/**
 * Pencil drawing primitives (see DESIGN.md › Pencil and paper).
 *
 * Shapes come from rough.js's generator and render as plain React paths in
 * `currentColor`, so they follow the theme. Every shape takes a fixed seed:
 * the same element is drawn the same way on every render instead of jittering.
 */

export const pencil = rough.generator();

export type Drawable = ReturnType<typeof pencil.line>;

/** Soft graphite defaults: slightly bowed, double stroked, thin. */
export const graphite = {
  roughness: 1.1,
  bowing: 0.9,
  strokeWidth: 1.15,
  stroke: "currentColor",
  fill: undefined,
} as const;

export function SketchPaths({ shapes, className, fillOpacity }: { shapes: Drawable[]; className?: string; fillOpacity?: number }) {
  const paths = React.useMemo(() => shapes.flatMap((shape) => pencil.toPaths(shape)), [shapes]);
  return (
    <g className={className}>
      {paths.map((path, index) => (
        <path
          key={index}
          d={path.d}
          stroke={path.stroke === "none" ? "none" : "currentColor"}
          strokeWidth={path.strokeWidth}
          fill={path.fill && path.fill !== "none" ? "currentColor" : "none"}
          fillOpacity={path.fill && path.fill !== "none" ? fillOpacity ?? 0.5 : undefined}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
    </g>
  );
}

function useElementSize<T extends HTMLElement>() {
  const [node, setNode] = React.useState<T | null>(null);
  const [size, setSize] = React.useState({ width: 0, height: 0 });
  React.useLayoutEffect(() => {
    if (!node) return;
    const update = () => setSize({ width: Math.round(node.clientWidth), height: Math.round(node.clientHeight) });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);
  return [setNode, size] as const;
}

type SketchFrameProps = React.HTMLAttributes<HTMLDivElement> & {
  seed?: number;
  /** Corner flourishes drawn outside the frame. */
  ornate?: boolean;
  as?: "div" | "section" | "article";
};

/** A region framed by a hand-drawn rectangle instead of a 1px box. */
export function SketchFrame({ seed = 7, ornate = false, className, children, as = "div", ...props }: SketchFrameProps) {
  const [ref, { width, height }] = useElementSize<HTMLDivElement>();
  const shapes = React.useMemo(() => {
    if (!width || !height) return [];
    return [pencil.rectangle(2, 2, width - 4, height - 4, { ...graphite, seed, roughness: 0.9 })];
  }, [width, height, seed]);
  const Component = as;
  return (
    <Component ref={ref} className={cn("sketch-frame", className)} {...props}>
      <svg className="sketch-overlay" width={width} height={height} aria-hidden="true">
        <SketchPaths shapes={shapes} />
      </svg>
      {ornate && width ? <CornerCurls width={width} height={height} /> : null}
      {children}
    </Component>
  );
}

/** A drawn horizontal rule that stretches to its container. */
export function SketchRule({ seed = 3, className }: { seed?: number; className?: string }) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const shapes = React.useMemo(
    () => (width ? [pencil.line(1, 4, width - 1, 4, { ...graphite, seed, roughness: 0.7, bowing: 1.6 })] : []),
    [width, seed],
  );
  return (
    <div ref={ref} className={cn("sketch-rule", className)} aria-hidden="true">
      <svg width={width} height={8}><SketchPaths shapes={shapes} /></svg>
    </div>
  );
}

function CornerCurls({ width, height }: { width: number; height: number }) {
  // A small curl at the top-left and bottom-right corners, mirrored.
  const curl = "M2 22 C2 9 9 2 22 2 M8 2 C2 5 3 13 9 12 C14 11 12 5 8 7";
  return (
    <svg className="sketch-overlay sketch-curls" width={width} height={height} aria-hidden="true">
      <path d={curl} transform="translate(-6 -6)" />
      <path d={curl} transform={`translate(${width + 6} ${height + 6}) rotate(180)`} />
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

/** Global SVG filters: a faint wobble that makes vector strokes read as graphite. */
export function PencilDefs() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true" focusable="false">
      <defs>
        <filter id="pencil-texture" x="-5%" y="-5%" width="110%" height="110%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="4" result="grain" />
          <feDisplacementMap in="SourceGraphic" in2="grain" scale="1.4" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
    </svg>
  );
}
