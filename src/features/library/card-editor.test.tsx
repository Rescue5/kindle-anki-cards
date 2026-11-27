import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CardEditor, WordTranslationDetails } from "./card-editor";
import { mockBackend, resetMockBackend } from "@/lib/mock-backend";
import type { DecisionValue, Enrichment, LibraryResult, StudyPrioritySource } from "@/types";

async function renderEditor(readOnly = false, edited = false, decision: DecisionValue | null = null, prioritySource?: StudyPrioritySource) {
  resetMockBackend({ scenario: "mixed", instant: true });
  const library = await mockBackend<LibraryResult>("load_library", {});
  const entry = library.entries[0];
  entry.decision = decision ? { value: decision, decided_at: "" } : null;
  entry.study_priority = { level: 8, score: .07, provisional: true, reason: "Недостаточно истории для точной оценки" };
  if (edited && entry.card) entry.card = { ...entry.card, meaning_source: "edited", meaning_ru: "Мой перевод" };
  return renderToStaticMarkup(<CardEditor entry={entry} prioritySource={prioritySource} readOnly={readOnly} busy={false} headingRef={React.createRef()}
    llmEnabled={true} onEnrich={() => {}}
    onSave={async () => {}} onDecision={async () => {}} onDirtyChange={() => {}} onPendingChange={() => {}} />);
}

describe("card editor states", () => {
  it.each(["rp-v2-coverage", "rp-v2-personal"] as const)("keeps reader evidence but hides legacy scoring reasons in %s", async (source) => {
    expect(await renderEditor()).toContain("Искали 2 раза");
    const html = await renderEditor(false, false, null, source);
    expect(html).toContain("Недостаточно истории для точной оценки");
    expect(html).toContain("Записей поиска: 2");
    expect(html).not.toContain("Искали 2 раза");
    expect(html).not.toContain("Оценено локальными частотными и морфологическими правилами");
  });
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
    const learnButton = html.split("</button>").find((fragment) => fragment.endsWith("Учить"));
    expect(learnButton).toMatch(/<button[^>]*disabled/);
  });
  it("separates the priority reason from the personal choice and allows changing or removing it", async () => {
    const html = await renderEditor(false, false, "skip");
    expect(html).toContain("Приоритет 8 из 10 · предварительно");
    expect(html).toContain("Недостаточно истории для точной оценки");
    expect(html).toContain("Моё решение · Не учить");
    expect(html).toContain(">Учить</button>");
    expect(html).toContain("Снять моё решение");
  });
  it("offers individual translation and retry only for eligible words with LLM enabled, respecting the lock", async () => {
    resetMockBackend({ scenario: "mixed", instant: true });
    const entry = (await mockBackend<LibraryResult>("load_library", {})).entries[0];
    entry.enrichment = null;
    entry.enrichment_state = "pending";
    const render = (llmEnabled = true, disabled = false) => renderToStaticMarkup(<WordTranslationDetails entry={entry}
      llmEnabled={llmEnabled} disabled={disabled} onEnrich={() => {}} />);
    expect(render()).toContain("Перевести слово");
    expect(render(false)).not.toContain("<button");
    expect(render(true, true)).toMatch(/<button[^>]*disabled/);
    entry.enrichment = { status: "failed", error: "Ошибка", provider: "test", model: "test", updated_at: "", prompt_version: 1 };
    entry.enrichment_state = "failed";
    expect(render()).toContain("Повторить перевод слова");
    entry.processing.state = "pending";
    entry.enrichment_state = "ineligible";
    expect(render()).not.toContain("<button");
  });
  it("shows ready generated examples separately without attaching a translation to another book context", async () => {
    resetMockBackend({ scenario: "mixed", instant: true });
    const entry = (await mockBackend<LibraryResult>("load_library", {})).entries[0];
    entry.enrichment = { status: "ready", example_en: "A generated example.", example_ru: "Созданный пример.",
      context_ru: "Перевод другого контекста", error: "", provider: "test", model: "test", updated_at: "", prompt_version: 1 } satisfies Enrichment;
    entry.enrichment_state = "pending";
    const html = renderToStaticMarkup(<WordTranslationDetails entry={entry} llmEnabled={true} disabled={false} onEnrich={() => {}} />);
    expect(html).toContain("A generated example.");
    expect(html).toContain("Созданный пример.");
    expect(html).not.toContain("Перевод другого контекста");
    expect(html).toContain("Перевести слово с ИИ");
  });

  it("links the verified sense and generated examples to the saved review", async () => {
    resetMockBackend({ scenario: "mixed", instant: true });
    const entry = (await mockBackend<LibraryResult>("load_library", {})).entries[0];
    entry.enrichment = { status: "ready", meaning_ru: "берег; банк", meaning_action: "kept", context_quality: "good", context_meaning_ru: "берег",
      context_truncated: true, context_ru: "На другом берегу", senses: [
        { meaning_ru: "берег реки", example_en: "He stood on the bank.", example_ru: "Он стоял на берегу." },
        { meaning_ru: "банк", example_en: "The bank closed at five.", example_ru: "Банк закрылся в пять." },
      ], provider: "test", model: "test", updated_at: "", error: "", prompt_version: 2 };
    entry.enrichment_state = "ready";
    const render = () => renderToStaticMarkup(<WordTranslationDetails entry={entry} llmEnabled disabled={false} onEnrich={() => {}} />);
    expect(render()).toContain("ИИ подтвердил исходный перевод");
    expect(render()).toContain("В этой цитате");
    expect(render()).toContain("Перевод фрагмента");
    expect(render()).toContain("Банк закрылся в пять.");
    entry.enrichment_state = "pending";
    expect(render()).not.toContain("В этой цитате");
  });
});
