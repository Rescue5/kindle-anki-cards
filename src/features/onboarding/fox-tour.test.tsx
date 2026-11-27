import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { FoxTour } from "./fox-tour";

vi.mock("@radix-ui/react-dialog", async (importOriginal) => {
  const dialog = await importOriginal<typeof import("@radix-ui/react-dialog")>();
  // SSR has no portal target. Keep the real Radix children for markup checks.
  return { ...dialog, Portal: ({ children }: React.PropsWithChildren) => children };
});

describe("FoxTour", () => {
  it("opens on the first example with immediate next and skip actions", () => {
    const html = renderToStaticMarkup(<FoxTour open onDismiss={() => {}} />);
    expect(html).toContain('role="dialog"');
    expect(html).toContain("Экскурсия с лисом");
    expect(html).toMatch(/<h3[^>]*tabindex="-1"[^>]*><span[^>]*>Шаг 1 из 4\. <\/span>Загрузим слова<\/h3>/);
    expect(html).toContain('class="fox-figure"');
    expect(html).toContain("Я покажу, как взять слова из книги с собой.");
    expect(html).toContain("Учебный пример");
    expect(html).toContain(">Пропустить</button>");
    expect(html).toContain(">Далее</button>");
    expect(html).not.toContain(">Назад</button>");
  });

  it("keeps the tour out of the document while closed", () => {
    expect(renderToStaticMarkup(<FoxTour open={false} onDismiss={() => {}} />)).toBe("");
  });
});
