import type { Point, Rect } from "./geometry";
import { add, center, mouthSegment, normalize, scale, sub } from "./geometry";

/**
 * Lamp models in scene coordinates. Each lamp is positioned relative to the
 * element it lights and exposes the exact segment its light leaves from.
 */

export type LampKind = "desk" | "pendant" | "sconce";

export type LampModel = {
  /** Straight strokes (arms, cords, poles). */
  lines: Array<[Point, Point]>;
  /** Joints and bases as ellipses: centre, horizontal and vertical diameter. */
  ellipses: Array<{ c: Point; w: number; h: number }>;
  /** Closed shade outline, hatched. */
  shade: Point[];
  /** Optional curved shade outline as an SVG path (domes). */
  shadePath?: string;
  mouth: [Point, Point];
  bulb: Point;
  /** A cord that fades upwards into the dark, from `[top, bottom]`. */
  cord?: [Point, Point];
  /** Where a pull chain ends, if the lamp has one. */
  chainEnd?: Point;
};

type SceneSize = { width: number; height: number };

export function lampModel(kind: LampKind, target: Rect, scene: SceneSize): LampModel {
  if (kind === "pendant") return pendantLamp(target);
  if (kind === "sconce") return sconce(target, scene);
  return deskLamp(target);
}

/** An architect's lamp standing on the "desk line" left of its subject, leaning over its top-left corner. */
function deskLamp(target: Rect): LampModel {
  const aimPoint = { x: target.x + target.width * 0.3, y: target.y + target.height * 0.52 };
  const mouthCentre = { x: target.x - 2, y: target.y - 22 };
  const aim = normalize(sub(aimPoint, mouthCentre));
  const mouth = mouthSegment(mouthCentre, aim, 30);
  const apex = sub(mouthCentre, scale(aim, 42));
  const back = mouthSegment(apex, aim, 9);
  const joint = sub(apex, scale(aim, 7));
  const base = { x: target.x - 92, y: target.y + target.height - 2 };
  const elbow = { x: base.x - 44, y: joint.y + (base.y - joint.y) * 0.5 };
  return {
    lines: [...doubleLine({ x: base.x, y: base.y - 6 }, elbow, 4), ...doubleLine(elbow, joint, 4)],
    ellipses: [
      { c: base, w: 92, h: 14 },
      { c: elbow, w: 13, h: 13 },
      { c: joint, w: 11, h: 11 },
    ],
    shade: [back[0], mouth[0], mouth[1], back[1]],
    mouth,
    bulb: sub(mouthCentre, scale(aim, 7)),
  };
}

/** A dome pendant hanging straight above its subject. */
function pendantLamp(target: Rect): LampModel {
  const cx = target.x + target.width / 2;
  const mouthY = target.y - 46;
  const half = 34;
  const top = mouthY - 34;
  const cordTop = Math.max(0, top - 40);
  return {
    lines: [],
    cord: [{ x: cx, y: cordTop }, { x: cx, y: top - 7 }],
    ellipses: [{ c: { x: cx, y: top - 4 }, w: 12, h: 7 }],
    shade: [],
    shadePath: `M${cx - half} ${mouthY} C${cx - half} ${top + 6} ${cx - 16} ${top} ${cx} ${top} C${cx + 16} ${top} ${cx + half} ${top + 6} ${cx + half} ${mouthY} Z`,
    mouth: [{ x: cx - half + 2, y: mouthY }, { x: cx + half - 2, y: mouthY }],
    bulb: { x: cx, y: mouthY - 6 },
  };
}

/** A wall sconce on the right wall of the navigation, turning towards the active item. */
function sconce(target: Rect, scene: SceneSize): LampModel {
  const wall = { x: scene.width - 4, y: 90 };
  const pivot = { x: wall.x - 34, y: wall.y + 4 };
  const aim = normalize(sub(center(target), pivot));
  const mouthCentre = add(pivot, scale(aim, 28));
  const mouth = mouthSegment(mouthCentre, aim, 16);
  const back = mouthSegment(add(pivot, scale(aim, 4)), aim, 6);
  const chainTop = { x: mouthCentre.x, y: mouthCentre.y + 6 };
  return {
    lines: [[{ x: wall.x, y: wall.y - 16 }, { x: wall.x, y: wall.y + 16 }], ...doubleLine(wall, pivot, 3), [chainTop, { x: chainTop.x, y: chainTop.y + 30 }]],
    ellipses: [{ c: pivot, w: 7, h: 7 }],
    shade: [back[0], mouth[0], mouth[1], back[1]],
    mouth,
    bulb: sub(mouthCentre, scale(aim, 4)),
    chainEnd: { x: chainTop.x, y: chainTop.y + 34 },
  };
}

function doubleLine(a: Point, b: Point, gap: number): Array<[Point, Point]> {
  const direction = normalize(sub(b, a));
  const offset = scale({ x: -direction.y, y: direction.x }, gap / 2);
  return [
    [add(a, offset), add(b, offset)],
    [sub(a, offset), sub(b, offset)],
  ];
}

export { center };
