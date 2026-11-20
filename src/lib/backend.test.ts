import { describe, expect, it } from "vitest";
import { BridgeError, parseBridgeError } from "./backend";

describe("bridge errors", () => {
  it("turns the JSON the Rust bridge rejects with into a BridgeError with code and message", () => {
    const error = parseBridgeError('{"error": "Не удалось выполнить экспорт: диск полон", "code": "export_failed"}');
    expect(error).toBeInstanceOf(BridgeError);
    expect(error).toMatchObject({ code: "export_failed", message: "Не удалось выполнить экспорт: диск полон" });
  });

  it("reads an error without a code", () => {
    const error = parseBridgeError('{"error": "Операция отменена"}') as BridgeError;
    expect(error).toBeInstanceOf(BridgeError);
    expect(error.code).toBeUndefined();
    expect(error.message).toBe("Операция отменена");
  });

  it("prints as its Russian text, so code that shows String(error) stays clean", () => {
    expect(String(new BridgeError("Нет слов для экспорта", "nothing_to_export"))).toBe("Нет слов для экспорта");
  });

  it("passes plain strings, other JSON and non-strings through untouched", () => {
    expect(parseBridgeError("python bridge crashed")).toBe("python bridge crashed");
    expect(parseBridgeError('{"ok": false}')).toBe('{"ok": false}');
    expect(parseBridgeError("{not json")).toBe("{not json");
    const original = new Error("boom");
    expect(parseBridgeError(original)).toBe(original);
  });
});
