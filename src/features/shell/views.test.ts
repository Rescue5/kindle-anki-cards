import { describe, expect, it } from "vitest";
import { NAV_VIEWS, VIEWS, navViewOf, parseView } from "./views";

describe("views", () => {
  it("lights the Слова entry for the screens that open from it", () => {
    expect(navViewOf("triage")).toBe("words");
    expect(navViewOf("export")).toBe("words");
    expect(navViewOf("home")).toBe("home");
    expect(navViewOf("settings")).toBe("settings");
  });

  it("maps every view to a navigation entry", () => {
    for (const view of VIEWS) expect(NAV_VIEWS).toContain(navViewOf(view));
  });

  it("opens the requested screen, or the home screen for anything unknown", () => {
    expect(parseView("?view=words&scenario=no-new")).toBe("words");
    expect(parseView("?view=export")).toBe("export");
    expect(parseView("?view=books")).toBe("home");
    expect(parseView("")).toBe("home");
  });
});
