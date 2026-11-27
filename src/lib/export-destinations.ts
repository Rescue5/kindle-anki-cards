import type { ExportDestination } from "@/types";

export const exportDestinationLabels = {
  anki: "Anki",
  obsidian: "Obsidian · Spaced Repetition",
  quizlet: "Quizlet",
  remnote: "RemNote",
  csv: "Подробный TSV",
} as const satisfies Record<ExportDestination, string>;

export function isExportDestination(value: string): value is ExportDestination {
  return Object.prototype.hasOwnProperty.call(exportDestinationLabels, value);
}

export function obsidianVaultPathError(path: string): string | null {
  const value = path.trim();
  if (!value) return "Укажите корневую папку хранилища Obsidian.";
  if (/^(?:\/(?!\/)|[A-Za-z]:[\\/]|(?:\\\\|\/\/)[^\\/]+[\\/][^\\/]+)/u.test(value)) return null;
  return "Укажите абсолютный путь к хранилищу Obsidian.";
}
