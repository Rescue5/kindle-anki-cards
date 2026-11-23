import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DeskLamp } from "./lamps";
import { MascotLamp } from "./mascot-lamp";

describe("mascot lamp", () => {
  it("keeps mascot drawing opt-in and preserves the light source", () => {
    const original = renderToStaticMarkup(<DeskLamp lit />);
    const mascot = renderToStaticMarkup(<DeskLamp lit mascot />);
    expect(original).not.toContain("mascot-ear");
    expect(mascot).toContain("mascot-ear-left");
    expect(mascot).toContain("mascot-ear-right");
    expect(mascot).toContain("mascot-squint");
    const mouth = /<ellipse class="lamp-mouth"[^>]+/;
    expect(mascot.match(mouth)?.[0]).toBe(original.match(mouth)?.[0]);
    expect(mascot).toContain("desk-lamp-cone");
  });
  it("offers a real greeting button without opening a bubble or enabling motion on first render", () => {
    for (const phase of ["preparing", "ready"] as const) {
      const markup = renderToStaticMarkup(<MascotLamp phase={phase} motion={false} />);
      expect(markup).toMatch(/<button[^>]*aria-label="Поприветствовать лампу"[^>]*aria-expanded="false"/);
      expect(markup).not.toContain('role="region"');
      expect(markup).not.toContain("mascot-motion");
    }
  });
});
