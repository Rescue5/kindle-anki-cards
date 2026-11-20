import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PencilButton, PencilChoice, PencilField, PencilLink, PencilRadioGroup } from "./pencil-controls";

const html = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("pencil controls", () => {
  it("draws a frame on a drawn button and none on a lit one", () => {
    expect(html(<PencilButton>К словам</PencilButton>)).toContain("pencil-frame");
    expect(html(<PencilButton look="lit">Экспортировать 5</PencilButton>)).not.toContain("pencil-frame");
  });

  it("blocks a loading button and says it is busy", () => {
    const markup = html(<PencilButton look="lit" loading>Экспортировать</PencilButton>);
    expect(markup).toContain("disabled");
    expect(markup).toContain('aria-busy="true"');
    expect(markup).toContain('data-loading="true"');
    expect(markup).toContain("kc-spin");
  });

  it("writes a keyboard hint inside the button", () => {
    expect(html(<PencilButton hint="1">Знаю</PencilButton>)).toContain("<kbd>1</kbd>");
  });

  it("announces a choice as a pressed toggle", () => {
    expect(html(<PencilChoice pressed>Учить</PencilChoice>)).toContain('aria-pressed="true"');
    expect(html(<PencilChoice pressed={false}>Знаю</PencilChoice>)).toContain('aria-pressed="false"');
  });

  it("is an anchor with an href and a button without one, and inert while loading", () => {
    expect(html(<PencilLink href="#folder">Открыть папку</PencilLink>)).toMatch(/^<a /);
    expect(html(<PencilLink onClick={() => undefined}>Закончить позже</PencilLink>)).toMatch(/^<button /);
    expect(html(<PencilLink href="#x" loading>Открыть</PencilLink>)).toContain('aria-disabled="true"');
    const lit = html(<PencilLink lit>Проверить спорные</PencilLink>);
    expect(lit).toContain("is-lit");
  });

  it("keeps one radio tabbable and falls back to the first enabled when nothing is chosen", () => {
    const options = [
      { value: "a", content: "Первый", disabled: true },
      { value: "b", content: "Второй" },
      { value: "c", content: "Третий" },
    ];
    const none = html(<PencilRadioGroup label="Пример" value={null} options={options} onChange={() => undefined} />);
    expect(none).toContain('role="radiogroup"');
    expect(none.match(/tabindex="0"/g)).toHaveLength(1);
    expect(none.indexOf('tabindex="0"')).toBeGreaterThan(none.indexOf("Первый"));
    const chosen = html(<PencilRadioGroup label="Пример" value="c" options={options} onChange={() => undefined} />);
    expect(chosen).toContain('aria-checked="true"');
    expect(chosen.match(/tabindex="0"/g)).toHaveLength(1);
    const busy = html(<PencilRadioGroup label="Пример" value="b" options={options} onChange={() => undefined} loading />);
    expect(busy).toContain('aria-busy="true"');
  });

  it("labels a field, ties the error and the hint to it, and marks a save in flight", () => {
    const markup = html(<PencilField label="Перевод" defaultValue="проблеск" hint="Сохраняется при выходе из поля" error="Перевод длиннее 200 символов" loading />);
    expect(markup).toContain("<label");
    expect(markup).toContain("Перевод");
    expect(markup).toContain('aria-invalid="true"');
    expect(markup).toContain('role="alert"');
    expect(markup).toMatch(/aria-describedby="[^"]+-error [^"]+-hint"/);
    expect(markup).toContain('aria-busy="true"');
    expect(html(<PencilField label="Перевод" hideLabel />)).toContain("sr-only");
  });
});
