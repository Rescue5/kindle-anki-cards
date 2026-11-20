import { describe, expect, it } from "vitest";
import { dateKey, formatDate, greeting, partOfSpeechShort, ruCount } from "./reading-domain";

describe("home helpers", () => {
  it("declines Russian counts correctly", () => {
    expect([1, 3, 11, 21].map((value) => ruCount(value, "слово", "слова", "слов"))).toEqual(["слово", "слова", "слов", "слово"]);
  });

  it("accepts only real calendar dates and says so when a date is unknown", () => {
    expect(dateKey("2026-09-28T10:00:00Z")).toBe("2026-09-28");
    expect(dateKey("2026-02-31")).toBeNull();
    expect(dateKey("")).toBeNull();
    expect(formatDate("")).toBe("Дата неизвестна");
  });

  it("greets by the time of day", () => {
    expect(greeting(new Date(2026, 9, 30, 7))).toBe("Доброе утро");
    expect(greeting(new Date(2026, 9, 30, 13))).toBe("Добрый день");
    expect(greeting(new Date(2026, 9, 30, 21))).toBe("Добрый вечер");
    expect(greeting(new Date(2026, 9, 30, 2))).toBe("Доброй ночи");
  });

  it("abbreviates parts of speech like a dictionary", () => {
    expect(partOfSpeechShort("n")).toBe("сущ.");
    expect(partOfSpeechShort("s")).toBe("прил.");
    expect(partOfSpeechShort(undefined)).toBe("");
  });
});
