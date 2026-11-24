import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FoxLantern } from "./fox-lantern";

describe("FoxLantern", () => {
  it("offers a persistent speech switch and no click greeting or automatic speech on render", () => {
    const markup = renderToStaticMarkup(<FoxLantern />);
    expect(markup).toMatch(/<button[^>]*aria-label="Реплики лиса"[^>]*aria-pressed="true"/);
    expect(markup).not.toContain("Поприветствовать лиса");
    expect(markup).not.toContain('role="region"');
  });
  it("keeps a static, quiet scene available without removing its control", () => {
    const markup = renderToStaticMarkup(<FoxLantern motion={false} quiet />);
    expect(markup).toContain('data-motion="false"');
    expect(markup).toContain('aria-label="Реплики лиса"');
    expect(markup).not.toContain('role="region"');
    expect(markup).toContain('class="fox-flame"');
    expect(markup.match(/class="fox-light-breathe"/g)).toHaveLength(2);
  });
});
