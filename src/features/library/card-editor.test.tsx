import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CardEditor, WordTranslationDetails } from "./card-editor";
import { mockBackend, resetMockBackend } from "@/lib/mock-backend";
import type { Enrichment, LibraryResult } from "@/types";

async function renderEditor(readOnly = false, edited = false) {
  resetMockBackend({ scenario: "mixed", instant: true });
  const library = await mockBackend<LibraryResult>("load_library", {});
  const entry = library.entries[0];
  if (edited && entry.card) entry.card = { ...entry.card, meaning_source: "edited", meaning_ru: "Мой перевод" };
  return renderToStaticMarkup(<CardEditor entry={entry} readOnly={readOnly} busy={false} headingRef={React.createRef()}
    llmEnabled={true} onEnrich={() => {}}
    onSave={async () => {}} onDecision={async () => {}} onDirtyChange={() => {}} onPendingChange={() => {}} />);
}

describe("card editor states", () => {
  it("offers reset only for an edited translation", async () => {
    expect(await renderEditor()).not.toContain("Вернуть исходный перевод");
    expect(await renderEditor(false, true)).toContain("Вернуть исходный перевод");
  });
  it("renders demo as a read-only card with disabled editing and decision actions", async () => {
    const html = await renderEditor(true);
    expect(html).toContain("только просмотр");
    expect(html).toMatch(/<textarea[^>]*disabled/);
    expect(html).toMatch(/<select[^>]*disabled/);
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Не учить/);
  });
  it("offers individual translation and retry only for eligible words with LLM enabled, respecting the lock", async () => {
    resetMockBackend({ scenario: "mixed", instant: true });
    const entry = (await mockBackend<LibraryResult>("load_library", {})).entries[0];
    entry.enrichment = null;
    const render = (llmEnabled = true, disabled = false) => renderToStaticMarkup(<WordTranslationDetails entry={entry}
      llmEnabled={llmEnabled} disabled={disabled} onEnrich={() => {}} />);
    expect(render()).toContain("Перевести слово");
    expect(render(false)).not.toContain("<button");
    expect(render(true, true)).toMatch(/<button[^>]*disabled/);
    entry.enrichment = { status: "failed", error: "Ошибка", provider: "test", model: "test", updated_at: "", prompt_version: 1 };
    expect(render()).toContain("Повторить перевод слова");
    entry.processing.state = "pending";
    expect(render()).not.toContain("<button");
  });
  it("shows ready generated examples separately without attaching a translation to another book context", async () => {
    resetMockBackend({ scenario: "mixed", instant: true });
    const entry = (await mockBackend<LibraryResult>("load_library", {})).entries[0];
    entry.enrichment = { status: "ready", example_en: "A generated example.", example_ru: "Созданный пример.",
      context_ru: "Перевод другого контекста", error: "", provider: "test", model: "test", updated_at: "", prompt_version: 1 } satisfies Enrichment;
    const html = renderToStaticMarkup(<WordTranslationDetails entry={entry} llmEnabled={true} disabled={false} onEnrich={() => {}} />);
    expect(html).toContain("A generated example.");
    expect(html).toContain("Созданный пример.");
    expect(html).not.toContain("Перевод другого контекста");
    expect(html).not.toContain("<button");
  });
});
